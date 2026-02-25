"""
Firma-KI Dashboard — Custom Template Tags & Filters
"""
from django import template
from django.utils import timezone
from datetime import timedelta

register = template.Library()


@register.filter
def format_tokens(value):
    """Format token count with K/M suffix."""
    try:
        value = int(value)
    except (ValueError, TypeError):
        return '0'
    if value >= 1_000_000:
        return f'{value / 1_000_000:.1f}M'
    elif value >= 1_000:
        return f'{value / 1_000:.1f}K'
    return str(value)


@register.filter
def format_cost(value):
    """Format cost in Euros."""
    try:
        value = float(value)
    except (ValueError, TypeError):
        return '€0.00'
    if value >= 1:
        return f'€{value:.2f}'
    elif value >= 0.01:
        return f'€{value:.3f}'
    elif value > 0:
        return f'€{value:.4f}'
    return '€0.00'


@register.filter
def format_percentage(value):
    """Format as percentage."""
    try:
        return f'{float(value):.1f}%'
    except (ValueError, TypeError):
        return '0%'


@register.filter
def format_latency(value):
    """Format latency in ms."""
    try:
        value = int(value)
    except (ValueError, TypeError):
        return '0ms'
    if value >= 1000:
        return f'{value / 1000:.1f}s'
    return f'{value}ms'


@register.filter
def format_bytes(value):
    """Format bytes to KB/MB/GB."""
    try:
        value = int(value)
    except (ValueError, TypeError):
        return '0 B'
    if value >= 1_000_000_000:
        return f'{value / 1_000_000_000:.1f} GB'
    elif value >= 1_000_000:
        return f'{value / 1_000_000:.1f} MB'
    elif value >= 1_000:
        return f'{value / 1_000:.1f} KB'
    return f'{value} B'


@register.filter
def truncate_json(value, length=100):
    """Truncate a JSON string for preview."""
    if not value:
        return ''
    text = str(value)
    if len(text) > length:
        return text[:length] + '...'
    return text


@register.filter
def timesince_short(value):
    """Short human-readable time-since: '2m ago', '3h ago', '5d ago'."""
    if not value:
        return ''
    try:
        now = timezone.now()
        diff = now - value
        seconds = int(diff.total_seconds())

        if seconds < 0:
            return 'just now'
        elif seconds < 60:
            return f'{seconds}s ago'
        elif seconds < 3600:
            return f'{seconds // 60}m ago'
        elif seconds < 86400:
            return f'{seconds // 3600}h ago'
        elif seconds < 604800:
            return f'{seconds // 86400}d ago'
        elif seconds < 2592000:
            return f'{seconds // 604800}w ago'
        else:
            return value.strftime('%b %d')
    except Exception:
        return str(value)


@register.filter
def file_icon(filename):
    """Return an icon class based on file extension."""
    if not filename:
        return 'file'
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    icons = {
        'pdf': '📄', 'doc': '📝', 'docx': '📝', 'txt': '📄',
        'csv': '📊', 'xlsx': '📊', 'xls': '📊',
        'png': '🖼️', 'jpg': '🖼️', 'jpeg': '🖼️', 'gif': '🖼️',
        'py': '🐍', 'js': '⚡', 'html': '🌐', 'css': '🎨',
        'json': '📋', 'xml': '📋', 'yaml': '📋', 'yml': '📋',
        'zip': '📦', 'tar': '📦', 'gz': '📦',
    }
    return icons.get(ext, '📄')
