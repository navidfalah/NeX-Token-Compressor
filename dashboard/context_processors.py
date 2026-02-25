"""
Firma-KI Dashboard — Context Processors
Injects live NEX cost-savings statistics into every dashboard template.
"""
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Count, Avg


def nex_stats(request):
    """
    Injects live NEX compression cost-savings statistics into every template.
    Gracefully returns zeros if the user is not authenticated or has no org.
    """
    context = {
        'nex_total_saved_eur': 0.0,
        'nex_compression_pct': 0,
        'nex_requests_today': 0,
        'nex_tokens_saved_today': 0,
        'nex_avg_latency_ms': 0,
        'nex_mid_input_today': 0,
        'nex_mid_output_today': 0,
    }

    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return context

    org = getattr(request, 'organization', None)
    if not org:
        return context

    try:
        from dashboard.models import AuditLog

        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_logs = AuditLog.objects.filter(organization=org, timestamp__gte=today_start)

        today_agg = today_logs.aggregate(
            total=Count('id'),
            tokens_original=Sum('tokens_original'),
            tokens_compressed=Sum('tokens_compressed'),
            tokens_response=Sum('tokens_response'),
            tokens_translated=Sum('tokens_translated'),
            avg_latency=Avg('latency_ms'),
        )

        total_orig_in = float(today_agg['tokens_original'] or 0)
        total_comp_in = float(today_agg['tokens_compressed'] or 0)
        total_comp_out = float(today_agg['tokens_response'] or 0)
        total_human_out = float(today_agg['tokens_translated'] or 0)
        
        cost_opus = (total_orig_in / 1_000_000) * 15.0 + (total_human_out / 1_000_000) * 75.0
        
        total_pipeline_in = total_orig_in + total_comp_in + total_comp_out
        total_pipeline_out = total_comp_in + total_comp_out + total_human_out
        
        cost_actual = (total_pipeline_in / 1_000_000) * 0.14 + (total_pipeline_out / 1_000_000) * 0.28
        
        cost_saved = max(0, cost_opus - cost_actual)

        # Calculate efficiency % (Money based)
        efficiency_pct = 0
        if cost_opus > 0:
            efficiency_pct = round((cost_saved / cost_opus) * 100, 1)

        context.update({
            'nex_total_saved_eur': round(cost_saved, 4),
            'nex_efficiency_pct': efficiency_pct,
            'nex_requests_today': today_agg['total'] or 0,
            'nex_avg_latency_ms': int(today_agg['avg_latency'] or 0),
            'nex_mid_input_today': total_comp,
            'nex_mid_output_today': today_agg['tokens_response'] or 0,
        })

    except Exception:
        # Never break template rendering for stats
        pass

    return context
