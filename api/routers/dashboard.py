from datetime import datetime, timedelta
import json
import io
from fpdf import FPDF
from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc

from api.dependencies import get_db
from models.accounts import User
from models.dashboard import APIKey, CompressionRule, AIProvider, AuditLog, SecureDocument, KeyMapping, PrivacyConfig
from core.security import decode_access_token
from api.templates_config import templates
"""
Firma-KI  —  Analytics Report
German-corporate minimal design.
Requires: pip install reportlab
"""

import io
from datetime import datetime, timedelta

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable



router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


from sqlalchemy.orm import selectinload

# Utility for common dashboard context
async def get_common_context(db: AsyncSession, user: User):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt_today = select(func.count(AuditLog.id)).where(
        AuditLog.organization_id == user.organization_id,
        AuditLog.timestamp >= today_start
    )
    res_today = await db.execute(stmt_today)
    return {
        "user": user,
        "nex_requests_today": res_today.scalar() or 0
    }

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
    
    stmt = select(User).options(selectinload(User.organization)).where(User.username == username)
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
    
    # 1b. Requests today
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt_today = select(func.count(AuditLog.id)).where(
        AuditLog.organization_id == current_user.organization_id,
        AuditLog.timestamp >= today_start
    )
    res_today = await db.execute(stmt_today)
    nex_requests_today = res_today.scalar() or 0
    
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
    stmt_logs = select(AuditLog).options(selectinload(AuditLog.ai_provider)).where(AuditLog.organization_id == current_user.organization_id).order_by(desc(AuditLog.timestamp)).limit(10)
    res_logs = await db.execute(stmt_logs)
    recent_logs = res_logs.scalars().all()
    
    # ── Real per-day stats from AuditLog ────────────────────────────────────────
    stmt_daily = select(
        func.strftime('%Y-%m-%d', AuditLog.timestamp).label("day"),
        func.sum(AuditLog.tokens_original).label("tok_orig"),
        func.sum(AuditLog.tokens_compressed).label("tok_comp"),
        func.count(AuditLog.id).label("reqs"),
        func.sum(AuditLog.cost_actual).label("cost"),
    ).where(
        AuditLog.organization_id == current_user.organization_id,
        AuditLog.timestamp >= start_date,
    ).group_by("day").order_by("day")
    res_daily = await db.execute(stmt_daily)
    daily_map = {
        row.day: {
            "date": row.day,
            "tokens_original": int(row.tok_orig or 0),
            "tokens_compressed": int(row.tok_comp or 0),
            "requests": int(row.reqs or 0),
            "cost": float(row.cost or 0),
        }
        for row in res_daily.all()
    }
    daily_stats = []
    for i in range(days):
        dt = (datetime.utcnow() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        daily_stats.append(daily_map.get(dt, {
            "date": dt, "tokens_original": 0, "tokens_compressed": 0, "requests": 0, "cost": 0.0
        }))

    # ── Provider breakdown ───────────────────────────────────────────────────────
    provider_stats = []
    stmt_prov = select(
        AIProvider.name,
        func.count(AuditLog.id).label("reqs"),
        func.sum(AuditLog.tokens_original).label("tokens"),
        func.sum(AuditLog.cost_actual).label("cost"),
    ).join(AuditLog, AIProvider.id == AuditLog.ai_provider_id, isouter=True).where(
        AuditLog.organization_id == current_user.organization_id,
        AuditLog.timestamp >= start_date,
    ).group_by(AIProvider.name)
    res_prov = await db.execute(stmt_prov)
    for name, count, tok, cost in res_prov.all():
        provider_stats.append({"name": name, "requests": count or 0, "tokens": int(tok or 0), "cost": float(cost or 0)})

    # ── User usage ───────────────────────────────────────────────────────────────
    user_usage: list = []
    
    # ── NEX Algorithm Registries (for Test Lab) ──────────────────────────────
    from services.gateway.compression.nex_code_compressor import ALGO_REGISTRY as CODE_ALGO
    from services.gateway.compression.nex_text_compressor import ALGO_REGISTRY as TEXT_ALGO
    
    # Calculate aggregate metrics for the template
    ratio = 0
    if tokens_original > 0:
        ratio = round((1 - tokens_compressed / tokens_original) * 100)

    # Simplified avg latency for overview (mocking if missing in logs)
    avg_latency = 0
    if total_requests > 0:
        stmt_lat = select(func.avg(AuditLog.latency_ms)).where(AuditLog.organization_id == current_user.organization_id)
        res_lat = await db.execute(stmt_lat)
        avg_latency = res_lat.scalar() or 0

    metrics = {
        "total_requests": total_requests,
        "total_tokens_original": tokens_original,
        "total_tokens_compressed": tokens_compressed,
        "total_cost_saved": float(cost_saved),
        "compression_ratio": ratio,
        "avg_latency": avg_latency
    }
    
    return templates.TemplateResponse("dashboard/home.html", {
        "request": request,
        "active_page": "dashboard",
        "metrics": metrics,
        "recent_logs": recent_logs,
        "daily_stats": daily_stats,
        "daily_stats_json": json.dumps(daily_stats),
        "provider_stats": provider_stats,
        "provider_stats_json": json.dumps(provider_stats),
        "user_usage": user_usage,
        "user": current_user,
        "days": days
    })

@router.get("/compression/test-lab", response_class=HTMLResponse)
async def test_lab(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(login_required)):
    from services.gateway.compression.nex_code_compressor import ALGO_REGISTRY as CODE_ALGO
    from services.gateway.compression.nex_text_compressor import ALGO_REGISTRY as TEXT_ALGO
    
    common = await get_common_context(db, current_user)
    return templates.TemplateResponse("dashboard/compression_test_lab.html", {
        "request": request,
        "active_page": "test_lab",
        "code_algos": CODE_ALGO,
        "text_algos": TEXT_ALGO,
        **common
    })

@router.post("/api/compression/test-action")
async def api_test_compression(
    request: Request, 
    db: AsyncSession = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    if not current_user:
        return {"error": "Unauthorized"}
    
    data = await request.json()
    input_text = data.get("text", "")
    algo_key = data.get("algo", "")
    mode = data.get("mode", "code") # "code" or "text"
    
    if mode == "code":
        from services.gateway.compression.nex_code_compressor import NEXCodeCompressor
        result = NEXCodeCompressor.compress_with_algo(input_text, algo_key)
    else:
        from services.gateway.compression.nex_text_compressor import NEXTextCompressor
        result = NEXTextCompressor.compress_with_algo(input_text, algo_key)
        
    return result.summary() | {"compressed_text": result.compressed}

    # ── Peak hours ───────────────────────────────────────────────────────────────
    peak_usage = []
    stmt_peak = select(
        func.strftime('%H', AuditLog.timestamp).label("hour"),
        func.count(AuditLog.id).label("cnt"),
    ).where(
        AuditLog.organization_id == current_user.organization_id,
        AuditLog.timestamp >= start_date,
    ).group_by("hour").order_by("hour")
    res_peak = await db.execute(stmt_peak)
    for hour, count in res_peak.all():
        peak_usage.append({"hour": f"{hour}:00", "count": count})

    # ── Avg latency ──────────────────────────────────────────────────────────────
    stmt_lat = select(func.avg(AuditLog.latency_ms)).where(
        AuditLog.organization_id == current_user.organization_id,
        AuditLog.timestamp >= start_date,
    )
    res_lat = await db.execute(stmt_lat)
    avg_latency = round(res_lat.scalar() or 0)

    metrics = {
        "total_requests": total_requests,
        "total_tokens_original": int(tokens_original),
        "total_tokens_compressed": int(tokens_compressed),
        "middle_ai_input": int(tokens_compressed),
        "middle_ai_output": int(tokens_response),
        "financial_efficiency_pct": round((float(cost_saved) / (float(cost_saved) + (int(tokens_original) * 0.00001))) * 100, 1) if tokens_original and cost_saved else 0,
        "total_cost_saved": float(cost_saved) if cost_saved else 0.0,
        "roi_multiplier": round(float(cost_saved) / 0.001, 2) if cost_saved and float(cost_saved) > 0 else 0,
        "compression_ratio": round((1 - (int(tokens_compressed) / int(tokens_original))) * 100, 1) if tokens_original else 0,
        "cache_hit_rate": 0,
        "avg_latency": avg_latency,
    }
        
    context = await get_common_context(db, current_user)
    context.update({
        "metrics": metrics,
        "recent_logs": recent_logs,
        "days": days,
        "daily_stats_json": json.dumps(daily_stats),
        "provider_stats_json": json.dumps(provider_stats),
        "user_usage_json": json.dumps(user_usage),
        "peak_usage_json": json.dumps(peak_usage)
    })
    return templates.TemplateResponse("dashboard/home.html", {"request": request, **context})


@router.get("/rules", response_class=HTMLResponse, name="dashboard_rules")
async def compression_rules(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    stmt = select(CompressionRule).where(
        (CompressionRule.organization_id == current_user.organization_id) | (CompressionRule.is_system == True)
    )
    res = await db.execute(stmt)
    rules = res.scalars().all()
    
    lang_groups = {}
    prog_groups = {}
    custom_rules = []
    
    for r in rules:
        if r.rule_type == 'language':
            l = r.language or 'en'
            if l not in lang_groups: lang_groups[l] = []
            lang_groups[l].append(r)
        elif r.rule_type == 'programming':
            p = r.programming_language or 'generic'
            if p not in prog_groups: prog_groups[p] = []
            prog_groups[p].append(r)
        else:
            custom_rules.append(r)

    context = await get_common_context(db, current_user)
    context.update({
        "lang_groups": lang_groups,
        "prog_groups": prog_groups,
        "custom_rules": custom_rules
    })
    return templates.TemplateResponse("dashboard/rules.html", {"request": request, **context})

@router.get("/providers", response_class=HTMLResponse, name="dashboard_ai_providers")
async def ai_providers(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    stmt = select(AIProvider).where(
        (AIProvider.organization_id == current_user.organization_id) | (AIProvider.is_system == True)
    )
    res = await db.execute(stmt)
    providers = res.scalars().all()

    context = await get_common_context(db, current_user)
    context["providers"] = providers
    context["error_message"] = None
    return templates.TemplateResponse("dashboard/ai_providers.html", {"request": request, **context})


@router.post("/providers", response_class=HTMLResponse)
async def ai_providers_post(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    form = await request.form()
    action = form.get("action", "")
    error_message = None

    try:
        if action == "create":
            name = (form.get("name") or "").strip()
            if not name:
                error_message = "Provider name is required."
            else:
                new_prov = AIProvider(
                    name=name,
                    provider_type=form.get("provider_type", "custom"),
                    api_base_url=(form.get("api_base_url") or "").strip(),
                    api_key=(form.get("api_key") or "").strip(),
                    model_name=(form.get("model_name") or "").strip(),
                    output_webhook_url=(form.get("output_webhook_url") or "").strip(),
                    max_tokens=int(form.get("max_tokens") or 4096),
                    temperature=float(form.get("temperature") or 0.7),
                    is_active=True,
                    is_default=False,
                    is_system=False,
                    organization_id=current_user.organization_id,
                )
                db.add(new_prov)
                await db.commit()

        elif action == "toggle":
            provider_id = form.get("provider_id")
            stmt_p = select(AIProvider).where(
                AIProvider.id == provider_id,
                AIProvider.organization_id == current_user.organization_id,
                AIProvider.is_system == False,
            )
            res_p = await db.execute(stmt_p)
            prov = res_p.scalar_one_or_none()
            if prov:
                prov.is_active = not prov.is_active
                await db.commit()

        elif action == "set_default":
            provider_id = form.get("provider_id")
            # Clear existing default for org
            stmt_clear = select(AIProvider).where(AIProvider.organization_id == current_user.organization_id)
            res_clear = await db.execute(stmt_clear)
            for p in res_clear.scalars().all():
                p.is_default = False
            # Set new default
            stmt_p = select(AIProvider).where(
                AIProvider.id == provider_id,
                AIProvider.organization_id == current_user.organization_id,
            )
            res_p = await db.execute(stmt_p)
            prov = res_p.scalar_one_or_none()
            if prov:
                prov.is_default = True
            await db.commit()

        elif action == "delete":
            provider_id = form.get("provider_id")
            stmt_p = select(AIProvider).where(
                AIProvider.id == provider_id,
                AIProvider.organization_id == current_user.organization_id,
                AIProvider.is_system == False,
            )
            res_p = await db.execute(stmt_p)
            prov = res_p.scalar_one_or_none()
            if prov:
                await db.delete(prov)
                await db.commit()

    except Exception as exc:
        await db.rollback()
        error_message = str(exc)

    # Reload list
    stmt = select(AIProvider).where(
        (AIProvider.organization_id == current_user.organization_id) | (AIProvider.is_system == True)
    )
    res = await db.execute(stmt)
    providers = res.scalars().all()
    context = await get_common_context(db, current_user)
    context["providers"] = providers
    context["error_message"] = error_message
    return templates.TemplateResponse("dashboard/ai_providers.html", {"request": request, **context})


@router.get("/team", response_class=HTMLResponse, name="dashboard_team")
async def team_management(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    stmt = select(User).where(User.organization_id == current_user.organization_id)
    res = await db.execute(stmt)
    members = [{"user": u, "requests": 0, "active_keys": 0} for u in res.scalars().all()]
    
    context = await get_common_context(db, current_user)
    context["member_stats"] = members
    return templates.TemplateResponse("dashboard/team.html", {"request": request, **context})

@router.get("/api-keys", response_class=HTMLResponse, name="dashboard_api_key_list")
async def api_key_list(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    stmt = select(APIKey).where(APIKey.organization_id == current_user.organization_id)
    res = await db.execute(stmt)
    keys = res.scalars().all()

    stmt_p = select(AIProvider).where(AIProvider.organization_id == current_user.organization_id)
    res_p = await db.execute(stmt_p)
    providers = res_p.scalars().all()

    context = await get_common_context(db, current_user)
    context["keys"] = keys
    context["providers"] = providers
    context["success_message"] = None
    return templates.TemplateResponse("dashboard/api_keys.html", {"request": request, **context})


@router.post("/api-keys", response_class=HTMLResponse)
async def api_key_post(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    form = await request.form()
    action = form.get("action", "")
    success_message = None
    error_message = None

    # ── CREATE ──────────────────────────────────────────────────────────────────
    if action == "create":
        try:
            name = (form.get("name") or "").strip()
            if not name:
                error_message = "Key name is required."
            else:
                rpm = form.get("rpm_limit")
                dtl = form.get("daily_token_limit")
                new_key = APIKey(
                    name=name,
                    organization_id=current_user.organization_id,
                    user_id=current_user.id,
                    linked_provider_id=form.get("provider_id") or None,
                    rate_limit=int(rpm) if rpm and rpm.isdigit() else 60,
                    daily_token_limit=int(dtl) if dtl and dtl.isdigit() else 0,
                    enable_compression=bool(form.get("enable_compression")),
                    enable_caching=bool(form.get("enable_caching")),
                )
                db.add(new_key)
                await db.commit()
                await db.refresh(new_key)
                success_message = new_key.key  # shown once
        except Exception as exc:
            await db.rollback()
            error_message = str(exc)

    # ── REVOKE ──────────────────────────────────────────────────────────────────
    elif action == "revoke":
        key_id = form.get("key_id")
        if key_id:
            stmt_k = select(APIKey).where(
                APIKey.id == key_id,
                APIKey.organization_id == current_user.organization_id
            )
            res_k = await db.execute(stmt_k)
            key_obj = res_k.scalar_one_or_none()
            if key_obj:
                key_obj.is_active = False
                await db.commit()

    # ── Reload list ─────────────────────────────────────────────────────────────
    stmt = select(APIKey).where(APIKey.organization_id == current_user.organization_id)
    res = await db.execute(stmt)
    keys = res.scalars().all()

    stmt_p = select(AIProvider).where(AIProvider.organization_id == current_user.organization_id)
    res_p = await db.execute(stmt_p)
    providers = res_p.scalars().all()

    context = await get_common_context(db, current_user)
    context["keys"] = keys
    context["providers"] = providers
    context["success_message"] = success_message
    context["error_message"] = error_message
    return templates.TemplateResponse("dashboard/api_keys.html", {"request": request, **context})




@router.get("/playground", response_class=HTMLResponse, name="dashboard_playground")
async def playground(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    stmt = select(APIKey).where(APIKey.organization_id == current_user.organization_id)
    res = await db.execute(stmt)
    api_keys = res.scalars().all()
        
    context = await get_common_context(db, current_user)
    context["api_keys"] = api_keys
    return templates.TemplateResponse("dashboard/playground.html", {"request": request, **context})
@router.get("/edge-nodes", response_class=HTMLResponse, name="dashboard_edge_nodes")
async def edge_nodes(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    context = await get_common_context(db, current_user)
    return templates.TemplateResponse("dashboard/edge_nodes.html", {"request": request, **context})

@router.get("/mcp-tools", response_class=HTMLResponse, name="dashboard_mcp_tools")
async def mcp_tools(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return RedirectResponse(url="/login")
    context = await get_common_context(db, current_user)
    return templates.TemplateResponse("dashboard/mcp_tools.html", {"request": request, **context})


@router.get("/cascade", response_class=HTMLResponse, name="dashboard_cascade")
async def cascade_intelligence(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if not user:
        return RedirectResponse(url="/accounts/login", status_code=status.HTTP_302_FOUND)
    context = await get_common_context(db, user)
    return templates.TemplateResponse("dashboard/cascade_intelligence.html", {
        "request": request, **context
    })

@router.get("/compression", response_class=HTMLResponse, name="dashboard_compression")
async def compression_engine_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if not user:
        return RedirectResponse(url="/accounts/login", status_code=status.HTTP_302_FOUND)
    context = await get_common_context(db, user)
    return templates.TemplateResponse("dashboard/compression_engine.html", {
        "request": request, **context
    })

@router.get("/telemetry", response_class=HTMLResponse, name="dashboard_telemetry")
async def token_telemetry_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if not user:
        return RedirectResponse(url="/accounts/login", status_code=status.HTTP_302_FOUND)
    context = await get_common_context(db, user)
    # Fetch real audit log stats from database
    stmt = select(AuditLog).where(AuditLog.organization_id == user.organization_id).order_by(desc(AuditLog.timestamp)).limit(50)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    total_tokens_in = sum((l.tokens_original or 0) for l in logs)
    total_tokens_out = sum((l.tokens_compressed or 0) for l in logs)
    total_saved = total_tokens_in - total_tokens_out
    avg_ratio = round((total_saved / total_tokens_in * 100) if total_tokens_in > 0 else 0, 1)
    return templates.TemplateResponse("dashboard/token_telemetry.html", {
        "request": request,
        **context,
        "telemetry": {
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "total_saved": total_saved,
            "avg_compression_pct": avg_ratio,
            "request_count": len(logs),
        }
    })

@router.get("/monitor", response_class=HTMLResponse, name="dashboard_pipeline_monitor")
async def pipeline_monitor(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if not user:
        return RedirectResponse(url="/accounts/login", status_code=status.HTTP_302_FOUND)
    context = await get_common_context(db, user)
    stmt = select(APIKey).where(APIKey.organization_id == user.organization_id)
    result = await db.execute(stmt)
    api_keys = result.scalars().all()
    return templates.TemplateResponse("dashboard/pipeline_monitor.html", {
        "request": request, **context, "api_keys": api_keys
    })


@router.get("/output/schema", response_class=HTMLResponse, name="dashboard_schema_standardization")
async def schema_standardization(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    context = await get_common_context(db, user)
    return templates.TemplateResponse("dashboard/output_schema.html", {"request": request, **context})




@router.get("/output/stream-normalization", response_class=HTMLResponse, name="dashboard_stream_normalization")
async def stream_normalization(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    context = await get_common_context(db, user)
    return templates.TemplateResponse("dashboard/output_stream_normalization.html", {"request": request, **context})




@router.get("/analytics", response_class=HTMLResponse, name="dashboard_analytics")
async def analytics_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    # Filter query params
    status_filter: str = "all",
    api_key_filter: str = "all",
    source_filter: str = "all",
    days: int = 7,
    # Pagination
    page: int = 1,
    limit: int = 50,
):
    if not user:
        return RedirectResponse(url="/accounts/login", status_code=status.HTTP_302_FOUND)
    context = await get_common_context(db, user)

    page = max(1, page)
    limit = max(10, min(200, limit))

    since = datetime.utcnow() - timedelta(days=days)

    # Build filtered query for all logs (used for stats)
    base_q = (
        select(AuditLog)
        .options(
            selectinload(AuditLog.ai_provider),
            selectinload(AuditLog.api_key),
        )
        .where(
            AuditLog.organization_id == user.organization_id,
            AuditLog.timestamp >= since,
        )
    )
    if status_filter != "all":
        base_q = base_q.where(AuditLog.status == status_filter)
    if api_key_filter != "all":
        base_q = base_q.where(AuditLog.api_key_id == api_key_filter)
    if source_filter != "all":
        base_q = base_q.where(AuditLog.source == source_filter)

    # First execute the query to get all logs for accurate summary stats
    base_q = base_q.order_by(desc(AuditLog.timestamp))
    result_all = await db.execute(base_q)
    all_logs = result_all.scalars().all()
    total_logs = len(all_logs)
    total_pages = max(1, (total_logs + limit - 1) // limit)

    # The slice for the current page
    offset = (page - 1) * limit
    logs = all_logs[offset:offset + limit]


    # ── Summary aggregates ─────────────────────────────────────────────────────
    total_requests = len(logs)
    total_tokens_in  = sum((l.tokens_original or 0) for l in logs)
    total_tokens_out = sum((l.tokens_compressed or 0) for l in logs)
    total_saved      = total_tokens_in - total_tokens_out
    total_cost       = float(sum((float(l.cost_actual) or 0) for l in logs))
    total_cost_saved = float(sum((float(l.cost_saved) or 0) for l in logs))
    avg_latency      = round(sum((l.latency_ms or 0) for l in logs) / max(1, total_requests))
    errors           = sum(1 for l in logs if l.status != "success")
    avg_ratio        = round((total_saved / total_tokens_in * 100) if total_tokens_in > 0 else 0, 1)

    summary = {
        "total_requests": total_requests,
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "tokens_saved": total_saved,
        "avg_compression_pct": avg_ratio,
        "total_cost_usd": round(total_cost, 6),
        "total_cost_saved_usd": round(total_cost_saved, 6),
        "avg_latency_ms": avg_latency,
        "error_count": errors,
    }

    # ── Per-API-key breakdown ──────────────────────────────────────────────────
    key_stats: dict = {}
    for log in logs:
        kid = log.api_key_id or "unknown"
        kname = (log.api_key.name if log.api_key else None) or "Unknown Key"
        if kid not in key_stats:
            key_stats[kid] = {"name": kname, "requests": 0, "tokens_in": 0, "tokens_saved": 0, "cost": 0.0, "errors": 0}
        key_stats[kid]["requests"] += 1
        key_stats[kid]["tokens_in"] += (log.tokens_original or 0)
        key_stats[kid]["tokens_saved"] += max(0, (log.tokens_original or 0) - (log.tokens_compressed or 0))
        key_stats[kid]["cost"] += float(log.cost_actual or 0)
        if log.status != "success":
            key_stats[kid]["errors"] += 1

    # ── Per-provider breakdown ─────────────────────────────────────────────────
    provider_stats: dict = {}
    for log in logs:
        pid = log.ai_provider_id or "unknown"
        pname = (log.ai_provider.name if log.ai_provider else None) or "Unknown Provider"
        if pid not in provider_stats:
            provider_stats[pid] = {"name": pname, "requests": 0, "tokens": 0, "cost": 0.0}
        provider_stats[pid]["requests"] += 1
        provider_stats[pid]["tokens"] += (log.tokens_compressed or log.tokens_original or 0)
        provider_stats[pid]["cost"] += float(log.cost_actual or 0)

    # ── Filter options for the UI ──────────────────────────────────────────────
    all_keys_stmt = select(APIKey).where(APIKey.organization_id == user.organization_id)
    all_keys_res = await db.execute(all_keys_stmt)
    all_keys = all_keys_res.scalars().all()

    return templates.TemplateResponse("dashboard/analytics.html", {
        "request": request,
        **context,
        "summary": summary,
        "logs": logs,
        "key_stats": list(key_stats.values()),
        "provider_stats": list(provider_stats.values()),
        "all_keys": all_keys,
        # Filter state
        "filter_status": status_filter,
        "filter_api_key": api_key_filter,
        "filter_source": source_filter,
        "filter_days": days,
        # Pagination
        "current_page": page,
        "total_pages": total_pages,
    })



@router.get("/compression/code", response_class=HTMLResponse, name="dashboard_compression_code")
async def compression_code_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if not user:
        return RedirectResponse(url="/accounts/login", status_code=status.HTTP_302_FOUND)
    context = await get_common_context(db, user)
    return templates.TemplateResponse("dashboard/compression_code.html", {
        "request": request, **context
    })

@router.get("/compression/text", response_class=HTMLResponse, name="dashboard_compression_text")
async def compression_text_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if not user:
        return RedirectResponse(url="/accounts/login", status_code=status.HTTP_302_FOUND)
    context = await get_common_context(db, user)
    return templates.TemplateResponse("dashboard/compression_text.html", {
        "request": request, **context
    })


# ─── Pipeline Simulation API ─────────────────────────────────────────────────

import ast
import re
import tokenize
import io
import time
import math
from collections import Counter

from fastapi.responses import JSONResponse
from pydantic import BaseModel


class SimulateRequest(BaseModel):
    input_text: str
    payload_type: str = "code"          # code | text | auto
    compression_algorithm: str = "ast"  # see below
    routing_threshold_tokens: int = 500


def _count_words(text: str) -> int:
    return len(text.split())

def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 4))


# ── CODE COMPRESSION ALGORITHMS ───────────────────────────────────────────────

def _ast_prune(source: str) -> dict:
    """Python AST: strip docstrings and string-constant comments."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"success": False, "error": str(e), "result": source}

    class _Stripper(ast.NodeTransformer):
        def visit_Expr(self, node):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return None
            return node
    tree = _Stripper().visit(tree)
    ast.fix_missing_locations(tree)
    try:
        result = ast.unparse(tree)
    except Exception:
        result = source
    return {"success": True, "result": result}

def _regex_prune(source: str) -> dict:
    """Regex: remove #-comments, triple-quoted strings, collapse blank lines."""
    r = re.sub(r'#[^\n]*', '', source)
    r = re.sub(r'"""[\s\S]*?"""', '', r)
    r = re.sub(r"'''[\s\S]*?'''", '', r)
    r = re.sub(r'\n\s*\n+', '\n', r)
    return {"success": True, "result": r.strip()}

def _minifier(source: str) -> dict:
    """Python Minifier: inline short functions, remove type hints, compress names."""
    r = re.sub(r'#[^\n]*', '', source)
    r = re.sub(r'"""[\s\S]*?"""', '""', r)
    r = re.sub(r"'''[\s\S]*?'''", "''", r)
    # Remove type annotations (very simplified)
    r = re.sub(r':\s*[\w\[\], |]+\s*=', ' =', r)
    r = re.sub(r'->\s*[\w\[\], |]+:', ':', r)
    r = re.sub(r'\n\s*\n+', '\n', r)
    r = re.sub(r'  +', ' ', r)
    return {"success": True, "result": r.strip()}

def _dead_code_eliminator(source: str) -> dict:
    """Dead Code: remove unreachable branches after return/raise, strip pass-only blocks."""
    lines = source.split('\n')
    result_lines = []
    skip_until_dedent = False
    base_indent = 0
    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if skip_until_dedent and indent > base_indent:
            continue
        skip_until_dedent = False
        result_lines.append(line)
        # Mark what follows a top-level return/raise as dead
        if re.match(r'^ *(return|raise)\b', line):
            skip_until_dedent = True
            base_indent = indent - 4
    result = '\n'.join(result_lines)
    result = re.sub(r'\n\s*pass\s*\n', '\n', result)  # strip bare pass
    result = re.sub(r'\n\s*\n+', '\n', result)
    return {"success": True, "result": result.strip()}

def _whitespace_compressor(source: str) -> dict:
    """Whitespace: normalize indents, collapse spaces, remove blank lines entirely."""
    r = re.sub(r'[ \t]+', ' ', source)
    r = re.sub(r'\n\s*\n', '\n', r)
    r = re.sub(r'^\s+', '', r, flags=re.MULTILINE)
    return {"success": True, "result": r.strip()}


# ── TEXT / NL COMPRESSION ALGORITHMS ─────────────────────────────────────────

def _nex_s1_prune(text: str) -> dict:
    """NEX S1: semantic density filter — keeps high-signal sentences."""
    SIGNAL_WORDS = {"result", "shows", "analysis", "impact", "increase", "decrease",
                    "achieve", "conclude", "found", "data", "value", "cost", "performance",
                    "failure", "success", "model", "api", "token", "study", "evidence", "key"}
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    high = [s for s in sentences if len(s.split()) > 5 and
            any(w in s.lower() for w in SIGNAL_WORDS)]
    if not high:
        high = sentences[:max(1, len(sentences) // 2)]
    return {"success": True, "result": " ".join(high)}

def _tfidf_extractor(text: str) -> dict:
    """TF-IDF: rank sentences by term frequency × inverse document frequency, keep top 40%."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if len(sentences) <= 2:
        return {"success": True, "result": text}
    stop = {"the","a","an","is","in","it","of","to","and","or","that","this","was","are","for","on","at","be","by","with","as","not","we","you","i","he","she","they"}
    def tokenize_sent(s): return [w.lower() for w in re.findall(r'\b\w+\b', s) if w.lower() not in stop]
    tf = [Counter(tokenize_sent(s)) for s in sentences]
    all_words = [w for t in tf for w in t]
    wcount = Counter(all_words)
    N = len(sentences)
    def idf(w): return math.log(N / (1 + sum(1 for t in tf if w in t)))
    def score(i):
        words = tokenize_sent(sentences[i])
        return sum(tf[i].get(w, 0) * idf(w) for w in words) / max(1, len(words))
    scores = [(score(i), i) for i in range(len(sentences))]
    scores.sort(reverse=True)
    keep_n = max(1, int(len(sentences) * 0.4))
    keep_idx = sorted([i for _, i in scores[:keep_n]])
    return {"success": True, "result": " ".join(sentences[i] for i in keep_idx)}

def _stopword_pruner(text: str) -> dict:
    """Stop-word pruner: remove filler words and replace with NEX compact notation."""
    STOP = {"the","a","an","in","it","of","and","or","that","this","was","are","for","on",
            "at","be","by","with","as","we","you","i","he","she","they","to","is","been","have","had","has"}
    words = text.split()
    pruned = [w for w in words if w.lower().rstrip('.,!?') not in STOP]
    return {"success": True, "result": " ".join(pruned)}

def _chunk_summarizer(text: str) -> dict:
    """Chunk: split into 100-word blocks, keep first 2 sentences of each — lossless structure."""
    words = text.split()
    chunks = [words[i:i+100] for i in range(0, len(words), 100)]
    result_parts = []
    for chunk in chunks:
        chunk_text = " ".join(chunk)
        sents = re.split(r'(?<=[.!?])\s+', chunk_text)
        result_parts.append(" ".join(sents[:2]))
    return {"success": True, "result": " ".join(result_parts)}

def _redundancy_eliminator(text: str) -> dict:
    """Redundancy: removes near-duplicate sentences (>70% word overlap)."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    unique = []
    seen_sets = []
    for sent in sentences:
        words = set(re.findall(r'\b\w+\b', sent.lower()))
        is_dup = any(
            len(words & seen) / max(1, len(words | seen)) > 0.7
            for seen in seen_sets
        )
        if not is_dup:
            unique.append(sent)
            seen_sets.append(words)
    return {"success": True, "result": " ".join(unique)}


_ALGORITHMS = {
    # code algorithms
    "ast":       (_ast_prune, "Python AST Pruner"),
    "regex":     (_regex_prune, "Regex Comment Stripper"),
    "minifier":  (_minifier, "Python Minifier"),
    "dead_code": (_dead_code_eliminator, "Dead Code Eliminator"),
    "whitespace":(_whitespace_compressor, "Whitespace Compressor"),
    # text algorithms
    "nex_s1":    (_nex_s1_prune, "NEX S1 Semantic Density Filter"),
    "tfidf":     (_tfidf_extractor, "TF-IDF Sentence Extractor"),
    "stopword":  (_stopword_pruner, "Stop-word Pruner"),
    "chunk":     (_chunk_summarizer, "Chunk Summarizer"),
    "redundancy":(_redundancy_eliminator, "Redundancy Eliminator"),
    "none":      (None, "None (bypass)"),
}


def _decide_tier(text: str, threshold_tokens: int) -> dict:
    token_count = _estimate_tokens(text)
    cx_keywords = ["derivative", "integral", "proof", "algorithm", "theorem",
                   "multi-step", "explain in detail", "synthesize", "complex",
                   "matrix", "differential", "quantum", "tensor", "infer"]
    found = [k for k in cx_keywords if k.lower() in text.lower()]
    tier2 = token_count > threshold_tokens or len(found) > 0
    return {
        "tier": 2 if tier2 else 1,
        "model": "Gemini 1.5 Pro" if tier2 else "DeepSeek V3",
        "token_count": token_count,
        "complexity_signals": found,
        "escalation_reason": (
            f"Token count {token_count} > threshold {threshold_tokens}" if token_count > threshold_tokens
            else f"Complexity signals: {found}" if found
            else "None — standard routing"
        )
    }



import re
import textwrap
import tokenize
import io
import time

def _count_words(text: str) -> int:
    return len(text.split())

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~0.75 words per token or ~4 chars per token."""
    return max(1, int(len(text) / 4))

def _ast_prune(source: str) -> dict:
    """Attempt AST-based pruning on Python source code."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"success": False, "error": str(e), "result": source}
    
    class CommentStripper(ast.NodeTransformer):
        def visit_Expr(self, node):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return None  # Strip docstrings / string constants used as comments
            return node
    
    cleaned = CommentStripper().visit(tree)
    ast.fix_missing_locations(cleaned)
    
    # Unparse back to source
    try:
        pruned_source = ast.unparse(cleaned)
    except Exception:
        pruned_source = source  # Fallback
    
    # Additionally strip inline # comments via tokenize
    tokens_out = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        for tok in tokens:
            if tok.type != tokenize.COMMENT:
                tokens_out.append(tok.string)
    except Exception:
        pass
    
    return {"success": True, "result": pruned_source}

def _regex_prune(source: str) -> dict:
    """Regex-based pruning: removes comments, blank lines, compresses whitespace."""
    result = re.sub(r'#[^\n]*', '', source)           # Remove # comments
    result = re.sub(r'"""[\s\S]*?"""', '', result)    # Remove triple-quoted strings
    result = re.sub(r"'''[\s\S]*?'''", '', result)    # Remove single-quoted docstrings
    result = re.sub(r'\n\s*\n+', '\n', result)         # Collapse blank lines
    result = result.strip()
    return {"success": True, "result": result}

def _nex_s1_prune(text: str) -> dict:
    """Semantic-density pruning: extract key sentences based on heuristics."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    # Keep sentences that are "high signal" (contain verbs/nouns above certain length)
    high_signal = [s for s in sentences if len(s.split()) > 5 and any(
        kw in s.lower() for kw in ["result", "shows", "analysis", "impact", "increase", "decrease", "achieve", "conclude", "found", "data", "value", "cost", "performance", "failure", "success", "model", "api", "token"]
    )]
    if not high_signal:
        high_signal = sentences[:max(1, len(sentences)//2)]
    result = " ".join(high_signal)
    return {"success": True, "result": result}

def _decide_tier(text: str, threshold_tokens: int) -> dict:
    """Cascade routing decision logic."""
    token_count = _estimate_tokens(text)
    complexity_keywords = ["derivative", "integral", "proof", "algorithm", "theorem", "multi-step", "reason why", "explain in detail", "synthesize", "complex", "matrix", "differential", "quantum", "tensor", "infer"]
    found_keywords = [k for k in complexity_keywords if k.lower() in text.lower()]
    forced_tier2 = token_count > threshold_tokens or len(found_keywords) > 0
    return {
        "tier": 2 if forced_tier2 else 1,
        "model": "Gemini 1.5 Pro" if forced_tier2 else "DeepSeek V3",
        "token_count": token_count,
        "complexity_signals": found_keywords,
        "escalation_reason": (
            f"Token count {token_count} > threshold {threshold_tokens}" if token_count > threshold_tokens
            else f"Complexity signals detected: {found_keywords}" if found_keywords
            else "None - standard routing"
        )
    }


from fastapi.responses import JSONResponse
from pydantic import BaseModel

class SimulateRequest(BaseModel):
    input_text: str
    payload_type: str = "code"          # code | text | auto
    compression_algorithm: str = "ast"  # ast | regex | nex_s1 | none
    routing_threshold_tokens: int = 500 # complexity token threshold for tier 2


@router.post("/api/pipeline-simulate", name="dashboard_pipeline_simulate")
async def pipeline_simulate(
    request: Request,
    body: SimulateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    steps = []
    t_start = time.time()
    
    # ── STEP 1: Input analysis
    raw_text = body.input_text.strip()
    raw_tokens = _estimate_tokens(raw_text)
    raw_words = _count_words(raw_text)
    steps.append({
        "step": 1,
        "name": "Input Received",
        "icon": "inbox",
        "details": f"Payload type: `{body.payload_type}` — {raw_words} words / ~{raw_tokens} tokens",
        "status": "success",
        "metrics": {
            "tokens": raw_tokens,
            "chars": len(raw_text),
            "words": raw_words,
        }
    })
    
    # ── STEP 2: Compression
    algorithm_used = body.compression_algorithm
    compressed_text = raw_text
    compression_failed = False
    compression_error = None
    algorithm_label = "None (bypass)"

    # ── Route through the ALGO_REGISTRY ──────────────────────────────────────
    # Import both registries so all algorithm keys work
    from services.gateway.compression.nex_code_compressor import (
        ALGO_REGISTRY as CODE_REGISTRY,
        NEXCodeCompressor,
    )
    from services.gateway.compression.nex_text_compressor import (
        ALGO_REGISTRY as TEXT_REGISTRY,
        NEXTextCompressor,
    )

    payload_type = body.payload_type.lower()

    if algorithm_used and algorithm_used != "none":
        # Determine which registry to consult based on payload type
        if payload_type == "code":
            registry = CODE_REGISTRY
            compressor_cls = NEXCodeCompressor
        else:
            registry = TEXT_REGISTRY
            compressor_cls = NEXTextCompressor

        if algorithm_used in registry:
            # Run through the individual algorithm
            try:
                if payload_type == "code":
                    result_obj = NEXCodeCompressor.compress_with_algo(raw_text, algorithm_used)
                else:
                    result_obj = NEXTextCompressor.compress_with_algo(raw_text, algorithm_used)
                compressed_text = result_obj.compressed
                algorithm_label = registry[algorithm_used]["name"]
            except Exception as e:
                compression_failed = True
                compression_error = f"Algorithm error: {str(e)}"
                algorithm_label = registry.get(algorithm_used, {}).get("name", algorithm_used)

        elif algorithm_used == "full_pipeline":
            # Run the full multi-stage pipeline
            try:
                if payload_type == "code":
                    result_obj = NEXCodeCompressor.compress_input(raw_text)
                else:
                    result_obj = NEXTextCompressor.compress_input(raw_text)
                compressed_text = result_obj.compressed
                algorithm_label = "Full NEX Pipeline"
            except Exception as e:
                compression_failed = True
                compression_error = f"Pipeline error: {str(e)}"
                algorithm_label = "Full NEX Pipeline"

        elif algorithm_used == "extreme_pipeline":
            try:
                if payload_type == "code":
                    result_obj = NEXCodeCompressor.compress_input(raw_text, extreme=True)
                else:
                    result_obj = NEXTextCompressor.compress_input(raw_text, extreme=True)
                compressed_text = result_obj.compressed
                algorithm_label = "Full NEX Extreme Pipeline"
            except Exception as e:
                compression_failed = True
                compression_error = f"Extreme pipeline error: {str(e)}"
                algorithm_label = "Full NEX Extreme Pipeline"

        else:
            # Unknown key — report it clearly
            compression_failed = True
            compression_error = f"Unknown algorithm key: '{algorithm_used}'"
            algorithm_label = algorithm_used


    compressed_tokens = _estimate_tokens(compressed_text)
    tokens_saved = raw_tokens - compressed_tokens
    reduction_pct = round((tokens_saved / raw_tokens * 100) if raw_tokens > 0 else 0, 1)
    
    if algorithm_used != "none":
        steps.append({
            "step": 2,
            "name": f"Payload Compression — {algorithm_label}",
            "icon": "compress",
            "status": "warning" if compression_failed else "success",
            "details": compression_error if compression_failed else f"{raw_tokens} → {compressed_tokens} tokens saved ({reduction_pct}% reduction)",
            "metrics": {
                "tokens_before": raw_tokens,
                "tokens_after": compressed_tokens,
                "tokens_saved": tokens_saved,
                "reduction_pct": reduction_pct,
                "algorithm": algorithm_label,
            },
            "diff": {
                "before": raw_text[:600] + ("…" if len(raw_text) > 600 else ""),
                "after": compressed_text[:600] + ("…" if len(compressed_text) > 600 else ""),
            }
        })
    
    # ── STEP 3: Cascade Routing Decision
    routing = _decide_tier(compressed_text, body.routing_threshold_tokens)
    steps.append({
        "step": 3,
        "name": "Cascade Routing Decision",
        "icon": "route",
        "status": "warning" if routing["tier"] == 2 else "success",
        "details": f"Tier {routing['tier']} selected → {routing['model']}. Reason: {routing['escalation_reason']}",
        "metrics": {
            "tier": routing["tier"],
            "model": routing["model"],
            "token_count": routing["token_count"],
            "complexity_signals": routing["complexity_signals"],
            "threshold": body.routing_threshold_tokens,
        }
    })
    
    # ── STEP 4: Simulated Dispatch
    elapsed_ms = round((time.time() - t_start) * 1000, 2)
    estimated_cost_usd = round(compressed_tokens * (0.000002 if routing["tier"] == 2 else 0.0000005), 6)
    
    steps.append({
        "step": 4,
        "name": "Payload Dispatch & Telemetry",
        "icon": "send",
        "status": "success",
        "details": f"Dispatched to {routing['model']} — estimated cost: ${estimated_cost_usd} — pipeline latency: {elapsed_ms}ms",
        "metrics": {
            "model": routing["model"],
            "estimated_cost_usd": estimated_cost_usd,
            "pipeline_latency_ms": elapsed_ms,
            "payload_tokens": compressed_tokens,
        }
    })
    
    # ── Write to AuditLog so it appears in dashboard ──────────────────────────────
    from decimal import Decimal
    try:
        from models.dashboard import AuditLog as _AuditLog
        audit = _AuditLog(
            organization_id=user.organization_id,
            original_payload=raw_text[:4000],
            compressed_payload=compressed_text[:4000],
            deepseek_response="",
            final_response="",
            tokens_original=raw_tokens,
            tokens_compressed=compressed_tokens,
            tokens_response=0,
            compression_ratio=reduction_pct,
            cost_original=Decimal(str(round(raw_tokens * 0.0000005, 8))),
            cost_actual=Decimal(str(estimated_cost_usd)),
            cost_saved=Decimal(str(round(max(0, raw_tokens - compressed_tokens) * 0.0000005, 8))),
            latency_ms=int(elapsed_ms),
            status="success",
            source="simulate",
            data_bytes_in=len(raw_text.encode()),
            data_bytes_out=len(compressed_text.encode()),
        )
        db.add(audit)
        await db.commit()
    except Exception:
        await db.rollback()

    return JSONResponse({
        "success": True,
        "steps": steps,
        "summary": {
            "raw_tokens": raw_tokens,
            "processed_tokens": compressed_tokens,
            "tokens_saved": tokens_saved,
            "reduction_pct": reduction_pct,
            "algorithm_used": algorithm_label if algorithm_used != "none" else "None",
            "model_selected": routing["model"],
            "tier": routing["tier"],
            "estimated_cost_usd": estimated_cost_usd,
        }
    })



# ─────────────────────────────────────────────
# Colour palette  —  monochrome + single accent
# ─────────────────────────────────────────────
INK        = colors.HexColor("#0d0d0d")   # near-black for body text
INK_LIGHT  = colors.HexColor("#4a4a4a")   # secondary text
RULE       = colors.HexColor("#d0d0d0")   # hairlines & borders
BG_ROW     = colors.HexColor("#f5f5f5")   # alternate table row
BG_HEADER  = colors.HexColor("#1a1a1a")   # table header fill
ACCENT     = colors.HexColor("#1a56a0")   # single blue accent
ACCENT_DIM = colors.HexColor("#e8eef7")   # very pale accent for bands
WHITE      = colors.white

PAGE_W, PAGE_H = A4
MARGIN         = 20 * mm
CONTENT_W      = PAGE_W - 2 * MARGIN


# ─────────────────────────────────────────────
# Typography helpers
# ─────────────────────────────────────────────
def _style(name, font="Helvetica", size=9, color=INK,
           leading=13, align=TA_LEFT, bold=False):
    return ParagraphStyle(
        name,
        fontName="Helvetica-Bold" if bold else font,
        fontSize=size,
        textColor=color,
        leading=leading,
        alignment=align,
    )

STYLE_NOTE = _style("note", size=7.5, color=INK_LIGHT, align=TA_CENTER, leading=11)


# ─────────────────────────────────────────────
# Custom Flowables
# ─────────────────────────────────────────────
class PageHeader(Flowable):
    """
    Clean two-row header:
    Row 1 — black bar with org name (white) + right-aligned report type label
    Row 2 — large document title + 2 pt accent rule
    """
    def __init__(self, org_name, width):
        super().__init__()
        self.org_name = org_name
        self.width    = width
        self.height   = 48

    def wrap(self, *args):
        return self.width, self.height

    def draw(self):
        c = self.canv
        w = self.width

        # Top black bar
        c.setFillColor(BG_HEADER)
        c.rect(0, 32, w, 16, fill=1, stroke=0)

        # Org name (left)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(0, 37, self.org_name.upper())

        # Report type label (right)
        c.setFillColor(colors.HexColor("#888888"))
        c.setFont("Helvetica", 7.5)
        c.drawRightString(w, 37, "KI-NUTZUNGSBERICHT / AI USAGE REPORT")

        # Large title
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 22)
        c.drawString(0, 8, "Analytics Report")

        # Short accent rule under title
        c.setStrokeColor(ACCENT)
        c.setLineWidth(2)
        c.line(0, 5, 60, 5)


class MetaRow(Flowable):
    """Single horizontal strip of N labelled meta fields."""
    def __init__(self, fields, width):
        super().__init__()
        self.fields = fields   # list of (label, value)
        self.width  = width
        self.height = 22

    def wrap(self, *args):
        return self.width, self.height

    def draw(self):
        c   = self.canv
        w   = self.width
        col = w / len(self.fields)

        c.setStrokeColor(RULE)
        c.setLineWidth(0.4)
        c.rect(0, 0, w, self.height, fill=0, stroke=1)

        for i, (label, value) in enumerate(self.fields):
            x = i * col
            if i > 0:
                c.setStrokeColor(RULE)
                c.setLineWidth(0.4)
                c.line(x, 0, x, self.height)

            c.setFillColor(INK_LIGHT)
            c.setFont("Helvetica", 6.5)
            c.drawString(x + 6, 14, label.upper())

            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 8.5)
            c.drawString(x + 6, 4, value)


class KPIRow(Flowable):
    """
    Borderless row of KPI cells separated by vertical hairlines.
    Accented cells get a 2 pt top stripe.
    """
    def __init__(self, kpis, width):
        super().__init__()
        self.kpis  = kpis   # list of (label, value, accent: bool)
        self.width = width
        self.height = 44

    def wrap(self, *args):
        return self.width, self.height

    def draw(self):
        c   = self.canv
        n   = len(self.kpis)
        col = self.width / n

        # Outer border
        c.setStrokeColor(RULE)
        c.setLineWidth(0.4)
        c.rect(0, 0, self.width, self.height, fill=0, stroke=1)

        for i, (label, value, use_accent) in enumerate(self.kpis):
            x = i * col

            # Column divider
            if i > 0:
                c.setStrokeColor(RULE)
                c.setLineWidth(0.4)
                c.line(x, 0, x, self.height)

            # Accent top stripe
            if use_accent:
                c.setFillColor(ACCENT)
                c.rect(x, self.height - 2, col, 2, fill=1, stroke=0)

            # Value
            val_font_size = 16 if len(value) <= 8 else 13
            c.setFillColor(ACCENT if use_accent else INK)
            c.setFont("Helvetica-Bold", val_font_size)
            c.drawString(x + 8, 20, value)

            # Label
            c.setFillColor(INK_LIGHT)
            c.setFont("Helvetica", 7)
            c.drawString(x + 8, 7, label.upper())


class SectionTitle(Flowable):
    """Section heading with a 3 pt left accent bar."""
    def __init__(self, text, width):
        super().__init__()
        self.text  = text
        self.width = width
        self.height = 16

    def wrap(self, *args):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(ACCENT)
        c.rect(0, 0, 3, self.height, fill=1, stroke=0)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(9, 4, self.text)


# ─────────────────────────────────────────────
# Table builders
# ─────────────────────────────────────────────
def _table(data, col_widths, align_right_from=1):
    """Minimal table: dark header, hairline grid, zebra rows."""
    n_cols = len(data[0])
    align_cmds = [
        ("ALIGN", (col, 0), (col, -1), "RIGHT")
        for col in range(align_right_from, n_cols)
    ]

    style = TableStyle([
        # Header
        ("BACKGROUND",    (0, 0), (-1, 0), BG_HEADER),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 8),
        ("TOPPADDING",    (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ("LEFTPADDING",   (0, 0), (-1, 0), 8),
        ("RIGHTPADDING",  (0, 0), (-1, 0), 8),
        # Body
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8.5),
        ("TOPPADDING",    (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("LEFTPADDING",   (0, 1), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 1), (-1, -1), 8),
        ("TEXTCOLOR",     (0, 1), (-1, -1), INK),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, BG_ROW]),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, RULE),
        ("LINEAFTER",     (0, 0), (-1, -1), 0,   WHITE),
        ("BOX",           (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        *align_cmds,
    ])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(style)
    return t


def _summary_table(metrics):
    """Two-column key/value table for executive summary."""
    data = [["KENNZAHL / METRIC", "WERT / VALUE"]]
    for label, value in metrics:
        data.append([label, value])

    style = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), BG_HEADER),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 8),
        ("TOPPADDING",    (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ("LEFTPADDING",   (0, 0), (-1, 0), 8),
        ("RIGHTPADDING",  (0, 0), (-1, 0), 8),
        # Label col
        ("FONTNAME",      (0, 1), (0, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (0, -1), 8.5),
        ("TEXTCOLOR",     (0, 1), (0, -1), INK_LIGHT),
        # Value col
        ("FONTNAME",      (1, 1), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE",      (1, 1), (1, -1), 9),
        ("TEXTCOLOR",     (1, 1), (1, -1), INK),
        ("ALIGN",         (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING",    (0, 1), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 7),
        ("LEFTPADDING",   (0, 1), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 1), (-1, -1), 8),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, BG_ROW]),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, RULE),
        ("BOX",           (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ])
    t = Table(data,
              colWidths=[CONTENT_W * 0.62, CONTENT_W * 0.38],
              repeatRows=1)
    t.setStyle(style)
    return t


# ─────────────────────────────────────────────
# Bar chart
# ─────────────────────────────────────────────
def _bar_chart(labels, values, caption="", width=CONTENT_W, height=100):
    d  = Drawing(width, height + 28)
    bc = VerticalBarChart()
    bc.x      = 36
    bc.y      = 22
    bc.width  = width - 52
    bc.height = height

    bc.data        = [values]
    bc.strokeColor = None

    bc.bars[0].fillColor   = ACCENT
    bc.bars[0].strokeColor = None

    bc.valueAxis.valueMin            = 0
    bc.valueAxis.labelTextFormat     = "%d"
    bc.valueAxis.labels.fontSize     = 7
    bc.valueAxis.labels.fillColor    = INK_LIGHT
    bc.valueAxis.labels.fontName     = "Helvetica"
    bc.valueAxis.gridStrokeColor     = RULE
    bc.valueAxis.gridStrokeDashArray = [2, 3]
    bc.valueAxis.strokeColor         = RULE

    bc.categoryAxis.categoryNames    = labels
    bc.categoryAxis.labels.fontSize  = 7
    bc.categoryAxis.labels.fillColor = INK_LIGHT
    bc.categoryAxis.labels.fontName  = "Helvetica"
    bc.categoryAxis.labels.angle     = 15 if len(labels) > 5 else 0
    bc.categoryAxis.strokeColor      = RULE
    bc.categoryAxis.gridStrokeColor  = None

    d.add(bc)

    if caption:
        d.add(String(width / 2, 4, caption,
                     fontSize=7, fillColor=INK_LIGHT,
                     fontName="Helvetica", textAnchor="middle"))
    return d


# ─────────────────────────────────────────────
# Page callbacks
# ─────────────────────────────────────────────
def _draw_footer(canvas, doc):
    canvas.saveState()
    y = 10
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN, y + 9, PAGE_W - MARGIN, y + 9)
    canvas.setFillColor(INK_LIGHT)
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(MARGIN, y, "Vertraulich · Nur für internen Gebrauch")
    canvas.drawCentredString(
        PAGE_W / 2, y,
        f"Firma-KI Analytics Report  ·  {datetime.utcnow().strftime('%d.%m.%Y')}"
    )
    canvas.drawRightString(PAGE_W - MARGIN, y, f"Seite {doc.page}")
    canvas.restoreState()


def _first_page(canvas, doc):
    _draw_footer(canvas, doc)


def _later_pages(canvas, doc):
    canvas.saveState()
    y = PAGE_H - 14
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN, y, PAGE_W - MARGIN, y)
    canvas.setFillColor(INK_LIGHT)
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(MARGIN, y + 2, "Firma-KI  ·  Analytics Report")
    canvas.drawRightString(PAGE_W - MARGIN, y + 2,
                           datetime.utcnow().strftime("%d.%m.%Y"))
    canvas.restoreState()
    _draw_footer(canvas, doc)


# ─────────────────────────────────────────────
# Route
# ─────────────────────────────────────────────
@router.get("/export/analytics-report", name="dashboard_export_analytics")
async def export_analytics_report(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = 30,
):
    if not current_user:
        return RedirectResponse(url="/login")

    since = datetime.utcnow() - timedelta(days=days)
    stmt  = (
        select(AuditLog)
        .options(selectinload(AuditLog.ai_provider), selectinload(AuditLog.api_key))
        .where(
            AuditLog.organization_id == current_user.organization_id,
            AuditLog.timestamp >= since,
        )
        .order_by(desc(AuditLog.timestamp))
    )
    res  = await db.execute(stmt)
    logs = res.scalars().all()

    # ── Aggregates ──────────────────────────────────────────
    total_reqs       = len(logs)
    total_in         = sum((l.tokens_original  or 0) for l in logs)
    total_out        = sum((l.tokens_compressed or 0) for l in logs)
    total_saved      = total_in - total_out
    total_cost       = sum(float(l.cost_actual or 0) for l in logs)
    total_cost_saved = sum(float(l.cost_saved  or 0) for l in logs)
    savings_pct      = (total_saved / total_in * 100) if total_in else 0.0

    prov_stats: dict = {}
    for l in logs:
        p = l.ai_provider.name if l.ai_provider else "Unbekannt"
        prov_stats.setdefault(p, {"reqs": 0, "tok": 0, "cost": 0.0})
        prov_stats[p]["reqs"] += 1
        prov_stats[p]["tok"]  += l.tokens_compressed or l.tokens_original or 0
        prov_stats[p]["cost"] += float(l.cost_actual or 0)

    key_stats: dict = {}
    for l in logs:
        k = l.api_key.name if l.api_key else "Unbekannt"
        key_stats.setdefault(k, {"reqs": 0, "cost": 0.0})
        key_stats[k]["reqs"] += 1
        key_stats[k]["cost"] += float(l.cost_actual or 0)

    org_name = (current_user.organization.name
                if current_user.organization else "Eigenständig")

    # ── Build PDF ────────────────────────────────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title="Firma-KI Analytics Report",
        author=current_user.email,
        subject=f"KI-Nutzungsbericht – letzte {days} Tage",
    )

    story = []

    # 1 · Header
    story.append(PageHeader(org_name, CONTENT_W))
    story.append(Spacer(1, 8))

    # 2 · Meta strip
    story.append(MetaRow(
        fields=[
            ("Erstellt am",      datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC")),
            ("Angefordert von",  current_user.email),
            ("Berichtszeitraum", f"Letzte {days} Tage"),
        ],
        width=CONTENT_W,
    ))
    story.append(Spacer(1, 14))

    # 3 · KPI strip
    story.append(KPIRow(
        kpis=[
            ("API-Anfragen gesamt", f"{total_reqs:,}",          True),
            ("Token Input",         f"{total_in:,}",            False),
            ("Token eingespart",    f"{total_saved:,}",         True),
            ("Einsparung",          f"{savings_pct:.1f} %",     False),
            ("Gesamtkosten",        f"${total_cost:.4f}",       False),
            ("Kostenersparnis",     f"${total_cost_saved:.4f}", True),
        ],
        width=CONTENT_W,
    ))
    story.append(Spacer(1, 20))

    # 4 · Executive Summary
    story.append(SectionTitle("Zusammenfassung / Executive Summary", CONTENT_W))
    story.append(Spacer(1, 6))
    story.append(KeepTogether([_summary_table([
        ("API-Anfragen gesamt",               f"{total_reqs:,}"),
        ("Token Input gesamt",                f"{total_in:,}"),
        ("Token an LLM weitergeleitet",       f"{total_out:,}"),
        ("Token eingespart durch Firma-KI",   f"{total_saved:,}  ({savings_pct:.1f} %)"),
        ("Gesamtkosten (USD)",                f"${total_cost:.6f}"),
        ("Kostenersparnis generiert (USD)",   f"${total_cost_saved:.6f}"),
    ])]))
    story.append(Spacer(1, 22))

    # 5 · Provider Metrics
    story.append(SectionTitle("Anbieterübersicht / Provider Metrics", CONTENT_W))
    story.append(Spacer(1, 6))

    prov_data = [["ANBIETER", "ANFRAGEN", "TOKEN VERARBEITET", "KOSTEN (USD)"]]
    for p, st in prov_stats.items():
        prov_data.append([p, f"{st['reqs']:,}", f"{st['tok']:,}", f"${st['cost']:.4f}"])

    story.append(KeepTogether([_table(prov_data, [
        CONTENT_W * 0.30,
        CONTENT_W * 0.18,
        CONTENT_W * 0.28,
        CONTENT_W * 0.24,
    ])]))
    story.append(Spacer(1, 10))

    if prov_stats:
        story.append(_bar_chart(
            list(prov_stats.keys()),
            [st["reqs"] for st in prov_stats.values()],
            caption="API-Anfragen pro Anbieter",
        ))
    story.append(Spacer(1, 22))

    # 6 · API Key Usage
    story.append(SectionTitle("API-Schlüssel Nutzung / API Key Usage", CONTENT_W))
    story.append(Spacer(1, 6))

    key_data = [["API-SCHLÜSSEL", "ANFRAGEN", "KOSTEN (USD)"]]
    for k, st in key_stats.items():
        key_data.append([k, f"{st['reqs']:,}", f"${st['cost']:.4f}"])

    story.append(KeepTogether([_table(key_data, [
        CONTENT_W * 0.55,
        CONTENT_W * 0.22,
        CONTENT_W * 0.23,
    ])]))
    story.append(Spacer(1, 28))

    # 7 · Closing note
    story.append(HRFlowable(width=CONTENT_W, color=RULE, thickness=0.4))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        f"Dieser Bericht ist vertraulich und ausschließlich für autorisierte Mitarbeiter "
        f"der {org_name} bestimmt. Alle Token- und Kostendaten stammen aus den Firma-KI "
        f"Audit-Protokollen für den Zeitraum bis zum "
        f"{datetime.utcnow().strftime('%d.%m.%Y %H:%M UTC')}.",
        STYLE_NOTE,
    ))

    doc.build(story, onFirstPage=_first_page, onLaterPages=_later_pages)

    buf.seek(0)
    filename = f"FirmaKI_Analytics_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )