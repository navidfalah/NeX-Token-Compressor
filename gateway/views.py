"""
Firma-KI Gateway — Views
The main reverse proxy endpoint. OpenAI-compatible chat completions.
"""
import json
import time
from decimal import Decimal

from django.http import JsonResponse, StreamingHttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from dashboard.models import AuditLog, CompressionRule, PIIConfig
from .authentication import authenticate_api_key, APIKeyAuthenticationError
from .pii_masker import PIIMasker
from .compressor import TokenCompressor
from .cache import SemanticCache
from .deepseek_client import DeepSeekClient
from .decoder import DeterministicDecoder


@method_decorator(csrf_exempt, name='dispatch')
class ChatCompletionsView(View):
    """
    POST /v1/chat/completions

    OpenAI-compatible reverse proxy endpoint.
    Pipeline: Auth → PII Mask → NEX Stage 1 → Stage 2 Logic → Stage 3 Expander → Decode → Response
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

        # 3. PII Masking
        try:
            pii_config = PIIConfig.objects.get(organization=organization)
        except PIIConfig.DoesNotExist:
            pii_config = None

        masker = PIIMasker(pii_config)
        mask_map = {}
        masked_messages = []
        
        # Inject Stage 1 NEX Generation rules
        try:
            from django.conf import settings
            import os
            rules_path = os.path.join(settings.BASE_DIR, 'COMPRESSION_RULES.md')
            with open(rules_path, 'r', encoding='utf-8') as f:
                nex_rules = f.read()
            masked_messages.append({
                'role': 'system',
                'content': f"You are a highly efficient Firma-KI NEX compression engine. Answer the user's queries concisely and accurately in strict accordance with the core rules.\n\nCRITICAL INSTRUCTION: You must strictly output your logic in NEX Bytecode according to the following framework:\n{nex_rules}"
            })
        except Exception as e:
            print(f"Warning: Could not load COMPRESSION_RULES.md: {e}")
            
        for msg in messages:
            if msg.get('content'):
                masked_content, msg_mask_map = masker.mask(msg['content'])
                mask_map.update(msg_mask_map)
                masked_messages.append({**msg, 'content': masked_content})
            else:
                masked_messages.append(msg)

        # 4. Cache Check
        cache = SemanticCache(organization)
        cached_response, cache_hit = cache.get(masked_messages)

        if cache_hit:
            # Return cached response
            latency_ms = int((time.time() - start_time) * 1000)
            decoder = DeterministicDecoder(masker)
            decoded_content = decoder.decode(
                cached_response.get('content', ''), mask_map
            )
            cached_response['content'] = decoded_content
            response_data = decoder.format_openai_response(cached_response)

            # Log the cache hit
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

        # 5. Execute 3-Stage NEX Pipeline
        is_streaming = body.get('stream', False)
        from dashboard.models import AIProvider
        from gateway.nex_pipeline import compress_to_nex, call_logic_provider_blocking, translate_from_nex_blocking, stream_translate_from_nex
        
        provider = api_key.linked_provider
        if not provider:
            provider = AIProvider.objects.filter(is_system=True, is_active=True).first()
        if not provider:
            provider = AIProvider.objects.filter(organization=organization, is_active=True).first()

        messages_history = masked_messages[:-1] if masked_messages else []
        last_message = masked_messages[-1]['content'] if masked_messages else ""

        try:
            # --- STAGE 1: NEX BYTECODE COMPRESSION ---
            nex_input = compress_to_nex(last_message, messages_history=messages_history)
            tokens_original = len(last_message.split()) + sum(len(m.get('content', '').split()) for m in messages_history)
            tokens_compressed = len(nex_input.split())
            compressed_payload = nex_input

            # --- STAGE 2: MIDDLE AI (LOGIC) ---
            s2_sys = "You are a pure logic engine. Solve concisely in minimal tokens."
            s2_msgs = [{'role': 'system', 'content': s2_sys}, {'role': 'user', 'content': nex_input}]
            nex_output, p2, r2 = call_logic_provider_blocking(provider, s2_msgs, model=body.get('model'), temperature=body.get('temperature', 0.1))
            
            if not nex_output:
                nex_output = "(Logic engine failed to respond)"

            if not is_streaming:
                # --- STAGE 3: THIRD AI (EXPANDER) ---
                final_text, p3, r3 = translate_from_nex_blocking(nex_output)

                # Decode & re-inject PII
                decoder = DeterministicDecoder(masker)
                decoded_content = decoder.decode(final_text, mask_map)
                
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
                cache.set(masked_messages, response_data, response_data['usage'].get('total_tokens', 0))
                
                # Format final response
                final_response = decoder.format_openai_response(response_data)
                
                # INJECT TELEMETRY FOR STAGE 2 & 3
                final_response['firmaki_telemetry'] = {
                    'stage2_middle_ai': {
                        'input': nex_input,
                        'output': nex_output,
                    },
                    'stage3_third_ai': {
                        'input': nex_output,
                        'output': final_text,
                    }
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
                                
                                # Wait before yielding if we are mid-mask (to avoid slicing PII like "[PERSON_1]")
                                if '[' in buffer and ']' not in buffer:
                                    continue
                                    
                                decoded_chunk = decoder.decode(buffer, mask_map)
                                
                                out_chunk = {
                                    "id": "chatcmpl-firmaki",
                                    "object": "chat.completion.chunk",
                                    "model": body.get('model', 'firma-ki-pipeline'),
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {"content": decoded_chunk},
                                            "finish_reason": None
                                        }
                                    ]
                                }
                                yield f"data: {json.dumps(out_chunk)}\n\n"
                                buffer = ""
                                
                        # Finalize
                        yield "data: [DONE]\n\n"
                        
                    except Exception as stream_err:
                        # Yield a generic error frame if it breaks mid-flight
                        err_chunk = {
                            "error": str(stream_err)
                        }
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
                        
                        # We use the naive split token length for decoded as approximation if DeepSeek doesn't attach usage
                        pii_entities_list = list(mask_map.values()) if mask_map else []
                        
                        metrics_payload = {
                            "tokens_original": tokens_original,
                            "tokens_compressed": tokens_compressed,
                            "savings_percentage": int(compression_ratio * 100),
                            "latency_ms": latency_ms,
                            "cost_saved_eur": float(cost_saved),
                            "pii_entities": pii_entities_list
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
                compressed_payload=compressed_payload,
                deepseek_response=str(e),
                final_response='',
                tokens_original=tokens_original,
                tokens_compressed=tokens_compressed,
                latency_ms=latency_ms,
                status=AuditLog.STATUS_ERROR,
                error_message=str(e),
            )
            return JsonResponse({'error': f'DeepSeek API error: {str(e)}'}, status=502)
