from fastapi.templating import Jinja2Templates
import humanize
from datetime import datetime

templates = Jinja2Templates(directory="templates")

# Globals
templates.env.globals['csrf_token'] = lambda: ""

# Filters
def format_bytes(n):
    try:
        return humanize.naturalsize(int(n))
    except (ValueError, TypeError):
        return "0 B"

def timesince_filter(dt):
    if not dt: return ""
    now = datetime.utcnow()
    if dt.tzinfo:
        dt = dt.replace(tzinfo=None)
    return humanize.naturaltime(now - dt).replace(" ago", "")

def timesince_short(dt):
    if not dt: return ""
    now = datetime.utcnow()
    if dt.tzinfo: dt = dt.replace(tzinfo=None)
    diff = now - dt
    if diff.days > 0:
        return f"{diff.days}d"
    if diff.seconds >= 3600:
        return f"{diff.seconds // 3600}h"
    if diff.seconds >= 60:
        return f"{diff.seconds // 60}m"
    return f"{diff.seconds}s"

def file_icon(filename):
    if not filename: return "📄"
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    icons = {
        'pdf': '📕',
        'docx': '📘',
        'doc': '📘',
        'txt': '📄',
        'py': '🐍',
        'js': '📜',
        'html': '🌐',
        'css': '🎨',
        'csv': '📊',
        'xlsx': '📊',
        'zip': '📦',
        'json': '⚙️'
    }
    return icons.get(ext, '📄')

def format_tokens(n):
    try:
        n = int(n)
        if n >= 1000000:
            return f"{n/1000000:.1f}M"
        if n >= 1000:
            return f"{n/1000:.1f}K"
        return str(n)
    except (ValueError, TypeError):
        return "0"

def format_latency(ms):
    try:
        ms = float(ms)
        if ms >= 1000:
            return f"{ms/1000:.2f}s"
        return f"{int(ms)}ms"
    except (ValueError, TypeError):
        return "0ms"

def format_cost(val):
    try:
        return f"{float(val):.4f}"
    except (ValueError, TypeError):
        return "0.00"

def strftime_filter(dt, format="%b %d, %Y"):
    if not dt: return ""
    return dt.strftime(format)

templates.env.filters["format_bytes"] = format_bytes
templates.env.filters["timesince"] = timesince_filter
templates.env.filters["timesince_short"] = timesince_short
templates.env.filters["file_icon"] = file_icon
templates.env.filters["format_tokens"] = format_tokens
templates.env.filters["format_latency"] = format_latency
templates.env.filters["format_cost"] = format_cost
templates.env.filters["strftime"] = strftime_filter
