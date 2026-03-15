import json
import time
import re
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from api.dependencies import get_db, verify_api_key
from schemas.gateway import ChatCompletionRequest
from models.dashboard import APIKey, AIProvider, AuditLog
from models.accounts import Organization

from services.gateway.compression.dual_engine import DualEngineCompressor
from services.gateway.cache import SemanticCache
from services.gateway.decoder import DeterministicDecoder
from services.gateway.cascade_router import CascadeRouter, CascadeConfigLoader
from services.gateway.edge.router import EdgeRouter
from services.gateway.nex_pipeline import (
    compress_to_nex_async,
    call_logic_provider_async,
    translate_from_nex_blocking_async,
    stream_translate_from_nex_async
)
from services.gateway.prompts import NEX_COMPRESSION_RULES

router = APIRouter(prefix="/v1", tags=["Gateway"])

COST_PER_1M_INPUT = Decimal('0.14')
COST_PER_1M_OUTPUT = Decimal('0.28')

from services.gateway.compression.ast_pruner import ASTPruner
from fastapi.concurrency import run_in_threadpool

@router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    raw_request: Request,
    auth: tuple = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
):
    api_key, organization = auth
    start_time = time.time()
    
    body = await raw_request.json()
    original_payload = json.dumps(body, indent=2)
    messages = [m.model_dump() for m in request.messages]
    
    # Pre-Flight: Granular Token Telemetry (Word-count placeholder)
    tokens_original = sum(len(m['content'].split()) for m in messages)

    # 1. Algorithmic Compression (AST Pruning for Code)
    for msg in messages:
        if "```" in msg['content']:
            # Extract code blocks and prune them
            code_blocks = re.findall(r'```(?:python)?\n(.*?)\n```', msg['content'], re.DOTALL)
            for block in code_blocks:
                pruned = ASTPruner.prune(block, "python")
                msg['content'] = msg['content'].replace(block, pruned)

    # 2. Dynamic Cascade Routing setup
    cascade_router = await CascadeConfigLoader.load_for_organization_async(db, organization)
    user_prompt = messages[-1]['content']
    
    # 3. Decision Logic: Direct to Gemini if complex, else DeepSeek
    is_complex = cascade_router.is_complex(user_prompt)
    
    # 4. DeepSeek Summarization Branch (Cost-saving branch for large text before Gemini)
    if not is_complex and len(user_prompt.split()) > 1500:
        summary_prompt = f"Summarize the following high-signal content for a reasoning model: {user_prompt}"
        # We use a system-level DeepSeek provider for summarization
        stmt = select(AIProvider).where(AIProvider.name == "DeepSeek-V3", AIProvider.is_system == True)
        summ_provider = (await db.execute(stmt)).scalar_one_or_none()
        
        if summ_provider:
            summary_res, p2, r2 = await call_logic_provider_async(
                summ_provider, 
                [{"role": "user", "content": summary_prompt}]
            )
            user_prompt = summary_res
            messages[-1]['content'] = user_prompt
            is_complex = True # Now escalate to Gemini

    async def call_provider_wrapped(prov, msgs):
        return await call_logic_provider_async(prov, msgs, model=request.model, temperature=request.temperature)

    # 5. Execute Routing Strategy
    # CascadeRouter.route handles Tier 1 (DeepSeek) and Escalation (Gemini) if needed
    nex_output, cascade_meta = await run_in_threadpool(cascade_router.route, messages, call_provider_wrapped)

    # Stage 3: Human Translation (NEX -> Natural Language)
    final_text, p3, r3 = await translate_from_nex_blocking_async(db, nex_output)
    
    # Post-Flight Auditing
    tokens_compressed = sum(len(m['content'].split()) for m in messages)
    completion_tokens = r3
    latency_ms = int((time.time() - start_time) * 1000)
    
    response_data = {
        'id': f"chatcmpl-{int(time.time())}",
        'object': 'chat.completion',
        'choices': [{"index": 0, "message": {"role": "assistant", "content": final_text}}],
        'usage': {
            'prompt_tokens': tokens_original,
            'completion_tokens': completion_tokens,
            'total_tokens': tokens_original + completion_tokens
        },
        'firmaki_telemetry': {
            'cascade_routing': cascade_meta,
            'latency_ms': latency_ms,
            'compression': {
                'engine': 'ast_pruner_v1',
                'reduction_pct': round((1 - (tokens_compressed / tokens_original)) * 100, 1) if tokens_original > 0 else 0
            }
        }
    }

    # Atomic Audit Log commit
    audit = AuditLog(
        organization_id=organization.id,
        api_key_id=api_key.id,
        original_payload=original_payload,
        compressed_payload=user_prompt,
        deepseek_response=nex_output,
        final_response=json.dumps(response_data),
        tokens_original=tokens_original,
        tokens_compressed=tokens_compressed,
        tokens_response=completion_tokens,
        status="success",
        latency_ms=latency_ms
    )
    db.add(audit)
    await db.commit()

    return JSONResponse(response_data)
