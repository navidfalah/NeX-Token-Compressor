from datetime import datetime, timedelta
import json
import humanize
from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc

from api.dependencies import get_db
from models.accounts import User
from models.dashboard import APIKey, CompressionRule, AIProvider, AuditLog, SecureDocument, KeyMapping, PrivacyConfig
from core.security import decode_access_token

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
templates = Jinja2Templates(directory="templates")

# Custom Jinja Filters
def format_bytes(n):
    try:
        return humanize.naturalsize(int(n))
    except (ValueError, TypeError):
        return "0 B"

def timesince_filter(dt):
    if not dt: return ""
    now = datetime.utcnow()
    # Ensure dt is naive if now is naive
    if dt.tzinfo:
        dt = dt.replace(tzinfo=None)
    return humanize.naturaltime(now - dt).replace(" ago", "")

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

templates.env.filters["format_bytes"] = format_bytes
templates.env.filters["timesince"] = timesince_filter
templates.env.filters["file_icon"] = file_icon

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

templates.env.filters["format_tokens"] = format_tokens
templates.env.filters["format_latency"] = format_latency
templates.env.filters["format_cost"] = format_cost

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

templates.env.filters["timesince_short"] = timesince_short

def strftime_filter(dt, format="%b %d, %Y"):
    if not dt: return ""
    return dt.strftime(format)

templates.env.filters["strftime"] = strftime_filter


# Real authentication dependency for dashboard views
async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token or not token.startswith("Bearer "):
        return None
    
    token = token[7:]
    payload = decode_access_token(token)
    if not payload:
        return None
    
    username = payload.get("sub")
    if not username:
        return None
    
    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    return user

def login_required(user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"}
        )
    return user

@router.get("/", response_class=HTMLResponse, name="dashboard_home")
async def dashboard_home(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)
        
    # Stats for 7 days
    days = int(request.query_params.get("days", 7))
    start_date = datetime.utcnow() - timedelta(days=days)

    # 1. Total requests
    stmt_req = select(func.count(AuditLog.id)).where(AuditLog.organization_id == current_user.organization_id)
    res_req = await db.execute(stmt_req)
    total_requests = res_req.scalar() or 0
    
    # 2. Total tokens saved & compression
    stmt_tokens = select(
        func.sum(AuditLog.tokens_original).label("orig"),
        func.sum(AuditLog.tokens_compressed).label("comp"),
        func.sum(AuditLog.tokens_response).label("resp"),
        func.sum(AuditLog.cost_saved).label("saved")
    ).where(AuditLog.organization_id == current_user.organization_id)
    res_tokens = await db.execute(stmt_tokens)
    ts = res_tokens.one_or_none()
    
    tokens_original = (ts.orig if ts else 0) or 0
    tokens_compressed = (ts.comp if ts else 0) or 0
    tokens_response = (ts.resp if ts else 0) or 0
    cost_saved = (ts.saved if ts else 0) or 0
    
    # 3. Recent logs
    stmt_logs = select(AuditLog).where(AuditLog.organization_id == current_user.organization_id).order_by(desc(AuditLog.timestamp)).limit(10)
    res_logs = await db.execute(stmt_logs)
    recent_logs = res_logs.scalars().all()
    
    # Aggregates for charts (Simplified for now)
    daily_stats = []
    for i in range(days):
        dt = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_stats.insert(0, {"date": dt, "tokens_original": 0, "tokens_compressed": 0})
        
    provider_stats = []
    stmt_prov = select(AIProvider.name, func.count(AuditLog.id)).join(AuditLog, AIProvider.id == AuditLog.ai_provider_id).where(AuditLog.organization_id == current_user.organization_id, AuditLog.timestamp >= start_date).group_by(AIProvider.name)
    res_prov = await db.execute(stmt_prov)
    for name, count in res_prov.all():
        provider_stats.append({"name": name, "requests": count})

    # 4. User Usage Insights (BI)
    user_usage = []
    stmt_user = select(User.username, func.sum(AuditLog.tokens_original).label("tokens")).join(AuditLog, User.id == AuditLog.user_id).where(AuditLog.organization_id == current_user.organization_id, AuditLog.timestamp >= start_date).group_by(User.username).order_by(desc("tokens")).limit(5)
    res_user = await db.execute(stmt_user)
    for uname, utokens in res_user.all():
        user_usage.append({"username": uname, "tokens": utokens})

    # 5. Peak Usage Periods (BI - Hour of day)
    peak_usage = []
    # Note: SQLite specific strftime for hour extraction
    stmt_peak = select(func.strftime('%H', AuditLog.timestamp).label("hour"), func.count(AuditLog.id)).where(AuditLog.organization_id == current_user.organization_id, AuditLog.timestamp >= start_date).group_by("hour").order_by("hour")
    res_peak = await db.execute(stmt_peak)
    for hour, count in res_peak.all():
        peak_usage.append({"hour": f"{hour}:00", "count": count})

    metrics = {
        "total_requests": total_requests,
        "total_tokens_original": tokens_original,
        "total_tokens_compressed": tokens_compressed,
        "middle_ai_input": tokens_compressed,
        "middle_ai_output": tokens_response,
        "financial_efficiency_pct": round((cost_saved / (cost_saved + (tokens_original * 0.00001))) * 100, 1) if tokens_original > 0 else 0, 
        "total_cost_saved": cost_saved,
        "roi_multiplier": round((float(cost_saved) / 0.001), 2) if cost_saved > 0 else 0, # Mock ROI baseline
        "compression_ratio": round((1 - (tokens_compressed / tokens_original)) * 100, 1) if tokens_original > 0 else 0,
        "cache_hit_rate": 0,
        "avg_latency": 0
    }
        
    return templates.TemplateResponse("dashboard/home.html", {
        "request": request, 
        "metrics": metrics,
        "recent_logs": recent_logs,
        "user": current_user,
        "days": days,
        "daily_stats_json": json.dumps(daily_stats),
        "provider_stats_json": json.dumps(provider_stats),
        "user_usage_json": json.dumps(user_usage),
        "peak_usage_json": json.dumps(peak_usage)
    })


@router.get("/rules", response_class=HTMLResponse, name="dashboard_rules")
async def compression_rules(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    stmt = select(CompressionRule).where(
        (CompressionRule.organization_id == current_user.organization_id) | (CompressionRule.is_system == True)
    )
    res = await db.execute(stmt)
    rules = res.scalars().all()
    return templates.TemplateResponse("dashboard/rules.html", {"request": request, "custom_rules": rules, "user": current_user})

@router.get("/providers", response_class=HTMLResponse, name="dashboard_ai_providers")
async def ai_providers(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    stmt = select(AIProvider).where(
        (AIProvider.organization_id == current_user.organization_id) | (AIProvider.is_system == True)
    )
    res = await db.execute(stmt)
    providers = res.scalars().all()
    return templates.TemplateResponse("dashboard/ai_providers.html", {"request": request, "providers": providers, "user": current_user})

@router.get("/team", response_class=HTMLResponse, name="dashboard_team")
async def team_management(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    stmt = select(User).where(User.organization_id == current_user.organization_id)
    res = await db.execute(stmt)
    members = [{"user": u, "requests": 0, "active_keys": 0} for u in res.scalars().all()]
    return templates.TemplateResponse("dashboard/team.html", {"request": request, "member_stats": members, "user": current_user})

@router.get("/api-keys", response_class=HTMLResponse, name="dashboard_api_key_list")
async def api_key_list(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    stmt = select(APIKey).where(APIKey.organization_id == current_user.organization_id)
    res = await db.execute(stmt)
    keys = res.scalars().all()
    return templates.TemplateResponse("dashboard/api_keys.html", {"request": request, "keys": keys, "user": current_user})

@router.get("/audit", response_class=HTMLResponse, name="dashboard_security_audit")
async def security_audit(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    
    # Get API keys for the left column
    stmt_keys = select(APIKey).where(APIKey.organization_id == current_user.organization_id)
    res_keys = await db.execute(stmt_keys)
    api_keys = res_keys.scalars().all()
    for k in api_keys:
        k.masked_key = f"{k.key[:6]}...{k.key[-4:]}" if len(k.key) > 10 else k.key

    stmt = select(AuditLog).where(AuditLog.organization_id == current_user.organization_id).order_by(desc(AuditLog.timestamp)).limit(50)
    res = await db.execute(stmt)
    logs = res.scalars().all()
    return templates.TemplateResponse("dashboard/security_audit.html", {"request": request, "logs": logs, "user": current_user, "api_keys": api_keys})

@router.get("/audit-list", response_class=HTMLResponse, name="dashboard_audit_list")
async def audit_list_view(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    search = request.query_params.get("search", "")
    status_filter = request.query_params.get("status", "")
    
    stmt = select(AuditLog).where(AuditLog.organization_id == current_user.organization_id)
    if search:
        stmt = stmt.where(AuditLog.original_payload.contains(search) | AuditLog.final_response.contains(search))
    if status_filter:
        stmt = stmt.where(AuditLog.status == status_filter)
        
    stmt = stmt.order_by(desc(AuditLog.timestamp)).limit(100)
    res = await db.execute(stmt)
    logs = res.scalars().all()
    
    return templates.TemplateResponse("dashboard/audit_list.html", {
        "request": request, 
        "logs": logs, 
        "search": search, 
        "status_filter": status_filter,
        "user": current_user
    })

@router.get("/audit/{log_id}", response_class=HTMLResponse, name="dashboard_audit_detail")
async def audit_detail(request: Request, log_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    stmt = select(AuditLog).where(AuditLog.id == log_id, AuditLog.organization_id == current_user.organization_id)
    res = await db.execute(stmt)
    log = res.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    return templates.TemplateResponse("dashboard/audit_detail.html", {"request": request, "log": log, "user": current_user})

@router.get("/playground", response_class=HTMLResponse, name="dashboard_playground")
async def playground(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    stmt = select(APIKey).where(APIKey.organization_id == current_user.organization_id)
    res = await db.execute(stmt)
    api_keys = res.scalars().all()
    # Mask keys for dropdown
    for k in api_keys:
        k.masked_key = f"{k.key[:6]}...{k.key[-4:]}" if len(k.key) > 10 else k.key
        
    return templates.TemplateResponse("dashboard/playground.html", {"request": request, "user": current_user, "api_keys": api_keys})
@router.get("/documents", response_class=HTMLResponse, name="dashboard_masked_documents_list")
async def masked_documents_list(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    from sqlalchemy.orm import selectinload
    stmt = select(SecureDocument).where(SecureDocument.organization_id == current_user.organization_id).options(selectinload(SecureDocument.key_mappings))
    res = await db.execute(stmt)
    documents = res.scalars().all()
    return templates.TemplateResponse("dashboard/masked_documents_list.html", {"request": request, "documents": documents, "user": current_user})

@router.get("/documents/{doc_id}", response_class=HTMLResponse, name="dashboard_masked_document_chat")
async def masked_document_chat(request: Request, doc_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    from sqlalchemy.orm import selectinload
    stmt = select(SecureDocument).where(SecureDocument.id == doc_id, SecureDocument.organization_id == current_user.organization_id).options(selectinload(SecureDocument.key_mappings))
    res = await db.execute(stmt)
    document = res.scalar_one_or_none()
    if not document: raise HTTPException(status_code=404, detail="Document not found")
    return templates.TemplateResponse("dashboard/masked_document_chat.html", {"request": request, "document": document, "user": current_user})

@router.get("/documents/{doc_id}/preview", response_class=HTMLResponse, name="dashboard_masked_document_preview_text")
async def masked_document_preview_text(request: Request, doc_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    stmt = select(SecureDocument).where(SecureDocument.id == doc_id, SecureDocument.organization_id == current_user.organization_id)
    res = await db.execute(stmt)
    document = res.scalar_one_or_none()
    if not document: raise HTTPException(status_code=404, detail="Document not found")
    return templates.TemplateResponse("dashboard/masked_document_preview.html", {"request": request, "document": document, "user": current_user})

@router.get("/documents/{doc_id}/download-text", name="dashboard_masked_document_download_text")
async def masked_document_download_text(doc_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Placeholder for download logic
    return RedirectResponse(url="/dashboard/documents")

@router.get("/documents/{doc_id}/preview-pdf", name="dashboard_masked_document_preview_pdf")
async def masked_document_preview_pdf(doc_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Placeholder
    return RedirectResponse(url="/dashboard/documents")
@router.get("/edge-nodes", response_class=HTMLResponse, name="dashboard_edge_nodes")
async def edge_nodes(request: Request, current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    return templates.TemplateResponse("dashboard/edge_nodes.html", {"request": request, "user": current_user})

@router.get("/mcp-tools", response_class=HTMLResponse, name="dashboard_mcp_tools")
async def mcp_tools(request: Request, current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    return templates.TemplateResponse("dashboard/mcp_tools.html", {"request": request, "user": current_user})

@router.get("/documents/{doc_id}/download-pdf", name="dashboard_masked_document_download_pdf")
async def masked_document_download_pdf(doc_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Placeholder
    return RedirectResponse(url="/dashboard/documents")

@router.get("/privacy", response_class=HTMLResponse, name="dashboard_privacy")
async def privacy_view(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    stmt = select(PrivacyConfig).where(PrivacyConfig.organization_id == current_user.organization_id)
    res = await db.execute(stmt)
    config = res.scalar_one_or_none()
    if not config:
        config = PrivacyConfig(organization_id=current_user.organization_id)
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return templates.TemplateResponse("dashboard/privacy.html", {"request": request, "config": config, "user": current_user})

@router.post("/privacy", name="dashboard_privacy_post")
async def privacy_post(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Placeholder for post logic
    return RedirectResponse(url="/dashboard/privacy")
