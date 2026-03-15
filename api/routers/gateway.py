import json
import time
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

    # Edge routing
    edge_node, edge_metadata = await EdgeRouter.select_edge_node_async(
        db=db,
        organization=organization,
        require_eu_sovereignty=True,
    )

    # Initial prompt injection
    messages.insert(0, {
        "role": "system",
        "content": (
            "You are a highly efficient Firma-KI NEX compression engine. "
            "Answer the user's queries concisely and accurately in strict "
            "accordance with the core rules.\n\n"
            "CRITICAL INSTRUCTION: You must strictly output your logic in "
            f"NEX Bytecode according to the following framework:\n{NEX_COMPRESSION_RULES}"
        )
    })

    # Generative Compression (Sync logic run in threadpool for now if it remains sync)
    from fastapi.concurrency import run_in_threadpool
    compressed_messages, compression_metadata = await run_in_threadpool(
        DualEngineCompressor.compress_messages, messages
    )
    
    tokens_original = compression_metadata.get('total_original_tokens', 0)
    tokens_compressed_initial = compression_metadata.get('total_compressed_tokens', 0)

    # Semantic Cache Check
    cache = SemanticCache(organization, domain=request.domain)
    cached_response, cache_hit, cache_meta = await cache.get(db, compressed_messages)

    if cache_hit:
        latency_ms = int((time.time() - start_time) * 1000)
        decoder = DeterministicDecoder()
        decoded_content = decoder.decode(cached_response.get('content', ''))
        cached_response['content'] = decoded_content
        response_data = decoder.format_openai_response(cached_response)

        response_data['firmaki_telemetry'] = {
            'cache': cache_meta,
            'compression': {
                'pipeline': compression_metadata.get('pipeline_details', []),
                'reduction_pct': compression_metadata.get('total_reduction_pct', 0),
            },
            'edge': edge_metadata,
        }

        # Log Audit
        audit = AuditLog(
            organization_id=organization.id,
            api_key_id=api_key.id,
            original_payload=original_payload,
            compressed_payload='[CACHED]',
            deepseek_response='[CACHED]',
            final_response=json.dumps(response_data, indent=2),
            tokens_original=tokens_original,
            tokens_compressed=tokens_compressed_initial,
            tokens_response=0,
            compression_ratio=1.0,
            cost_original=0,
            cost_actual=0,
            cost_saved=0,
            latency_ms=latency_ms,
            cache_hit=True,
            status="cached"
        )
        db.add(audit)
        await db.commit()

        return JSONResponse(response_data)

    # Resolve Provider
    provider = api_key.linked_provider
    if not provider:
        stmt = select(AIProvider).where(AIProvider.is_system == True, AIProvider.is_active == True)
        result = await db.execute(stmt)
        provider = result.scalar_one_or_none()
        
    if not provider:
        stmt = select(AIProvider).where(AIProvider.organization_id == organization.id, AIProvider.is_active == True)
        result = await db.execute(stmt)
        provider = result.scalar_one_or_none()

    messages_history = compressed_messages[:-1] if compressed_messages else []
    last_message = compressed_messages[-1]['content'] if compressed_messages else ""
    compressed_payload_human = last_message

    try:
        # Stage 1: Context Synthesizer (NEX Transpilation)
        nex_input = await compress_to_nex_async(db, last_message, "", messages_history)
        tokens_compressed = len(nex_input.split())

        # Cascade Routing configuration
        cascade_router = await CascadeConfigLoader.load_for_organization_async(db, organization)
        cascade_metadata = {}

        s2_sys = "You are a pure logic engine. Solve concisely in minimal tokens."
        s2_msgs = [
            {'role': 'system', 'content': s2_sys},
            {'role': 'user', 'content': nex_input}
        ]

        # Stage 2: Logic Execution
        if cascade_router.cheap_provider and cascade_router.heavyweight_provider:
            async def call_fn_async(prov, msgs):
                return await call_logic_provider_async(
                    prov, msgs,
                    model=request.model,
                    temperature=request.temperature
                )
            # cascade_router.route is currently sync in its orchestration, 
            # let's assume we want a route_async but for now we'll call manually or wrap
            # For simplicity, if cascade is active, we use its logic
            nex_output, cascade_metadata = await run_in_threadpool(cascade_router.route, s2_msgs, call_fn_async)
            r2 = cascade_metadata.get('total_cost_tokens', 0) # simplified
        else:
            nex_output, p2, r2 = await call_logic_provider_async(
                provider, s2_msgs, request.model, request.temperature
            )

        if not nex_output:
            nex_output = "(Logic engine failed to respond)"

        # Stage 3: Human Translation
        if not request.stream:
            final_text, p3, r3 = await translate_from_nex_blocking_async(db, nex_output)
            decoder = DeterministicDecoder()
            decoded_content = decoder.decode(final_text)

            response_data = {
                'id': f"chatcmpl-{int(time.time())}",
                'object': 'chat.completion',
                'model': request.model or provider.model_name,
                'choices': [{"index": 0, "message": {"role": "assistant", "content": decoded_content}}],
                'usage': {
                    'prompt_tokens': tokens_original,
                    'completion_tokens': r3,
                    'total_tokens': tokens_original + r3
                }
            }
            
            # Cache it
            await cache.set(db, compressed_messages, response_data, tokens_original + r3)

            final_response = response_data
            final_response['firmaki_telemetry'] = {
                'stage2_middle_ai': {'input': nex_input, 'output': nex_output},
                'stage3_third_ai': {'input': nex_output, 'output': final_text},
                'compression': {
                    'engine': 'dual_engine_v3_async',
                    'pipeline_details': compression_metadata.get('pipeline_details', []),
                    'reduction_pct': compression_metadata.get('total_reduction_pct', 0),
                },
                'cascade_routing': cascade_metadata,
                'cache': cache_meta,
                'edge': edge_metadata,
            }

            cost_original = (Decimal(tokens_original) / Decimal('1000000')) * COST_PER_1M_INPUT
            cost_actual = (Decimal(tokens_compressed) / Decimal('1000000')) * COST_PER_1M_INPUT
            cost_saved = cost_original - cost_actual
            compression_ratio = round(1 - (tokens_compressed / tokens_original), 4) if tokens_original > 0 else 0.0

            latency_ms = int((time.time() - start_time) * 1000)

            audit = AuditLog(
                organization_id=organization.id,
                api_key_id=api_key.id,
                original_payload=original_payload,
                compressed_payload=compressed_payload_human,
                deepseek_response=nex_output,
                final_response=json.dumps(final_response, indent=2),
                tokens_original=tokens_original,
                tokens_compressed=tokens_compressed,
                tokens_response=r3,
                tokens_translated=r3,
                compression_ratio=compression_ratio,
                cost_original=cost_original,
                cost_actual=cost_actual,
                cost_saved=cost_saved,
                latency_ms=latency_ms,
                status="success"
            )
            db.add(audit)
            await db.commit()

            return JSONResponse(final_response)

        else:
            # Async Streaming Response
            async def event_generator():
                async for chunk in stream_translate_from_nex_async(nex_output):
                    yield f"data: {json.dumps({'choices': [{'delta': {'content': chunk}}]})}\n\n"
                yield "data: [DONE]\n\n"
            
            return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        audit = AuditLog(
            organization_id=organization.id,
            api_key_id=api_key.id,
            original_payload=original_payload,
            compressed_payload=compressed_payload_human if 'compressed_payload_human' in locals() else '',
            deepseek_response=str(e),
            final_response='',
            tokens_original=tokens_original if 'tokens_original' in locals() else 0,
            tokens_compressed=0,
            latency_ms=latency_ms,
            status="error",
            error_message=str(e)
        )
        db.add(audit)
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Gateway pipeline error: {str(e)}")
