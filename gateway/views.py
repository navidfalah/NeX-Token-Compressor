"""
Firma-KI Gateway — Views
The main reverse proxy endpoint. OpenAI-compatible chat completions.

Next-Gen Architecture:
  - Dual-Engine Generative Compression Matrix (NLC / CAC)
  - Domain-Specific Semantic Caching (embedding-based)
  - Confidence-Driven Cascade Routing
  - Edge-Native Processing (zero-latency nodes)
  - Centralized MCP Gateway (via separate endpoint)
"""
import json
import time
from decimal import Decimal

from django.http import JsonResponse, StreamingHttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from dashboard.models import AuditLog
from .authentication import authenticate_api_key, APIKeyAuthenticationError
from .compression import DualEngineCompressor
from .cache import SemanticCache
from .deepseek_client import DeepSeekClient
from .decoder import DeterministicDecoder
from .cascade_router import CascadeRouter, CascadeConfigLoader
from .edge import EdgeRouter


@method_decorator(csrf_exempt, name='dispatch')
class ChatCompletionsView(View):
    """
    POST /v1/chat/completions

    OpenAI-compatible reverse proxy endpoint.
    Pipeline: Auth → Edge Select → PII Mask → Dual-Engine Compress → Semantic Cache
              → Cascade Route → NEX Stage 1 → Stage 2 Logic → Stage 3 Expand
              → Decode → Response
    """

    # Cost per 1M tokens (DeepSeek pricing approximation)
    COST_PER_1M_INPUT = Decimal('0.14')   # €0.14 per 1M input tokens
    COST_PER_1M_OUTPUT = Decimal('0.28')  # €0.28 per 1M output tokens

    def post(self, request, *args, **kwargs):
        start_time = time.time()

        # 1. Authenticate
        try:
            api_key, organization = authenticate_api_key(request)
        except APIKeyAuthenticationError as e:
            return JsonResponse({'error': str(e)}, status=401)

        # 2. Parse request body
        try:
            body = json.loads(request.body)
            messages = body.get('messages', [])
            if not messages:
                return JsonResponse({'error': 'No messages provided.'}, status=400)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

        original_payload = json.dumps(body, indent=2)

        # 3. Edge-Native Processing — select optimal pre-processing node
        edge_node, edge_metadata = EdgeRouter.select_edge_node(
            request=request,
            organization=organization,
            require_eu_sovereignty=True,
        )

        # Inject Stage 1 NEX Generation rules
        from .prompts import NEX_COMPRESSION_RULES
        
        # Append as a system message to the front
        messages.insert(0, {
            'role': 'system',
            'content': (
                "You are a highly efficient Firma-KI NEX compression engine. "
                "Answer the user's queries concisely and accurately in strict "
                "accordance with the core rules.\n\n"
                "CRITICAL INSTRUCTION: You must strictly output your logic in "
                f"NEX Bytecode according to the following framework:\n{NEX_COMPRESSION_RULES}"
            )
        })

        # 5. Dual-Engine Generative Compression
        compressed_messages, compression_metadata = DualEngineCompressor.compress_messages(
            messages
        )
        tokens_original = compression_metadata.get('total_original_tokens', 0)
        tokens_compressed = compression_metadata.get('total_compressed_tokens', 0)

        # 6. Semantic Cache Check (embedding-based)
        cache = SemanticCache(
            organization,
            domain=body.get('domain', ''),
        )
        cached_response, cache_hit, cache_meta = cache.get(compressed_messages)

        if cache_hit:
            latency_ms = int((time.time() - start_time) * 1000)
            decoder = DeterministicDecoder()
            decoded_content = decoder.decode(
                cached_response.get('content', '')
            )
            cached_response['content'] = decoded_content
            response_data = decoder.format_openai_response(cached_response)

            # Inject gateway telemetry
            response_data['firmaki_telemetry'] = {
                'cache': cache_meta,
                'compression': {
                    'pipeline': compression_metadata.get('pipeline_details', []),
                    'reduction_pct': compression_metadata.get('total_reduction_pct', 0),
                },
                'edge': edge_metadata,
            }

            AuditLog.objects.create(
                organization=organization,
                api_key=api_key,
                original_payload=original_payload,
                compressed_payload='[CACHED]',
                deepseek_response='[CACHED]',
                final_response=json.dumps(response_data, indent=2),
                tokens_original=0,
                tokens_compressed=0,
                tokens_response=0,
                compression_ratio=1.0,
                cost_original=Decimal('0'),
                cost_actual=Decimal('0'),
                cost_saved=Decimal('0'),
                latency_ms=latency_ms,
                cache_hit=True,
                status=AuditLog.STATUS_CACHED,
            )

            return JsonResponse(response_data)

        # 7. Execute 3-Stage NEX Pipeline with Cascade Routing
        is_streaming = body.get('stream', False)
        from dashboard.models import AIProvider
        from gateway.nex_pipeline import (
            compress_to_nex, call_logic_provider_blocking,
            translate_from_nex_blocking, stream_translate_from_nex
        )

        provider = api_key.linked_provider
        if not provider:
            provider = AIProvider.objects.filter(is_system=True, is_active=True).first()
        if not provider:
            provider = AIProvider.objects.filter(organization=organization, is_active=True).first()

        messages_history = compressed_messages[:-1] if compressed_messages else []
        last_message = compressed_messages[-1]['content'] if compressed_messages else ""

        # Prepare compressed payload text for audit
        compressed_payload = last_message

        try:
            # --- STAGE 1: NEX BYTECODE COMPRESSION ---
            nex_input = compress_to_nex(last_message, messages_history=messages_history)
            tokens_compressed = len(nex_input.split())

            # --- CONFIDENCE-DRIVEN CASCADE ROUTING ---
            cascade_router = CascadeConfigLoader.load_for_organization(organization)
            cascade_metadata = {}

            # --- STAGE 2: MIDDLE AI (LOGIC) ---
            s2_sys = "You are a pure logic engine. Solve concisely in minimal tokens."
            s2_msgs = [
                {'role': 'system', 'content': s2_sys},
                {'role': 'user', 'content': nex_input}
            ]

            if cascade_router.cheap_provider and cascade_router.heavyweight_provider:
                # Use cascade routing: cheap first, escalate if uncertain
                def call_fn(prov, msgs):
                    return call_logic_provider_blocking(
                        prov, msgs,
                        model=body.get('model'),
                        temperature=body.get('temperature', 0.1)
                    )
                nex_output, cascade_metadata = cascade_router.route(s2_msgs, call_fn)
                p2 = cascade_metadata.get('total_cost_tokens', 0)
                r2 = 0
            else:
                # Standard routing (no cascade configured)
                nex_output, p2, r2 = call_logic_provider_blocking(
                    provider, s2_msgs,
                    model=body.get('model'),
                    temperature=body.get('temperature', 0.1)
                )

            if not nex_output:
                nex_output = "(Logic engine failed to respond)"

            if not is_streaming:
                # --- STAGE 3: THIRD AI (EXPANDER) ---
                final_text, p3, r3 = translate_from_nex_blocking(nex_output)

                # Stage 3 decode
                decoder = DeterministicDecoder()
                decoded_content = decoder.decode(final_text)

                response_data = {
                    'id': 'chatcmpl-firmaki',
                    'object': 'chat.completion',
                    'model': body.get('model', 'firma-ki-pipeline'),
                    'content': decoded_content,
                    'usage': {
                        'prompt_tokens': tokens_original,
                        'completion_tokens': r3,
                        'total_tokens': tokens_original + r3
                    }
                }

                # Cache the response
                cache.set(
                    compressed_messages, response_data,
                    response_data['usage'].get('total_tokens', 0)
                )

                # Format final response
                final_response = decoder.format_openai_response(response_data)

                # INJECT COMPREHENSIVE TELEMETRY
                final_response['firmaki_telemetry'] = {
                    'stage2_middle_ai': {
                        'input': nex_input,
                        'output': nex_output,
                    },
                    'stage3_third_ai': {
                        'input': nex_output,
                        'output': final_text,
                    },
                    'compression': {
                        'engine': 'dual_engine_v2',
                        'pipeline_details': compression_metadata.get('pipeline_details', []),
                        'reduction_pct': compression_metadata.get('total_reduction_pct', 0),
                    },
                    'cascade_routing': cascade_metadata,
                    'cache': cache_meta,
                    'edge': edge_metadata,
                }

                final_response_json = json.dumps(final_response, indent=2)

                # Calculate costs
                tokens_response = r3
                cost_original = (Decimal(tokens_original) / Decimal('1000000')) * self.COST_PER_1M_INPUT
                cost_actual = (Decimal(tokens_compressed) / Decimal('1000000')) * self.COST_PER_1M_INPUT
                cost_saved = cost_original - cost_actual

                compression_ratio = 0.0
                if tokens_original > 0:
                    compression_ratio = round(1 - (tokens_compressed / tokens_original), 4)

                latency_ms = int((time.time() - start_time) * 1000)

                # Audit Log
                AuditLog.objects.create(
                    organization=organization,
                    api_key=api_key,
                    original_payload=original_payload,
                    compressed_payload=compressed_payload,
                    deepseek_response=json.dumps(response_data, indent=2),
                    final_response=final_response_json,
                    tokens_original=tokens_original,
                    tokens_compressed=tokens_compressed,
                    tokens_response=tokens_response,
                    compression_ratio=compression_ratio,
                    cost_original=cost_original,
                    cost_actual=cost_actual,
                    cost_saved=cost_saved,
                    latency_ms=latency_ms,
                    cache_hit=False,
                    status=AuditLog.STATUS_SUCCESS,
                )
                return JsonResponse(final_response)

            else:
                # Streaming mode
                response_stream = stream_translate_from_nex(nex_output)
                decoder = DeterministicDecoder(masker)

                def stream_generator():
                    full_content = ""
                    buffer = ""
                    tokens_response_counter = 0

                    try:
                        for chunk_str in response_stream:
                            if not chunk_str:
                                continue

                            delta_content = chunk_str
                            if delta_content:
                                tokens_response_counter += 1
                                buffer += delta_content
                                full_content += delta_content

                                # Buffer mid-mask tokens
                                if '[' in buffer and ']' not in buffer:
                                    continue

                                decoded_chunk = decoder.decode(buffer, mask_map)

                                out_chunk = {
                                    "id": "chatcmpl-firmaki",
                                    "object": "chat.completion.chunk",
                                    "model": body.get('model', 'firma-ki-pipeline'),
                                    "choices": [{
                                        "index": 0,
                                        "delta": {"content": decoded_chunk},
                                        "finish_reason": None
                                    }]
                                }
                                yield f"data: {json.dumps(out_chunk)}\n\n"
                                buffer = ""

                        yield "data: [DONE]\n\n"

                    except Exception as stream_err:
                        err_chunk = {"error": str(stream_err)}
                        yield f"data: {json.dumps(err_chunk)}\n\n"
                    finally:
                        # Save audit metrics
                        cost_original = (Decimal(tokens_original) / Decimal('1000000')) * self.COST_PER_1M_INPUT
                        cost_actual = (Decimal(tokens_compressed) / Decimal('1000000')) * self.COST_PER_1M_INPUT
                        cost_saved = cost_original - cost_actual

                        compression_ratio = 0.0
                        if tokens_original > 0:
                            compression_ratio = round(1 - (tokens_compressed / tokens_original), 4)

                        latency_ms = int((time.time() - start_time) * 1000)

                        pii_entities_list = list(mask_map.values()) if mask_map else []

                        metrics_payload = {
                            "tokens_original": tokens_original,
                            "tokens_compressed": tokens_compressed,
                            "savings_percentage": int(compression_ratio * 100),
                            "latency_ms": latency_ms,
                            "cost_saved_eur": float(cost_saved),
                            "pii_entities": pii_entities_list,
                            "compression_engine": "dual_engine_v2",
                            "cascade_routing": cascade_metadata,
                            "edge_node": edge_metadata.get('node_selected'),
                        }

                        yield f"data: __METRICS__{json.dumps(metrics_payload)}\n\n"

                        AuditLog.objects.create(
                            organization=organization,
                            api_key=api_key,
                            original_payload=original_payload,
                            compressed_payload=compressed_payload,
                            deepseek_response=full_content,
                            final_response=full_content,
                            tokens_original=tokens_original,
                            tokens_compressed=tokens_compressed,
                            tokens_response=tokens_response_counter,
                            compression_ratio=compression_ratio,
                            cost_original=cost_original,
                            cost_actual=cost_actual,
                            cost_saved=cost_saved,
                            latency_ms=latency_ms,
                            cache_hit=False,
                            status=AuditLog.STATUS_SUCCESS,
                        )

                return StreamingHttpResponse(stream_generator(), content_type='text/event-stream')

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            AuditLog.objects.create(
                organization=organization,
                api_key=api_key,
                original_payload=original_payload,
                compressed_payload=compressed_payload if 'compressed_payload' in dir() else '',
                deepseek_response=str(e),
                final_response='',
                tokens_original=tokens_original if 'tokens_original' in dir() else 0,
                tokens_compressed=tokens_compressed if 'tokens_compressed' in dir() else 0,
                latency_ms=latency_ms,
                status=AuditLog.STATUS_ERROR,
                error_message=str(e),
            )
            return JsonResponse({'error': f'Gateway pipeline error: {str(e)}'}, status=502)
