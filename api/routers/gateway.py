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
from services.gateway.nex_pipeline import (
    compress_to_nex_async,
    call_logic_provider_async,
    translate_from_nex_blocking_async,
)

router = APIRouter(prefix="/v1", tags=["Gateway"])

# DeepSeek pricing (per 1M tokens)
COST_PER_1M_INPUT  = Decimal("0.14")
COST_PER_1M_OUTPUT = Decimal("0.28")


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

    original_payload = ""
    compressed_text = ""
    raw_response = ""
    nex_output = ""
    is_complex = False

    try:
        body = await raw_request.json()
        original_payload = json.dumps(body)
        messages = [m.model_dump() for m in request.messages]

        # ── Count original tokens ──────────────────────────────────────────────
        full_input = " ".join(m["content"] for m in messages)
        tokens_original = _estimate_tokens(full_input)

        # ── Detect payload type ────────────────────────────────────────────────
        has_code = any(
            "```" in m["content"] or "def " in m["content"] or "class " in m["content"]
            for m in messages
        )

        # ══════════════════════════════════════════════════════════════════════
        # STAGE 1 — NEX Compression (human → NEX bytecode)
        # Uses system DeepSeek key always.  If no key available, we fall back
        # to the simple rule-based compressors.
        # ══════════════════════════════════════════════════════════════════════
        user_text = messages[-1]["content"] if messages else ""
        nex_input = await compress_to_nex_async(
            db=db,
            human_text=user_text,
            context_text="",
            messages_history=messages[:-1],
        )

        # If Stage 1 produced the same text (no key / fallback), also apply
        # rule-based compression on every message.
        if nex_input == user_text:
            # Fallback: rule-based compression per message
            compressed_messages = []
            for msg in messages:
                content = msg["content"]
                if has_code:
                    result = NEXCodeCompressor.compress_input(content, extreme=True)
                else:
                    result = NEXTextCompressor.compress_input(content, extreme=True)
                compressed_messages.append({**msg, "content": result.compressed})
            compressed_text = " ".join(m["content"] for m in compressed_messages)
            nex_messages = compressed_messages
        else:
            # Use NEX bytecode as the final user message, keep history untouched
            compressed_text = nex_input
            nex_messages = messages[:-1] + [{"role": "user", "content": nex_input}]

        tokens_compressed = _estimate_tokens(compressed_text)

        # ══════════════════════════════════════════════════════════════════════
        # CASCADE ROUTING — pick provider
        # ══════════════════════════════════════════════════════════════════════
        cascade_router = await CascadeConfigLoader.load_for_organization_async(db, organization)
        is_complex = cascade_router.is_complex(compressed_text)

        if api_key_obj.linked_provider_id:
            stmt_p = select(AIProvider).where(AIProvider.id == api_key_obj.linked_provider_id)
        elif is_complex and cascade_router.heavyweight_provider_id:
            stmt_p = select(AIProvider).where(AIProvider.id == cascade_router.heavyweight_provider_id)
        elif not is_complex and cascade_router.cheap_provider_id:
            stmt_p = select(AIProvider).where(AIProvider.id == cascade_router.cheap_provider_id)
        else:
            stmt_p = select(AIProvider).where(
                AIProvider.organization_id == organization.id,
                AIProvider.is_active == True,
                AIProvider.is_default == True,
            ).limit(1)

        res_p = await db.execute(stmt_p)
        provider_used = res_p.scalar_one_or_none()

        if not provider_used:
            stmt_p2 = select(AIProvider).where(
                AIProvider.organization_id == organization.id,
                AIProvider.is_active == True,
            ).limit(1)
            res_p2 = await db.execute(stmt_p2)
            provider_used = res_p2.scalar_one_or_none()

        if not provider_used:
            raise HTTPException(
                status_code=503,
                detail="No AI provider configured. Add one in the dashboard under AI Providers."
            )

        # ══════════════════════════════════════════════════════════════════════
        # STAGE 2 — Core AI call (NEX input → NEX output)
        # Uses the provider selected by cascade routing.
        # ══════════════════════════════════════════════════════════════════════
        raw_response, prompt_tokens_used, completion_tokens = await call_logic_provider_async(
            provider=provider_used,
            nex_messages=nex_messages,
            model=request.model or None,
            temperature=request.temperature,
        )
        nex_output = raw_response

        # ══════════════════════════════════════════════════════════════════════
        # STAGE 3 — NEX → Human translation (always system DeepSeek)
        # If no system key, fall back to rule-based output decompression.
        # ══════════════════════════════════════════════════════════════════════
        human_text, _, _ = await translate_from_nex_blocking_async(db=db, nex_text=nex_output)

        if human_text and human_text.strip() and human_text != nex_output:
            final_text = human_text
        else:
            # Fallback: rule-based output post-processing
            if has_code:
                out_result = NEXCodeCompressor.compress_output(nex_output)
            else:
                out_result = NEXTextCompressor.compress_output(nex_output)
            final_text = out_result.compressed or nex_output

    except HTTPException:
        raise
    except Exception as exc:
        error_text = str(exc)
        final_text = f"[Gateway error: {error_text}]"

    # ── Cost calculation ──────────────────────────────────────────────────────
    latency_ms = int((time.time() - start_time) * 1000)
    pt = max(prompt_tokens_used, tokens_compressed)
    ct = completion_tokens
    cost_actual   = (Decimal(pt)  / Decimal(1_000_000) * COST_PER_1M_INPUT
                   + Decimal(ct)  / Decimal(1_000_000) * COST_PER_1M_OUTPUT)
    cost_original = (Decimal(tokens_original) / Decimal(1_000_000) * COST_PER_1M_INPUT
                   + Decimal(ct) / Decimal(1_000_000) * COST_PER_1M_OUTPUT)
    cost_saved    = max(Decimal("0"), cost_original - cost_actual)
    comp_ratio    = round((1 - tokens_compressed / tokens_original) * 100, 1) if tokens_original > 0 else 0.0

    # ── Write AuditLog ────────────────────────────────────────────────────────
    try:
        audit = AuditLog(
            organization_id=organization.id,
            user_id=api_key_obj.user_id,  # Link to the owner of the API key
            api_key_id=api_key_obj.id,
            ai_provider_id=provider_used.id if provider_used else None,
            original_payload=original_payload,
            compressed_payload=compressed_text,
            deepseek_response=nex_output,
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
            data_bytes_in=len(original_payload.encode()),
            data_bytes_out=len(final_text.encode()),
        )
        db.add(audit)
        await db.commit()
    except Exception:
        await db.rollback()

    if error_text and final_text.startswith("[Gateway error"):
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
            "stage1_nex_compression": True,
            "stage2_provider": provider_used.name if provider_used else "none",
            "stage3_nex_translation": True,
            "tokens_original": tokens_original,
            "tokens_compressed": tokens_compressed,
            "compression_ratio_pct": comp_ratio,
            "cost_actual_usd": float(cost_actual),
            "cost_saved_usd": float(cost_saved),
            "is_complex_request": is_complex,
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
            "X-NEX-Stage1":         "enabled",
            "X-NEX-Stage3":         "enabled",
        },
    )
