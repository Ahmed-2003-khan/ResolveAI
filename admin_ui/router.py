import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db import get_session
from app.models.audit_log import AuditLog
from app.models.conversation import Conversation
from app.models.kb_chunk import KBChunk
from app.models.message import Message

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="admin_ui/templates")
security = HTTPBasic()


def check_auth(credentials: Annotated[HTTPBasicCredentials, Depends(security)]) -> str:
    settings = get_settings()
    ok_user = secrets.compare_digest(
        credentials.username.encode(), settings.admin_username.encode()
    )
    ok_pass = secrets.compare_digest(
        credentials.password.encode(), settings.admin_password.encode()
    )
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


Authenticated = Annotated[str, Depends(check_auth)]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/")
async def admin_index(_: Authenticated) -> RedirectResponse:
    return RedirectResponse(url="/admin/conversations")


@router.get("/conversations", response_class=HTMLResponse)
async def conversations_list(
    request: Request,
    _: Authenticated,
    db: Session,
    status_filter: str = "",
    page: int = 1,
) -> HTMLResponse:
    page_size = 50
    offset = (page - 1) * page_size

    q = select(Conversation).order_by(desc(Conversation.last_activity))
    if status_filter:
        q = q.where(Conversation.status == status_filter)

    conversations = (await db.execute(q.offset(offset).limit(page_size))).scalars().all()

    # Per-conversation message counts
    mc_q = select(Message.conversation_id, func.count(Message.id).label("cnt")).group_by(
        Message.conversation_id
    )
    msg_counts = {r.conversation_id: r.cnt for r in (await db.execute(mc_q)).all()}

    count_q = select(func.count(Conversation.id))
    if status_filter:
        count_q = count_q.where(Conversation.status == status_filter)
    total = (await db.execute(count_q)).scalar_one()

    return templates.TemplateResponse(
        "conversations.html",
        {
            "request": request,
            "conversations": conversations,
            "msg_counts": msg_counts,
            "status_filter": status_filter,
            "page": page,
            "page_size": page_size,
            "total": total,
        },
    )


@router.get("/conversations/{conv_id}", response_class=HTMLResponse)
async def conversation_detail(
    request: Request,
    conv_id: str,
    _: Authenticated,
    db: Session,
) -> HTMLResponse:
    try:
        conv_uuid = uuid.UUID(conv_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc

    conv = await db.get(Conversation, conv_uuid)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs_q = select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)
    messages = (await db.execute(msgs_q)).scalars().all()

    audit_q = (
        select(AuditLog)
        .where(AuditLog.conversation_id == conv.id)
        .order_by(AuditLog.created_at)
    )
    audit_logs = (await db.execute(audit_q)).scalars().all()

    return templates.TemplateResponse(
        "conversation_detail.html",
        {
            "request": request,
            "conv": conv,
            "messages": messages,
            "audit_logs": audit_logs,
        },
    )


@router.get("/kb", response_class=HTMLResponse)
async def kb_list(
    request: Request,
    _: Authenticated,
    db: Session,
    q: str = "",
    source_type: str = "",
    page: int = 1,
) -> HTMLResponse:
    page_size = 30
    offset = (page - 1) * page_size

    query = select(KBChunk).order_by(desc(KBChunk.last_updated))
    if q:
        query = query.where(KBChunk.content.ilike(f"%{q}%"))
    if source_type:
        query = query.where(KBChunk.source_type == source_type)

    chunks = (await db.execute(query.offset(offset).limit(page_size))).scalars().all()

    count_q = select(func.count(KBChunk.id))
    if q:
        count_q = count_q.where(KBChunk.content.ilike(f"%{q}%"))
    if source_type:
        count_q = count_q.where(KBChunk.source_type == source_type)
    total = (await db.execute(count_q)).scalar_one()

    st_q = select(KBChunk.source_type).distinct().where(KBChunk.source_type.isnot(None))
    source_types = [r[0] for r in (await db.execute(st_q)).all()]

    return templates.TemplateResponse(
        "kb_manager.html",
        {
            "request": request,
            "chunks": chunks,
            "q": q,
            "source_type": source_type,
            "source_types": source_types,
            "page": page,
            "page_size": page_size,
            "total": total,
        },
    )


@router.post("/kb")
async def kb_create(
    _: Authenticated,
    db: Session,
    source_id: Annotated[str, Form()],
    source_type: Annotated[str, Form()],
    title: Annotated[str, Form()],
    content: Annotated[str, Form()],
    product_area: Annotated[str, Form()] = "",
    language: Annotated[str, Form()] = "en",
) -> RedirectResponse:
    chunk = KBChunk(
        source_id=source_id,
        source_type=source_type,
        title=title,
        content=content,
        product_area=product_area or None,
        language=language,
    )
    db.add(chunk)
    await db.commit()
    return RedirectResponse(url="/admin/kb", status_code=303)


@router.delete("/kb/{chunk_id}", response_class=HTMLResponse)
async def kb_delete(
    chunk_id: str,
    _: Authenticated,
    db: Session,
) -> HTMLResponse:
    try:
        chunk_uuid = uuid.UUID(chunk_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Chunk not found") from exc

    chunk = await db.get(KBChunk, chunk_uuid)
    if chunk:
        await db.delete(chunk)
        await db.commit()
    return HTMLResponse(content="", status_code=200)


@router.get("/metrics", response_class=HTMLResponse)
async def metrics_summary(
    request: Request,
    _: Authenticated,
    db: Session,
) -> HTMLResponse:
    # Conversation status breakdown
    conv_q = select(Conversation.status, func.count(Conversation.id).label("cnt")).group_by(
        Conversation.status
    )
    conv_stats = {r.status: r.cnt for r in (await db.execute(conv_q)).all()}

    # Message direction breakdown
    msg_q = select(Message.direction, func.count(Message.id).label("cnt")).group_by(
        Message.direction
    )
    msg_stats = {r.direction: r.cnt for r in (await db.execute(msg_q)).all()}

    # Channel breakdown
    channel_q = select(Conversation.channel, func.count(Conversation.id).label("cnt")).group_by(
        Conversation.channel
    )
    channel_stats = {r.channel: r.cnt for r in (await db.execute(channel_q)).all()}

    # Per-node audit stats
    audit_q = (
        select(
            AuditLog.node_name,
            func.count(AuditLog.id).label("calls"),
            func.avg(AuditLog.latency_ms).label("avg_latency_ms"),
            func.sum(AuditLog.cost_usd).label("total_cost_usd"),
        )
        .where(AuditLog.node_name.isnot(None))
        .group_by(AuditLog.node_name)
        .order_by(desc("calls"))
    )
    audit_stats = (await db.execute(audit_q)).all()

    total_cost = (await db.execute(select(func.sum(AuditLog.cost_usd)))).scalar_one() or 0
    kb_count = (await db.execute(select(func.count(KBChunk.id)))).scalar_one()

    return templates.TemplateResponse(
        "metrics.html",
        {
            "request": request,
            "conv_stats": conv_stats,
            "msg_stats": msg_stats,
            "channel_stats": channel_stats,
            "audit_stats": audit_stats,
            "total_cost": float(total_cost),
            "kb_count": kb_count,
        },
    )
