"""
Firma-KI Dashboard — Views
Analytics, AI Providers, API Keys, Rules, Privacy, Files, Team, and Audit views.
"""
import json
import time
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Avg, F, Q
from django.http import JsonResponse, StreamingHttpResponse
from datetime import timedelta
from django.utils import timezone
from decimal import Decimal
import chromadb
import fitz
import docx

from .models import APIKey, AIProvider, CompressionRule, PIIConfig, AuditLog, FileAnalysis, ChatSession, ChatMessage, MaskedDocument, DocumentKeyMapping
from gateway.pii_masker import PIIMasker
from accounts.decorators import owner_required
from accounts.models import User


@login_required
def dashboard_home(request):
    """Executive analytics dashboard with live-ready data."""
    org = request.organization
    if not org:
        messages.error(request, 'No organization found. Please register first.')
        return redirect('landing')

    # Time range filter
    days = int(request.GET.get('days', 30))
    since = timezone.now() - timedelta(days=days)

    logs = AuditLog.objects.filter(organization=org, timestamp__gte=since)

    # Aggregate metrics
    metrics = logs.aggregate(
        total_requests=Count('id'),
        total_tokens_original=Sum('tokens_original'),
        total_tokens_compressed=Sum('tokens_compressed'),
        total_tokens_response=Sum('tokens_response'),
        total_tokens_translated=Sum('tokens_translated'),
        total_cost_original=Sum('cost_original'),
        total_cost_saved=Sum('cost_saved'),
        total_cost_actual=Sum('cost_actual'),
        avg_latency=Avg('latency_ms'),
        cache_hits=Count('id', filter=Q(cache_hit=True)),
        total_data_in=Sum('data_bytes_in'),
        total_data_out=Sum('data_bytes_out'),
    )

    for key in metrics:
        if metrics[key] is None:
            metrics[key] = 0

    # Financial Efficiency (Cost Savings vs Opus Baseline) dynamically
    total_orig_in = float(metrics.get('total_tokens_original') or 0)
    total_human_out = float(metrics.get('total_tokens_translated') or 0)
    total_mid_in = float(metrics.get('total_tokens_compressed') or 0)
    total_mid_out = float(metrics.get('total_tokens_response') or 0)

    cost_opus = (total_orig_in / 1_000_000) * 15.0 + (total_human_out / 1_000_000) * 75.0
    
    total_pipeline_in = total_orig_in + total_mid_in + total_mid_out
    total_pipeline_out = total_mid_in + total_mid_out + total_human_out
    
    cost_actual = (total_pipeline_in / 1_000_000) * 0.14 + (total_pipeline_out / 1_000_000) * 0.28
    
    cost_saved = max(0, cost_opus - cost_actual)

    if cost_opus > 0:
        metrics['financial_efficiency_pct'] = round((cost_saved / cost_opus) * 100, 1)
    else:
        metrics['financial_efficiency_pct'] = 0
        
    metrics['total_cost_saved'] = round(cost_saved, 4)

    # Middle AI totals
    metrics['middle_ai_input'] = metrics['total_tokens_compressed']
    metrics['middle_ai_output'] = metrics['total_tokens_response']

    # Cache hit rate
    if metrics['total_requests'] > 0:
        metrics['cache_hit_rate'] = round(
            (metrics['cache_hits'] / metrics['total_requests']) * 100, 1
        )
    else:
        metrics['cache_hit_rate'] = 0

    recent_logs = logs.order_by('-timestamp')[:50]

    # Daily aggregation for charts
    daily_stats = []
    for i in range(min(days, 30)):
        day = timezone.now().date() - timedelta(days=i)
        day_logs = logs.filter(timestamp__date=day)
        day_agg = day_logs.aggregate(
            requests=Count('id'),
            tokens_original=Sum('tokens_original'),
            tokens_compressed=Sum('tokens_compressed'),
            cost_saved=Sum('cost_saved'),
        )
        daily_stats.append({
            'date': day.isoformat(),
            'requests': day_agg['requests'] or 0,
            'tokens_original': day_agg['tokens_original'] or 0,
            'tokens_compressed': day_agg['tokens_compressed'] or 0,
            'cost_saved': float(day_agg['cost_saved'] or 0),
        })

    daily_stats.reverse()

    # Per-provider stats
    provider_stats = []
    providers = AIProvider.objects.filter(Q(organization=org) | Q(is_system=True), is_active=True).distinct()
    for provider in providers:
        p_logs = logs.filter(ai_provider=provider)
        p_agg = p_logs.aggregate(
            requests=Count('id'),
            data_in=Sum('data_bytes_in'),
            data_out=Sum('data_bytes_out'),
            tokens=Sum('tokens_compressed'),
        )
        provider_stats.append({
            'name': provider.name,
            'type': provider.get_provider_type_display(),
            'requests': p_agg['requests'] or 0,
            'data_in': p_agg['data_in'] or 0,
            'data_out': p_agg['data_out'] or 0,
            'tokens': p_agg['tokens'] or 0,
        })

    # Per-user token usage stats
    user_stats = logs.values('user__first_name', 'user__last_name', 'user__email').annotate(
        tokens_original=Sum('tokens_original'),
        tokens_response=Sum('tokens_response'),
        tokens_compressed=Sum('tokens_compressed'),
    ).order_by('-tokens_original')[:20]

    context = {
        'metrics': metrics,
        'recent_logs': recent_logs,
        'daily_stats_json': json.dumps(daily_stats),
        'provider_stats_json': json.dumps(provider_stats),
        'days': days,
        'active_keys': APIKey.objects.filter(organization=org, is_active=True).count(),
        'total_rules': CompressionRule.objects.filter(
            Q(organization=org) | Q(is_system=True), is_active=True
        ).count(),
        'providers': providers,
        'user_stats': user_stats,
    }
    return render(request, 'dashboard/home.html', context)


@login_required
def api_live_stats(request):
    """JSON endpoint for live-updating charts (AJAX polling)."""
    org = request.organization
    if not org:
        return JsonResponse({'error': 'No org'}, status=400)

    now = timezone.now()
    last_hour = now - timedelta(hours=1)
    last_5min = now - timedelta(minutes=5)

    logs_hour = AuditLog.objects.filter(organization=org, timestamp__gte=last_hour)
    logs_5min = AuditLog.objects.filter(organization=org, timestamp__gte=last_5min)

    # Per-minute breakdown (last 60 minutes)
    minute_data = []
    for i in range(60):
        minute_start = now - timedelta(minutes=i+1)
        minute_end = now - timedelta(minutes=i)
        count = logs_hour.filter(timestamp__gte=minute_start, timestamp__lt=minute_end).count()
        minute_data.append({
            'minute': minute_start.strftime('%H:%M'),
            'requests': count,
        })
    minute_data.reverse()

    # Per-provider live counts
    providers = AIProvider.objects.filter(Q(organization=org) | Q(is_system=True), is_active=True).distinct()
    provider_live = []
    for p in providers:
        count = logs_hour.filter(ai_provider=p).count()
        data_in = logs_hour.filter(ai_provider=p).aggregate(s=Sum('data_bytes_in'))['s'] or 0
        data_out = logs_hour.filter(ai_provider=p).aggregate(s=Sum('data_bytes_out'))['s'] or 0
        provider_live.append({
            'name': p.name,
            'type': p.provider_type,
            'requests_hour': count,
            'data_in': data_in,
            'data_out': data_out,
        })

    return JsonResponse({
        'requests_5min': logs_5min.count(),
        'requests_hour': logs_hour.count(),
        'minute_data': minute_data,
        'provider_live': provider_live,
        'timestamp': now.isoformat(),
    })


@login_required
def api_key_list(request):
    """List and manage API keys with policy settings."""
    org = request.organization
    keys = APIKey.objects.filter(organization=org)
    providers = AIProvider.objects.filter(Q(organization=org) | Q(is_system=True), is_active=True).distinct()
    new_key_value = None

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            name = request.POST.get('name', 'Unnamed Key')
            linked_provider_id = request.POST.get('linked_provider', '')
            linked_provider = None
            if linked_provider_id:
                try:
                    linked_provider = AIProvider.objects.get(id=linked_provider_id, organization=org)
                except AIProvider.DoesNotExist:
                    pass

            key = APIKey.objects.create(
                organization=org,
                user=request.user,
                name=name,
                linked_provider=linked_provider,
                rate_limit=int(request.POST.get('rate_limit', 60)),
                daily_token_limit=int(request.POST.get('daily_token_limit', 0)),
                allowed_models=request.POST.get('allowed_models', ''),
                enable_compression=request.POST.get('enable_compression') == 'on',
                enable_pii_masking=request.POST.get('enable_pii_masking') == 'on',
                enable_caching=request.POST.get('enable_caching') == 'on',
            )
            new_key_value = key.key
            messages.success(request, key.key, extra_tags='new_api_key')
            return render(request, 'dashboard/api_keys.html', {
                'keys': keys,
                'providers': providers,
                'new_key_value': new_key_value,
            })
            
        elif action == 'revoke':
            key_id = request.POST.get('key_id')
            try:
                key = APIKey.objects.get(id=key_id, organization=org)
                key.is_active = False
                key.save()
                messages.success(request, f'API Key "{key.name}" has been revoked.')
            except APIKey.DoesNotExist:
                messages.error(request, 'Key not found.')
        return redirect('dashboard:api_key_list')
        
    return render(request, 'dashboard/api_keys.html', {
        'keys': keys,
        'providers': providers,
        'new_key_value': new_key_value,
    })

import urllib.request
import urllib.error
from django.views.decorators.http import require_POST

@login_required
@require_POST
def api_file_chat(request, file_id):
    """File Chat endpoint — uses document context + AI Provider to chat with data."""
    org = request.organization
    if not org:
        return JsonResponse({'error': 'Organization required'}, status=403)
        
    try:
        file_obj = get_object_or_404(FileAnalysis, id=file_id, organization=org)
        
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        file_ids = data.get('file_ids', [])
        if not user_message:
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)
            
        session_id = data.get('session_id')
        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id, organization=org, user=request.user)
            except ChatSession.DoesNotExist:
                return JsonResponse({'error': 'Chat session not found'}, status=404)
        else:
            session = ChatSession.objects.create(
                organization=org,
                user=request.user,
                title=f"Chat about {file_obj.filename}"[:255]
            )

        # Save user message
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_USER,
            content=user_message
        )
            
        # 4. Grab active AI Provider globally since custom select is removed
        provider = AIProvider.objects.filter(is_system=True, is_active=True).first()
        if not provider:
            provider = AIProvider.objects.filter(organization=org, is_active=True).first()
            
        if not provider:
            return JsonResponse({'error': 'No active AI Provider available.'}, status=400)
            
        if not provider:
            return JsonResponse({'error': 'No valid AI provider configured. Please select one or set a system default.'}, status=400)
            
        wants_full = "translate all" in user_message.lower() or "translate everything" in user_message.lower()
        context_text = ""
        try:
            import os
            import chromadb
            from django.conf import settings
            chroma_dir = os.path.join(settings.MEDIA_ROOT, 'vector_stores', str(file_obj.id))
            client = chromadb.PersistentClient(path=chroma_dir)
            collection = client.get_collection(name=f"file_{file_obj.id}")
            
            if wants_full:
                results = collection.get()
                context_text = "\n\n".join(results['documents']) if results and results['documents'] else ""
            else:
                results = collection.query(query_texts=[user_message], n_results=5)
                context_text = "\n\n".join(results['documents'][0]) if results and results['documents'] else ""
        except Exception as e:
            print(f"ChromaDB retrieval error: {e}")
            
        if not context_text:
            context_text = file_obj.result if file_obj.result else "No text extracted from this file."
            
        system_prompt = "You are a highly efficient Firma-KI NEX compression engine. Answer the user's queries concisely and accurately in strict accordance with the core rules."
        try:
            from django.conf import settings
            import os
            rules_path = os.path.join(settings.BASE_DIR, 'COMPRESSION_RULES.md')
            with open(rules_path, 'r', encoding='utf-8') as f:
                nex_rules = f.read()
            system_prompt += f"\n\nCRITICAL INSTRUCTION: You must strictly output your logic in NEX Bytecode according to the following framework:\n{nex_rules}"
        except Exception as e:
            print(f"Warning: Could not load COMPRESSION_RULES.md: {e}")
            
        system_prompt += f"\n\nUse the following document context to answer the user's queries concisely.\n\nDOCUMENT CONTEXT:\n{context_text}"
        
        # Load previous messages
        messages_history = [
            {'role': 'system', 'content': system_prompt}
        ]
        prev_msgs = session.messages.all()
        for msg in prev_msgs:
            messages_history.append({'role': msg.role, 'content': msg.content})
        
        start_time = time.time()
        if provider.provider_type == 'deepseek':
            req_url = 'https://api.deepseek.com/chat/completions'
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {provider.api_key}'
            }
            payload = {
                'model': provider.model_name or 'deepseek-chat',
                'messages': messages_history,
                'temperature': provider.temperature,
            }
            
            payload['stream'] = True
            
            def stream_response():
                req = urllib.request.Request(req_url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
                ai_text = ""
                tokens_prompt = 0
                tokens_response = 0
                error_occurred = False
                
                translated_text = ""
                trans_tokens_prompt = 0
                trans_tokens_response = 0
                
                try:
                    # --- STAGE 1: NEX BYTECODE GENERATION (Hidden from User) ---
                    try:
                        with urllib.request.urlopen(req, timeout=60) as response:
                            for line in response:
                                line = line.decode('utf-8').strip()
                                if not line or not line.startswith('data: '):
                                    continue
                                data_str = line[6:]
                                if data_str == '[DONE]':
                                    break
                                try:
                                    chunk = json.loads(data_str)
                                    if 'usage' in chunk and chunk['usage']:
                                        tokens_prompt = chunk['usage'].get('prompt_tokens', tokens_prompt)
                                        tokens_response = chunk['usage'].get('completion_tokens', tokens_response)
                                    if chunk.get('choices') and chunk['choices'][0].get('delta', {}).get('content'):
                                        ai_text += chunk['choices'][0]['delta']['content']
                                except json.JSONDecodeError:
                                    pass
                    except Exception as e:
                        error_occurred = True
                        yield f"\n\nSystem Error: Could not connect to {provider.name} (Stage 1). Details: {str(e)}"
                        return
                        
                    # --- STAGE 2: HUMAN DECODER (Streamed to User) ---
                    if not error_occurred and ai_text:
                        decoder_sys = "You are a Human Translator for the Firma-KI proxy. Your goal is to linearly translate the dense, optimized NEX bytecode provided in the user's prompt back into a fluid, professional human response. Do not output any NEX tags."
                        decoder_payload = {
                            'model': provider.model_name or 'deepseek-chat',
                            'messages': [
                                {'role': 'system', 'content': decoder_sys},
                                {'role': 'user', 'content': f"Translate this NEX bytecode to Human:\n{ai_text}"}
                            ],
                            'temperature': provider.temperature,
                            'stream': True
                        }
                        decoder_req = urllib.request.Request(req_url, data=json.dumps(decoder_payload).encode('utf-8'), headers=headers, method='POST')
                        
                        try:
                            with urllib.request.urlopen(decoder_req, timeout=60) as response:
                                for line in response:
                                    line = line.decode('utf-8').strip()
                                    if not line or not line.startswith('data: '):
                                        continue
                                    data_str = line[6:]
                                    if data_str == '[DONE]':
                                        break
                                    try:
                                        chunk = json.loads(data_str)
                                        if 'usage' in chunk and chunk['usage']:
                                            trans_tokens_prompt = chunk['usage'].get('prompt_tokens', trans_tokens_prompt)
                                            trans_tokens_response = chunk['usage'].get('completion_tokens', trans_tokens_response)
                                        if chunk.get('choices') and chunk['choices'][0].get('delta', {}).get('content'):
                                            content_chunk = chunk['choices'][0]['delta']['content']
                                            translated_text += content_chunk
                                            yield content_chunk
                                    except json.JSONDecodeError:
                                        pass
                        except Exception as e:
                            error_occurred = True
                            yield f"\n\nSystem Error: Could not connect to {provider.name} (Stage 2). Details: {str(e)}"
                            return

                finally:
                    if not error_occurred and ai_text:
                        if tokens_prompt == 0:
                            tokens_prompt = sum(len(m['content'].split()) for m in messages_history)
                        if tokens_response == 0:
                            tokens_response = len(ai_text.split())

                        # We store the Stage 2 Translated string for user history, but log the raw NEX
                        ChatMessage.objects.create(
                            session=session,
                            role=ChatMessage.ROLE_AI,
                            content=translated_text
                        )

                        latency_ms = int((time.time() - start_time) * 1000)

                        AuditLog.objects.create(
                            organization=org,
                            user=request.user,
                            ai_provider=provider,
                            source=AuditLog.SOURCE_FILE_CHAT,
                            original_payload=json.dumps({'message': user_message}),
                            compressed_payload=json.dumps({'message': user_message, 'history_length': session.messages.count()}),
                            deepseek_response=ai_text,  # Record the STAGE 1 NEX Bytecode for database analytics
                            final_response=translated_text,  # Record the final Human translation
                            tokens_original=tokens_prompt + trans_tokens_prompt,
                            tokens_compressed=tokens_prompt,
                            tokens_response=tokens_response + trans_tokens_response,
                            latency_ms=latency_ms
                        )

                        savings = max(0, round((tokens_prompt - tokens_prompt) / tokens_prompt * 100)) if tokens_prompt > 0 else 0

                        metrics_data = {
                            'tokens_original': tokens_prompt,
                            'tokens_compressed': tokens_prompt,
                            'savings_percentage': savings,
                            'latency_ms': latency_ms
                        }
                        yield f"__METRICS__{json.dumps(metrics_data)}"

            return StreamingHttpResponse(stream_response(), content_type='text/plain')
        else:
            return JsonResponse({'error': f'Streaming not implemented for {provider.get_provider_type_display()}'}, status=400)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def ai_providers(request):
    """Manage AI providers."""
    org = request.organization
    providers = AIProvider.objects.filter(Q(organization=org) | Q(is_system=True)).distinct()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            AIProvider.objects.create(
                organization=org,
                name=request.POST.get('name', ''),
                provider_type=request.POST.get('provider_type', 'deepseek'),
                api_base_url=request.POST.get('api_base_url', ''),
                api_key=request.POST.get('api_key', ''),
                model_name=request.POST.get('model_name', ''),
                output_webhook_url=request.POST.get('output_webhook_url', ''),
                max_tokens=int(request.POST.get('max_tokens', 4096)),
                temperature=float(request.POST.get('temperature', 0.7)),
                is_default=not providers.filter(is_default=True).exists(),
            )
            messages.success(request, 'AI Provider added.')
        elif action == 'delete':
            pid = request.POST.get('provider_id')
            try:
                p = AIProvider.objects.get(id=pid, organization=org)
                p.delete()
                messages.success(request, f'"{p.name}" removed.')
            except AIProvider.DoesNotExist:
                messages.error(request, 'Provider not found.')
        elif action == 'toggle':
            pid = request.POST.get('provider_id')
            try:
                p = AIProvider.objects.get(id=pid, organization=org)
                p.is_active = not p.is_active
                p.save()
                messages.success(request, f'"{p.name}" {"activated" if p.is_active else "deactivated"}.')
            except AIProvider.DoesNotExist:
                messages.error(request, 'Provider not found.')
        elif action == 'set_default':
            pid = request.POST.get('provider_id')
            try:
                AIProvider.objects.filter(organization=org).update(is_default=False)
                p = AIProvider.objects.get(id=pid, organization=org)
                p.is_default = True
                p.save()
                messages.success(request, f'"{p.name}" set as default provider.')
            except AIProvider.DoesNotExist:
                messages.error(request, 'Provider not found.')
        return redirect('dashboard:ai_providers')

    return render(request, 'dashboard/ai_providers.html', {'providers': providers})


@login_required
def compression_rules(request):
    """View compression rules — built-in + custom."""
    org = request.organization

    # System rules visible to all orgs
    system_rules = CompressionRule.objects.filter(is_system=True)
    custom_rules = CompressionRule.objects.filter(organization=org, is_system=False)

    builtin_lang_rules = system_rules.filter(rule_type=CompressionRule.TYPE_BUILTIN_LANGUAGE)
    builtin_prog_rules = system_rules.filter(rule_type=CompressionRule.TYPE_BUILTIN_PROGRAMMING)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            pattern = request.POST.get('pattern', '')
            replacement = request.POST.get('replacement', '')
            description = request.POST.get('description', '')
            if pattern and replacement:
                CompressionRule.objects.create(
                    organization=org,
                    rule_type=CompressionRule.TYPE_CUSTOM,
                    pattern=pattern,
                    replacement=replacement,
                    description=description,
                )
                messages.success(request, f'Custom rule added: "{pattern}" → "{replacement}"')
        elif action == 'delete':
            rule_id = request.POST.get('rule_id')
            try:
                rule = CompressionRule.objects.get(id=rule_id, organization=org, is_system=False)
                rule.delete()
                messages.success(request, 'Rule deleted.')
            except CompressionRule.DoesNotExist:
                messages.error(request, 'Rule not found or is a system rule.')
        return redirect('dashboard:rules')

    context = {
        'builtin_lang_rules': builtin_lang_rules,
        'builtin_prog_rules': builtin_prog_rules,
        'custom_rules': custom_rules,
        'lang_groups': {
            'de': builtin_lang_rules.filter(language='de'),
            'en': builtin_lang_rules.filter(language='en'),
        },
        'prog_groups': {
            'python': builtin_prog_rules.filter(programming_language='python'),
            'javascript': builtin_prog_rules.filter(programming_language='javascript'),
            'sql': builtin_prog_rules.filter(programming_language='sql'),
        },
    }
    return render(request, 'dashboard/rules.html', context)


@login_required
def privacy_hub(request):
    """GDPR/PII configuration hub."""
    org = request.organization
    config, created = PIIConfig.objects.get_or_create(organization=org)

    if request.method == 'POST':
        config.mask_names = request.POST.get('mask_names') == 'on'
        config.mask_emails = request.POST.get('mask_emails') == 'on'
        config.mask_ibans = request.POST.get('mask_ibans') == 'on'
        config.mask_ips = request.POST.get('mask_ips') == 'on'
        config.mask_phone_numbers = request.POST.get('mask_phone_numbers') == 'on'
        config.mask_custom_ids = request.POST.get('mask_custom_ids') == 'on'
        config.ai_detection_enabled = request.POST.get('ai_detection_enabled') == 'on'
        config.custom_regex_patterns = request.POST.get('custom_regex_patterns', '')
        config.save()
        messages.success(request, 'Privacy settings updated.')
        return redirect('dashboard:privacy')

    return render(request, 'dashboard/privacy.html', {'config': config})


def process_file_rag(file_analysis_obj):
    import os
    import chromadb
    import fitz
    import docx
    from django.conf import settings

    file_path = file_analysis_obj.file.path
    ext = os.path.splitext(file_path)[1].lower()
    text = ""
    try:
        if ext == '.pdf':
            doc = fitz.open(file_path)
            for page in doc:
                text += page.get_text() + "\n"
        elif ext in ['.docx', '.doc']:
            doc = docx.Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"
        else:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
    except Exception as e:
        print(f"Error extracting text: {e}")
    
    text = text.strip()
    if not text:
        text = "No extractable text found."
        
    file_analysis_obj.result = text[:100000]
    
    chroma_dir = os.path.join(settings.MEDIA_ROOT, 'vector_stores', str(file_analysis_obj.id))
    os.makedirs(chroma_dir, exist_ok=True)
    
    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_or_create_collection(name=f"file_{file_analysis_obj.id}")
    
    chunk_size = 1500
    overlap = 200
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += (chunk_size - overlap)
        
    if chunks:
        ids = [f"chunk_{i}" for i in range(len(chunks))]
        metadatas = [{"source": file_analysis_obj.filename, "chunk": i} for i in range(len(chunks))]
        collection.add(documents=chunks, ids=ids, metadatas=metadatas)
        
    file_analysis_obj.status = FileAnalysis.STATUS_DONE
    file_analysis_obj.save()

@login_required
def file_analysis(request):
    """File upload and AI analysis."""
    from .models import Directory
    org = request.organization
    files = FileAnalysis.objects.filter(organization=org).select_related('directory')
    directories = Directory.objects.filter(organization=org)
    providers = AIProvider.objects.filter(Q(organization=org) | Q(is_system=True), is_active=True).distinct()

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create_directory':
            name = request.POST.get('name')
            if name:
                Directory.objects.create(organization=org, user=request.user, name=name)
                messages.success(request, f'Directory "{name}" created.')
                
        elif action == 'upload':
            uploaded_files = request.FILES.getlist('files')
            directory_id = request.POST.get('directory_id')
            prompt = request.POST.get('prompt', 'Analyze this file and provide a summary.')
            
            directory = None
            if directory_id:
                try:
                    directory = Directory.objects.get(id=directory_id, organization=org)
                except Directory.DoesNotExist:
                    pass

            for f in uploaded_files:
                fa_obj = FileAnalysis.objects.create(
                    organization=org,
                    user=request.user,
                    directory=directory,
                    file=f,
                    filename=f.name,
                    file_size=f.size,
                    prompt=prompt,
                    status=FileAnalysis.STATUS_PENDING,
                )
                try:
                    process_file_rag(fa_obj)
                except Exception as e:
                    fa_obj.status = FileAnalysis.STATUS_ERROR
                    fa_obj.error_message = f"RAG Processing Error: {str(e)}"
                    fa_obj.save()

            messages.success(request, f'{len(uploaded_files)} file(s) processed and queued for analysis.')
        elif action == 'delete':
            fid = request.POST.get('file_id')
            try:
                fa = FileAnalysis.objects.get(id=fid, organization=org)
                if fa.file:
                    try:
                        os.remove(fa.file.path)
                    except OSError:
                        pass
                fa.delete()
                messages.success(request, 'File analysis deleted.')
            except FileAnalysis.DoesNotExist:
                messages.error(request, 'File not found.')
        elif action == 'reprocess':
            fid = request.POST.get('file_id')
            try:
                fa = FileAnalysis.objects.get(id=fid, organization=org)
                fa.status = FileAnalysis.STATUS_PENDING
                fa.error_message = ""
                fa.save()
                try:
                    process_file_rag(fa)
                    messages.success(request, f'File "{fa.filename}" successfully reprocessed.')
                except Exception as e:
                    fa.status = FileAnalysis.STATUS_ERROR
                    fa.error_message = f"RAG Processing Error: {str(e)}"
                    fa.save()
                    messages.error(request, f'Failed to reprocess "{fa.filename}".')
            except FileAnalysis.DoesNotExist:
                messages.error(request, 'File not found.')
                
        return redirect('dashboard:file_analysis')

    return render(request, 'dashboard/file_analysis.html', {
        'files': files,
        'directories': directories,
        'providers': providers,
    })


@login_required
@owner_required
def team_management(request):
    """Manage team members and access levels."""
    org = request.organization
    from accounts.models import Invitation

    members = User.objects.filter(organization=org)
    invitations = Invitation.objects.filter(organization=org, accepted=False)

    # Per-member request counts
    member_stats = []
    for member in members:
        req_count = AuditLog.objects.filter(
            api_key__user=member, organization=org
        ).count()
        key_count = APIKey.objects.filter(user=member, organization=org, is_active=True).count()
        member_stats.append({
            'user': member,
            'requests': req_count,
            'active_keys': key_count,
        })

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'change_role':
            user_id = request.POST.get('user_id')
            new_role = request.POST.get('role')
            try:
                user = User.objects.get(id=user_id, organization=org)
                if user != request.user:
                    user.role = new_role
                    user.save()
                    messages.success(request, f'{user.username} role changed to {user.get_role_display()}.')
                else:
                    messages.error(request, 'You cannot change your own role.')
            except User.DoesNotExist:
                messages.error(request, 'User not found.')
        elif action == 'remove_user':
            user_id = request.POST.get('user_id')
            try:
                user = User.objects.get(id=user_id, organization=org)
                if user != request.user:
                    user.is_active = False
                    user.save()
                    messages.success(request, f'{user.username} has been deactivated.')
                else:
                    messages.error(request, 'You cannot remove yourself.')
            except User.DoesNotExist:
                messages.error(request, 'User not found.')
        return redirect('dashboard:team')

    return render(request, 'dashboard/team.html', {
        'member_stats': member_stats,
        'invitations': invitations,
    })


@login_required
def audit_list(request):
    """Audit log table with filtering."""
    org = request.organization
    logs = AuditLog.objects.filter(organization=org)

    status_filter = request.GET.get('status', '')
    if status_filter:
        logs = logs.filter(status=status_filter)

    search = request.GET.get('search', '')
    if search:
        logs = logs.filter(
            Q(original_payload__icontains=search) |
            Q(deepseek_response__icontains=search)
        )

    provider_filter = request.GET.get('provider', '')
    if provider_filter:
        logs = logs.filter(ai_provider_id=provider_filter)

    return render(request, 'dashboard/audit_list.html', {
        'logs': logs[:100],
        'status_filter': status_filter,
        'search': search,
        'provider_filter': provider_filter,
        'providers': AIProvider.objects.filter(Q(organization=org) | Q(is_system=True)).distinct(),
    })


@login_required
def audit_detail(request, log_id):
    """Detailed split-screen view of a single audit log."""
    org = request.organization
    log = get_object_or_404(AuditLog, id=log_id, organization=org)
    return render(request, 'dashboard/audit_detail.html', {'log': log})

@login_required
def secure_chat(request):
    """Standalone Secure Data Chat view."""
    org = request.organization
    files = FileAnalysis.objects.filter(organization=org).order_by('-created_at')
    sessions = ChatSession.objects.filter(
        organization=org, user=request.user
    ).order_by('-updated_at')[:20]

    return render(request, 'dashboard/secure_chat.html', {
        'files': files,
        'chat_sessions': sessions,
    })

@login_required
@require_POST
def api_secure_chat(request):
    """API for the standalone secure chat, allowing multiple file selection."""
    org = request.organization
    if not org:
        return JsonResponse({'error': 'Organization required'}, status=403)
        
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        file_ids = data.get('file_ids', [])
        file_ids = data.get('file_ids', [])
        
        if not user_message:
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)
            
        session_id = data.get('session_id')
        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id, organization=org, user=request.user)
            except ChatSession.DoesNotExist:
                return JsonResponse({'error': 'Chat session not found'}, status=404)
        else:
            session = ChatSession.objects.create(
                organization=org,
                user=request.user,
                title=user_message[:255] if len(user_message) > 0 else "New Chat"
            )

        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_USER,
            content=user_message
        )

        
        # Globally default to active system-level Provider (or Org AI)
        provider = AIProvider.objects.filter(is_system=True, is_active=True).first()
        if not provider:
             provider = AIProvider.objects.filter(organization=org, is_active=True).first()

        if not provider:
            return JsonResponse({'error': 'No active AI Provider configured.'}, status=400)
            
        context_text = ""
        if file_ids:
            files = FileAnalysis.objects.filter(id__in=file_ids, organization=org)
            for f in files:
                context_text += f"\n--- Document: {f.filename} ---\n"
                context_text += f.result if f.result else "No text extracted."

        # Build chat history (user/ai messages only — NO system prompt bloat)
        chat_history = []
        for msg in session.messages.all():
            chat_history.append({'role': msg.role, 'content': msg.content})

        # PII Masking on the user message
        from gateway.compressor import PIIMasker
        masker = PIIMasker()
        masked_message, pii_entities = masker.mask(user_message), []

        start_time = time.time()

        from gateway.nex_pipeline import compress_to_nex, call_logic_provider_blocking, stream_translate_from_nex

        def stream_response():
            error_occurred = False
            nex_input = ""
            nex_output = ""
            translated_text = ""
            tokens_s1_prompt = 0
            tokens_s1_resp = 0
            tokens_s2_prompt = 0
            tokens_s2_resp = 0

            try:
                # ---------------------------------------------------------------
                # STAGE 1: Convert full context + history + query → Logic Mission
                # ---------------------------------------------------------------
                try:
                    # Count total input tokens: user message + context + all history
                    history_word_count = sum(len(m['content'].split()) for m in chat_history)
                    tokens_s1_prompt = len(user_message.split()) + len(context_text.split()) + history_word_count
                    nex_input = compress_to_nex(user_message, context_text=context_text, messages_history=chat_history)
                    tokens_s1_resp = len(nex_input.split())
                except Exception as e:
                    print(f'[Stage 1 error] {e}')
                    nex_input = user_message  # degrade gracefully
                    tokens_s1_resp = len(nex_input.split())

                # ---------------------------------------------------------------
                # STAGE 2: Core AI Logic (configured provider)
                # ---------------------------------------------------------------
                # Stage 2 now receives the ABSOLUTE MINIMUM: just the Logic Mission
                s2_system = "You are a pure logic engine. Solve the prompt concisely in minimal tokens. Do not format or explain."
                s2_messages = [
                    {'role': 'system', 'content': s2_system},
                    {'role': 'user', 'content': nex_input}
                ]
                
                try:
                    nex_output, tokens_s2_prompt, tokens_s2_resp = call_logic_provider_blocking(provider, s2_messages)
                    if not nex_output:
                        error_occurred = True
                        yield f"\n\nSystem Error: No response from {provider.name} (Stage 2)."
                        return
                except Exception as e:
                    error_occurred = True
                    yield f"\n\nSystem Error: {provider.name} (Stage 2) failed: {str(e)}"
                    return

                # ---------------------------------------------------------------
                # STAGE 3: Translate NEX response → Human text (DeepSeek, streamed)
                # ---------------------------------------------------------------
                try:
                    for chunk in stream_translate_from_nex(nex_output):
                        unmasked = masker.unmask(chunk)
                        translated_text += unmasked
                        yield unmasked
                except Exception as e:
                    error_occurred = True
                    yield f"\n\nSystem Error: Translation (Stage 3) failed: {str(e)}"
                    return

            finally:
                if not error_occurred and nex_output:
                    # Save the human-readable AI reply to chat history
                    ChatMessage.objects.create(
                        session=session,
                        role=ChatMessage.ROLE_AI,
                        content=translated_text or masker.unmask(nex_output)
                    )

                    latency_ms = int((time.time() - start_time) * 1000)

                    AuditLog.objects.create(
                        organization=org,
                        user=request.user,
                        ai_provider=provider,
                        source=AuditLog.SOURCE_SECURE_CHAT,
                        original_payload=json.dumps({
                            'message': user_message,
                            'file_ids': file_ids,
                            'pii_entities_masked': len(pii_entities)
                        }),
                        compressed_payload=nex_input,          # Stage 1 output (NEX)
                        deepseek_response=nex_output,           # Stage 2 output (NEX)
                        final_response=translated_text,         # Stage 3 output (Human)
                        tokens_original=tokens_s1_prompt,
                        tokens_compressed=tokens_s1_resp,
                        tokens_response=tokens_s2_resp,
                        tokens_translated=len(translated_text.split()),
                        latency_ms=latency_ms
                    )

                    # --- Cost Efficiency Calculation vs Claude Opus ---
                    # Claude Opus Baseline: €15 / 1M In, €75 / 1M Out
                    cost_opus = (log.tokens_original / 1_000_000) * 15.0 + (log.tokens_translated / 1_000_000) * 75.0
                    
                    # NEX 3-Stage Pipeline Actual Cost (DeepSeek proxy: €0.14 In / €0.28 Out)
                    total_pipeline_in = log.tokens_original + log.tokens_compressed + log.tokens_response
                    total_pipeline_out = log.tokens_compressed + log.tokens_response + log.tokens_translated
                    cost_actual = (total_pipeline_in / 1_000_000) * 0.14 + (total_pipeline_out / 1_000_000) * 0.28

                    log.cost_original = cost_opus
                    log.cost_actual = cost_actual
                    log.cost_saved = max(0, cost_opus - cost_actual)
                    
                    if cost_opus > 0:
                        log.compression_ratio = round((log.cost_saved / cost_opus) * 100, 1) # Repurposing field for Cost Savings %
                    
                    log.save()

                    tokens_s3_resp = len(translated_text.split())

                    metrics_data = {
                        'tokens_original': tokens_s1_prompt,
                        'tokens_compressed': tokens_s1_resp,
                        'output_tokens_original': tokens_s3_resp,
                        'output_tokens_compressed': tokens_s2_resp,
                        'cost_opus_eur': float(cost_opus),
                        'cost_saved_eur': float(log.cost_saved),
                        'financial_efficiency_pct': log.compression_ratio,
                        'latency_ms': latency_ms
                    }
                    yield f"__METRICS__{json.dumps(metrics_data)}"

        return StreamingHttpResponse(stream_response(), content_type='text/plain')

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)



@login_required
def api_chat_history(request):
    """Retrieve chat sessions or messages for a session."""
    org = request.organization
    session_id = request.GET.get('session_id')
    
    if session_id:
        try:
            session = ChatSession.objects.get(id=session_id, organization=org, user=request.user)
            messages = session.messages.all()
            return JsonResponse({
                'session_id': str(session.id),
                'title': session.title,
                'messages': [{'id': str(m.id), 'role': m.role, 'content': m.content} for m in messages]
            })
        except ChatSession.DoesNotExist:
            return JsonResponse({'error': 'Session not found'}, status=404)
    else:
        sessions = ChatSession.objects.filter(organization=org, user=request.user)
        return JsonResponse({
            'sessions': [{'id': str(s.id), 'title': s.title, 'updated_at': s.updated_at.isoformat()} for s in sessions]
        })

@login_required
@require_POST
def api_chat_delete(request):
    """Delete a chat session."""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        session = ChatSession.objects.get(id=session_id, organization=request.organization, user=request.user)
        session.delete()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_POST
def api_chat_update(request):
    """Update a previous message, delete subsequent messages, and return the new response."""
    # It acts identically to api_secure_chat but alters the session history first
    org = request.organization
    try:
        data = json.loads(request.body)
        message_id = data.get('message_id')
        new_content = data.get('content', '').strip()
        file_ids = data.get('file_ids', [])
        
        if not new_content:
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)
            
        msg = ChatMessage.objects.get(id=message_id, session__organization=org, session__user=request.user)
        session = msg.session
        
        # Delete old AI responses after this
        session.messages.filter(created_at__gt=msg.created_at).delete()
        
        # Update user message
        msg.content = new_content
        msg.save()
        
        provider = AIProvider.objects.filter(is_system=True, is_active=True).first()
        if not provider:
            return JsonResponse({'error': 'System AI provider not configured.'}, status=400)
            
        context_text = ""
        if file_ids:
            files = FileAnalysis.objects.filter(id__in=file_ids, organization=org)
            for f in files:
                context_text += f"\n--- Document: {f.filename} ---\n"
                context_text += f.result if f.result else "No text extracted."

        # Build chat history (user/ai messages only — NO system prompt bloat)
        chat_history = []
        for m in session.messages.all():
            chat_history.append({'role': m.role, 'content': m.content})

        from gateway.compressor import PIIMasker
        from gateway.nex_pipeline import compress_to_nex, call_logic_provider_blocking, translate_from_nex_blocking

        start_time = time.time()
        masker = PIIMasker()

        # ---------------------------------------------------------------
        # STAGE 1: Convert full context + history + query → Logic Mission
        # ---------------------------------------------------------------
        history_word_count = sum(len(m['content'].split()) for m in chat_history)
        tok_orig = len(new_content.split()) + len(context_text.split()) + history_word_count
        nex_input = compress_to_nex(new_content, context_text=context_text, messages_history=chat_history)
        tok_comp = len(nex_input.split())

        # ---------------------------------------------------------------
        # STAGE 2: Core AI logic on NEX input (configured provider)
        # ---------------------------------------------------------------
        s2_system = "You are a pure logic engine. Solve the prompt concisely in minimal tokens. Do not format or explain."
        s2_messages = [
            {'role': 'system', 'content': s2_system},
            {'role': 'user', 'content': nex_input}
        ]
        nex_output, tokens_s2_prompt, tokens_s2_resp = call_logic_provider_blocking(provider, s2_messages)
        if not nex_output:
            nex_output = "(No response from provider)"

        # ---------------------------------------------------------------
        # STAGE 3: Translate NEX response → Human text (DeepSeek, blocking)
        # ---------------------------------------------------------------
        final_ai_text = translate_from_nex_blocking(nex_output)
        final_ai_text = masker.unmask(final_ai_text)

        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_AI,
            content=final_ai_text
        )

        latency_ms = int((time.time() - start_time) * 1000)

        total_pipeline_in = tok_orig + tok_comp + tokens_s2_resp
        total_pipeline_out = tok_comp + tokens_s2_resp + len(final_ai_text.split())
        
        cost_opus = (tok_orig / 1_000_000) * 15.0 + (len(final_ai_text.split()) / 1_000_000) * 75.0
        cost_actual = (total_pipeline_in / 1_000_000) * 0.14 + (total_pipeline_out / 1_000_000) * 0.28
        
        cost_saved = max(0, cost_opus - cost_actual)
        compression_ratio = 0
        if cost_opus > 0:
            compression_ratio = round((cost_saved / cost_opus) * 100, 1)

        AuditLog.objects.create(
            organization=org,
            user=request.user,
            ai_provider=provider,
            source=AuditLog.SOURCE_SECURE_CHAT,
            original_payload=json.dumps({'message': new_content, 'file_ids': file_ids}),
            compressed_payload=nex_input,
            deepseek_response=nex_output,
            final_response=final_ai_text,
            tokens_original=tok_orig,
            tokens_compressed=tok_comp,
            tokens_response=tokens_s2_resp,
            tokens_translated=len(final_ai_text.split()),
            cost_original=cost_opus,
            cost_actual=cost_actual,
            cost_saved=cost_saved,
            compression_ratio=compression_ratio,
            latency_ms=latency_ms
        )

        tokens_s3_resp = len(final_ai_text.split())

        return JsonResponse({
            'response': final_ai_text,
            'session_id': str(session.id),
            'metrics': {
                'tokens_original': tok_orig,
                'tokens_compressed': tok_comp,
                'output_tokens_original': tokens_s3_resp,
                'output_tokens_compressed': tokens_s2_resp,
                'cost_opus_eur': float(cost_opus),
                'cost_saved_eur': float(cost_saved),
                'financial_efficiency_pct': compression_ratio,
                'latency_ms': latency_ms
            }
        })

    except ChatMessage.DoesNotExist:
        return JsonResponse({'error': 'Message not found or forbidden'}, status=403)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def playground(request):
    """Real-time data compression and safety testing Playground."""
    org = request.organization
    if not org:
        messages.error(request, 'No organization found. Please register first.')
        return redirect('landing')
        
    # Get active API keys for the user to select from
    api_keys = APIKey.objects.filter(user=request.user, organization=org, is_active=True).order_by('-created_at')
        
    return render(request, 'dashboard/playground.html', {
        'api_keys': api_keys,
    })
        
@login_required
def security_audit(request):
    """
    Security & GDPR configuration page.
    Shows exactly what data was removed/modified by the gateway for each API key.
    Includes toggles for compression and PII making defaults per key.
    """
    org = request.organization
    if not org:
        messages.error(request, 'No organization found. Please register first.')
        return redirect('landing')

    # Handle POST updates to API Key Configuration
    if request.method == 'POST':
        action = request.POST.get('action')
        key_id = request.POST.get('key_id')
        
        if action == 'update_security_config' and key_id:
            try:
                api_key = APIKey.objects.get(id=key_id, organization=org)
                # Checkboxes: "on" if checked, otherwise missing
                api_key.enable_pii_masking = request.POST.get('enable_pii_masking') == 'on'
                api_key.enable_compression = request.POST.get('enable_compression') == 'on'
                api_key.save()
                messages.success(request, f'Security configuration updated for key: {api_key.name}')
            except APIKey.DoesNotExist:
                messages.error(request, 'API Key not found.')
        
        return redirect('dashboard:security_audit')

    api_keys = APIKey.objects.filter(organization=org).order_by('-created_at')
    recent_logs = AuditLog.objects.filter(organization=org, status=AuditLog.STATUS_SUCCESS).order_by('-timestamp')[:50]
    
    # Pre-process logs to extract modified data metrics
    processed_logs = []
    
    import re
    pii_pattern = re.compile(r'\[(PERSON|EMAIL|PHONE|CREDIT_CARD|LOC|ORG|DATE)_[0-9]+\]')
    
    for log in recent_logs:
        # Extract the redacted tags that were created by the gateway via regex matches on compressed_payload
        stripped_tags = list(set(pii_pattern.findall(log.compressed_payload))) if log.compressed_payload else []
        
        # Determine the source app (Gateway or File Chat / Secure Chat)
        source_label = dict(AuditLog.SOURCE_CHOICES).get(log.source, log.source)
        
        log_data = {
            'id': log.id,
            'timestamp': log.timestamp,
            'source_label': source_label,
            'api_key_name': log.api_key.name if log.api_key else 'Unknown Key',
            'api_key_masked': log.api_key.masked_key if log.api_key else 'N/A',
            'stripped_tags': stripped_tags,
            'tokens_saved': log.tokens_original - log.tokens_compressed,
        }
        processed_logs.append(log_data)


    return render(request, 'dashboard/security_audit.html', {
        'api_keys': api_keys,
        'logs': processed_logs,
    })


@login_required
def masked_documents_list(request):
    """View to list and upload Masked Documents (Clean Files)."""
    org = request.organization
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'upload':
            uploaded_files = request.FILES.getlist('files')
            pii_config, _ = PIIConfig.objects.get_or_create(organization=org)
            masker = PIIMasker(pii_config)

            for f in uploaded_files:
                text = ""
                ext = os.path.splitext(f.name)[1].lower()
                try:
                    if ext == '.pdf':
                        doc = fitz.open(stream=f.read(), filetype="pdf")
                        for page in doc:
                            text += page.get_text() + "\n"
                    elif ext in ['.docx', '.doc']:
                        import docx
                        import io
                        doc = docx.Document(io.BytesIO(f.read()))
                        for para in doc.paragraphs:
                            text += para.text + "\n"
                    elif ext == '.json':
                        content = f.read().decode('utf-8', errors='ignore')
                        text = content
                    else:
                        text = f.read().decode('utf-8', errors='ignore')
                except Exception as e:
                    messages.error(request, f"Error reading {f.name}: {e}")
                    continue

                if not text.strip():
                    messages.error(request, f"No text could be extracted from {f.name}.")
                    continue

                # Mask text
                masked_text, mask_map = masker.mask(text)

                # Save document
                mdoc = MaskedDocument.objects.create(
                    organization=org,
                    user=request.user,
                    filename=f.name,
                    file_size=f.size,
                    clean_content=masked_text
                )

                # Save mappings
                mappings_to_create = []
                for placeholder, original in mask_map.items():
                    # extract PII type from placeholder, e.g. [EMAIL_1] -> EMAIL
                    pii_type = placeholder.strip('[]').split('_')[0]
                    mappings_to_create.append(
                        DocumentKeyMapping(
                            document=mdoc,
                            placeholder=placeholder,
                            original_value=original,
                            pii_type=pii_type
                        )
                    )
                DocumentKeyMapping.objects.bulk_create(mappings_to_create)

                if ext == '.pdf' and 'doc' in locals() and mask_map:
                    try:
                        for page in doc:
                            for placeholder, original in mask_map.items():
                                instances = page.search_for(original)
                                for inst in instances:
                                    page.add_redact_annot(inst, text=placeholder, fill=(0,0,0), text_color=(1,1,1))
                            page.apply_redactions()
                        
                        pdf_bytes = doc.write()
                        from django.core.files.base import ContentFile
                        mdoc.redacted_file.save(f"redacted_{f.name}", ContentFile(pdf_bytes))
                        doc.close()
                    except Exception as e:
                        messages.warning(request, f"Could not visually redact PDF {f.name}: {e}")

            messages.success(request, f'Successfully processed {len(uploaded_files)} file(s).')
        elif action == 'delete':
            doc_id = request.POST.get('document_id')
            try:
                mdoc = MaskedDocument.objects.get(id=doc_id, organization=org)
                mdoc.delete()
                messages.success(request, 'Clean file deleted.')
            except MaskedDocument.DoesNotExist:
                messages.error(request, 'File not found.')
        return redirect('dashboard:masked_documents_list')

    documents = MaskedDocument.objects.filter(organization=org)
    return render(request, 'dashboard/masked_documents_list.html', {
        'documents': documents,
    })

@login_required
def masked_document_chat(request, doc_id):
    """Interface to chat with a particular MaskedDocument."""
    org = request.organization
    document = get_object_or_404(MaskedDocument, id=doc_id, organization=org)
    
    return render(request, 'dashboard/masked_document_chat.html', {
        'document': document,
    })

from django.views.decorators.http import require_POST

@login_required
@require_POST
def api_masked_document_chat(request, doc_id):
    """Endpoint for chatting over a MaskedDocument with placeholders decoded on the fly."""
    org = request.organization
    try:
        document = get_object_or_404(MaskedDocument, id=doc_id, organization=org)
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        if not user_message:
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)
            
        provider = AIProvider.objects.filter(is_system=True, is_active=True).first()
        if not provider:
            provider = AIProvider.objects.filter(organization=org, is_active=True).first()
        if not provider:
            return JsonResponse({'error': 'No active AI Provider available.'}, status=400)
            
        context_text = document.clean_content[:100000]
        
        system_prompt = (
            "You are an AI assistant answering questions about a document. "
            "The document has been PII-masked, meaning sensitive values are replaced with placeholders like [NAME_1], [EMAIL_1], etc. "
            "Please use these placeholders when referring to the sensitive data. "
            f"\n\nDOCUMENT CONTEXT (Masked):\n{context_text}"
        )
        
        # In a real scenario we'd query past messages via a session, simplify for now:
        messages_history = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message}
        ]
        
        req_url = provider.api_base_url
        if not req_url:
            req_url = 'https://api.openai.com/v1/chat/completions' if provider.provider_type == 'openai' else 'https://api.deepseek.com/chat/completions'
        
        if not provider.api_key:
             return JsonResponse({'error': 'AI provider requires an API key.'}, status=400)
            
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {provider.api_key}'
        }
        payload = {
            'model': provider.model_name or 'deepseek-chat',
            'messages': messages_history,
            'temperature': provider.temperature,
            'stream': True
        }
        
        def stream_response():
            import urllib.request
            req = urllib.request.Request(req_url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
            try:
                mappings = {m.placeholder: m.original_value for m in document.key_mappings.all()}
                
                buffer_text = ""
                with urllib.request.urlopen(req, timeout=60) as response:
                    for line in response:
                        line = line.decode('utf-8').strip()
                        if not line or not line.startswith('data: '):
                            continue
                        data_str = line[6:]
                        if data_str == '[DONE]':
                            if buffer_text:
                                for p, o in mappings.items():
                                    buffer_text = buffer_text.replace(p, o)
                                yield buffer_text
                            break
                        try:
                            chunk = json.loads(data_str)
                            if chunk.get('choices') and chunk['choices'][0].get('delta', {}).get('content'):
                                content_chunk = chunk['choices'][0]['delta']['content']
                                buffer_text += content_chunk
                                
                                # If potential placeholder is unclosed, wait to flush
                                if '[' in buffer_text and ']' not in buffer_text[buffer_text.rfind('['):]:
                                    continue
                                    
                                # fully formed so replace
                                for p, o in mappings.items():
                                    if p in buffer_text:
                                        buffer_text = buffer_text.replace(p, o)
                                    
                                if len(buffer_text) > 50 and '[' not in buffer_text:
                                    yield buffer_text
                                    buffer_text = ""
                                elif len(buffer_text) > 200:
                                    last_open = buffer_text.rfind('[')
                                    if last_open == -1:
                                        last_open = len(buffer_text)
                                    yield buffer_text[:last_open]
                                    buffer_text = buffer_text[last_open:]
                                    
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                yield f"\n\nSystem Error: {str(e)}"
                
        return StreamingHttpResponse(stream_response(), content_type='text/plain')
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

from django.http import HttpResponse

@login_required
def masked_document_preview_text(request, doc_id):
    """View the raw clean text in the dashboard."""
    org = request.organization
    mdoc = get_object_or_404(MaskedDocument, id=doc_id, organization=org)
    return render(request, 'dashboard/masked_document_preview.html', {'document': mdoc})

@login_required
def masked_document_preview_pdf(request, doc_id):
    """View the redacted PDF in the browser."""
    org = request.organization
    mdoc = get_object_or_404(MaskedDocument, id=doc_id, organization=org)
    if not mdoc.redacted_file:
        return HttpResponse('No redacted PDF available for this document.', status=404)
    from django.http import FileResponse
    response = FileResponse(mdoc.redacted_file.open('rb'), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="redacted_{mdoc.filename}"'
    return response

@login_required
def masked_document_download_text(request, doc_id):
    """Download the specific masked document as a text file."""
    org = request.organization
    mdoc = get_object_or_404(MaskedDocument, id=doc_id, organization=org)
    response = HttpResponse(mdoc.clean_content, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="clean_{mdoc.filename}.txt"'
    return response

@login_required
def masked_document_download_pdf(request, doc_id):
    """Download the redacted PDF file."""
    org = request.organization
    mdoc = get_object_or_404(MaskedDocument, id=doc_id, organization=org)
    if not mdoc.redacted_file:
        return HttpResponse('No redacted PDF available for this document.', status=404)
    from django.http import FileResponse
    response = FileResponse(mdoc.redacted_file.open('rb'), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="redacted_{mdoc.filename}"'
    return response
