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

from .models import APIKey, AIProvider, CompressionRule, AuditLog

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
    Security & Policy configuration page.
    Shows logs and metrics for compression operations.
    Includes toggles for compression per key.
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

    for log in recent_logs:
        source_label = dict(AuditLog.SOURCE_CHOICES).get(log.source, log.source)
        
        log_data = {
            'id': log.id,
            'timestamp': log.timestamp,
            'source_label': source_label,
            'api_key_name': log.api_key.name if log.api_key else 'Unknown Key',
            'api_key_masked': log.api_key.masked_key if log.api_key else 'N/A',
            'tokens_saved': log.tokens_original - log.tokens_compressed,
        }
        processed_logs.append(log_data)

    return render(request, 'dashboard/security_audit.html', {
        'api_keys': api_keys,
        'logs': processed_logs,
    })

@login_required
def mcp_tools(request):
    """View to manage MCP Tools."""
    org = request.organization
    if not org:
        messages.error(request, 'No organization found. Please register first.')
        return redirect('landing')
    return render(request, 'dashboard/mcp_tools.html', {})

@login_required
def edge_nodes(request):
    """View to manage Edge Nodes."""
    org = request.organization
    if not org:
        messages.error(request, 'No organization found. Please register first.')
        return redirect('landing')
    return render(request, 'dashboard/edge_nodes.html', {})
