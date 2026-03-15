import json
import time
import re
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from api.dependencies import get_db, verify_api_key
from schemas.gateway import ChatCompletionRequest
from models.dashboard import APIKey, AIProvider, AuditLog
from models.accounts import Organization

from services.gateway.compression.nex_code_compressor import NEXCodeCompressor
from services.gateway.compression.nex_text_compressor import NEXTextCompressor
from services.gateway.cascade_router import CascadeConfigLoader

router = APIRouter(prefix="/v1", tags=["Gateway"])

# DeepSeek pricing (per 1M tokens)
COST_PER_1M_INPUT  = Decimal("0.14")
COST_PER_1M_OUTPUT = Decimal("0.28")


async def _call_provider(provider: AIProvider, messages: list[dict], model: str | None = None, temperature: float = 0.7) -> tuple[str, int, int]:
    """
    Single unified HTTP call to any AI provider that follows the OpenAI chat completion API.
    Returns (response_text, prompt_tokens_used, completion_tokens_used).
    """
    import httpx

    payload = {
        "model": model or provider.model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": provider.max_tokens,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {provider.api_key}",
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{provider.api_base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return content, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    except Exception as exc:
        raise RuntimeError(f"Provider call failed ({provider.name}): {exc}") from exc


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    raw_request: Request,
    auth: tuple = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    api_key_obj, organization = auth
    start_time = time.time()
    error_text = ""
    final_text = ""
    provider_used: AIProvider | None = None
    tokens_original = 0
    tokens_compressed = 0
    prompt_tokens_used = 0
    completion_tokens = 0

    try:
        body = await raw_request.json()
        original_payload = json.dumps(body)
        messages = [m.model_dump() for m in request.messages]

        # ── Input: estimate tokens before compression ─────────────────────────
        full_input = " ".join(m["content"] for m in messages)
        tokens_original = _estimate_tokens(full_input)

        # ── Decide payload type and apply INPUT compression ───────────────────
        has_code = any("```" in m["content"] or "def " in m["content"] for m in messages)

        for msg in messages:
            content = msg["content"]
            if has_code:
                result = NEXCodeCompressor.compress_input(content)
            else:
                result = NEXTextCompressor.compress_input(content)
            msg["content"] = result.compressed

        compressed_text = " ".join(m["content"] for m in messages)
        tokens_compressed = _estimate_tokens(compressed_text)

        # ── Cascade Routing: pick the right provider ──────────────────────────
        cascade_router = await CascadeConfigLoader.load_for_organization_async(db, organization)
        user_prompt = messages[-1]["content"]
        is_complex = cascade_router.is_complex(user_prompt)

        # Try to find the correct provider from cascade config or API key
        if api_key_obj.linked_provider_id:
            stmt_p = select(AIProvider).where(AIProvider.id == api_key_obj.linked_provider_id)
        elif is_complex and cascade_router.heavyweight_provider_id:
            stmt_p = select(AIProvider).where(AIProvider.id == cascade_router.heavyweight_provider_id)
        elif not is_complex and cascade_router.cheap_provider_id:
            stmt_p = select(AIProvider).where(AIProvider.id == cascade_router.cheap_provider_id)
        else:
            # Fallback: use the default active provider
            stmt_p = select(AIProvider).where(
                AIProvider.organization_id == organization.id,
                AIProvider.is_active == True,
                AIProvider.is_default == True,
            ).limit(1)

        res_p = await db.execute(stmt_p)
        provider_used = res_p.scalar_one_or_none()

        if not provider_used:
            # Last resort: any active provider for the org
            stmt_p2 = select(AIProvider).where(
                AIProvider.organization_id == organization.id,
                AIProvider.is_active == True,
            ).limit(1)
            res_p2 = await db.execute(stmt_p2)
            provider_used = res_p2.scalar_one_or_none()

        if not provider_used:
            raise HTTPException(status_code=503, detail="No AI provider configured. Add one in the dashboard under AI Providers.")

        # ── Call AI provider ──────────────────────────────────────────────────
        raw_response, prompt_tokens_used, completion_tokens = await _call_provider(
            provider_used, messages,
            model=request.model,
            temperature=request.temperature,
        )

        # ── Output: apply OUTPUT compression (normalise AI response) ──────────
        if has_code:
            out_result = NEXCodeCompressor.compress_output(raw_response)
        else:
            out_result = NEXTextCompressor.compress_output(raw_response)
        final_text = out_result.compressed

    except HTTPException:
        raise
    except Exception as exc:
        error_text = str(exc)
        final_text = f"[Gateway error: {error_text}]"

    # ── Cost calculation ──────────────────────────────────────────────────────
    latency_ms = int((time.time() - start_time) * 1000)
    pt = max(prompt_tokens_used, tokens_compressed)
    ct = completion_tokens
    cost_actual  = Decimal(pt)  / Decimal(1_000_000) * COST_PER_1M_INPUT  \
                 + Decimal(ct)  / Decimal(1_000_000) * COST_PER_1M_OUTPUT
    cost_original = Decimal(tokens_original) / Decimal(1_000_000) * COST_PER_1M_INPUT \
                  + Decimal(ct) / Decimal(1_000_000) * COST_PER_1M_OUTPUT
    cost_saved   = max(Decimal("0"), cost_original - cost_actual)
    comp_ratio   = round((1 - tokens_compressed / tokens_original) * 100, 1) if tokens_original > 0 else 0.0

    # ── Write AuditLog ────────────────────────────────────────────────────────
    try:
        audit = AuditLog(
            organization_id=organization.id,
            api_key_id=api_key_obj.id,
            ai_provider_id=provider_used.id if provider_used else None,
            original_payload=original_payload if 'original_payload' in dir() else "",
            compressed_payload=compressed_text if 'compressed_text' in dir() else "",
            deepseek_response=raw_response if 'raw_response' in dir() else "",
            final_response=final_text,
            tokens_original=tokens_original,
            tokens_compressed=tokens_compressed,
            tokens_response=completion_tokens,
            compression_ratio=comp_ratio,
            cost_original=cost_original,
            cost_actual=cost_actual,
            cost_saved=cost_saved,
            latency_ms=latency_ms,
            status="success" if not error_text else "error",
            error_message=error_text,
            source="gateway",
            data_bytes_in=len(original_payload.encode() if 'original_payload' in dir() else b""),
            data_bytes_out=len(final_text.encode()),
        )
        db.add(audit)
        await db.commit()
    except Exception as log_exc:
        # Never let logging crash the response
        await db.rollback()

    # ── Build response ────────────────────────────────────────────────────────
    if error_text and not final_text.startswith("[Gateway"):
        raise HTTPException(status_code=500, detail=error_text)

    response_data = {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "model": provider_used.model_name if provider_used else "unknown",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": final_text},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": tokens_original,
            "completion_tokens": completion_tokens,
            "total_tokens": tokens_original + completion_tokens,
        },
        "firmaki_telemetry": {
            "tokens_original": tokens_original,
            "tokens_compressed": tokens_compressed,
            "compression_ratio_pct": comp_ratio,
            "cost_actual_usd": float(cost_actual),
            "cost_saved_usd": float(cost_saved),
            "provider_used": provider_used.name if provider_used else "none",
            "is_complex_request": is_complex if 'is_complex' in dir() else None,
            "latency_ms": latency_ms,
        },
    }
    return JSONResponse(
        content=response_data,
        headers={
            "X-Tokens-Original":    str(tokens_original),
            "X-Tokens-Compressed":  str(tokens_compressed),
            "X-Compression-Pct":    str(comp_ratio),
            "X-Cost-USD":           f"{float(cost_actual):.8f}",
            "X-Cost-Saved-USD":     f"{float(cost_saved):.8f}",
            "X-Model-Used":         provider_used.name if provider_used else "none",
            "X-Latency-MS":         str(latency_ms),
        },
    )
