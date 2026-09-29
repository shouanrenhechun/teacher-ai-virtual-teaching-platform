from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import select, update, func, text
from ..models import TeachingSession
from .identity import practice_owner

from ..schemas.evaluation import EvaluationReportRead
from ..schemas.session import (
    SessionCreateRequest,
    SessionHistoryItemRead,
    SessionMessageRequest,
    TeachingSessionDetailRead,
)
from ..services.llm import LLMClient
from ..services.llm.base import LLMConfigurationError, LLMServiceError
from ..services.session_service import (
    SessionConflict,
    build_session_detail,
    create_or_reuse_session,
    end_session,
    load_session,
    list_session_history,
    send_teacher_message,
)
from ..services.evaluation_engine import EvaluationEngine
from .deps import db_session
from .llm_routes import llm_client_dependency


router = APIRouter(prefix="/api/sessions", tags=["teaching-sessions"])


def get_session_or_404(db: Session, session_id: int, owner_hash: str):
    session = load_session(db, session_id)
    if session is None or session.owner_hash != owner_hash:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="实训会话不存在")
    return session


@router.post("", response_model=TeachingSessionDetailRead)
def create_session(
    request: SessionCreateRequest,
    db: Session = Depends(db_session),
    owner_hash: str = Depends(practice_owner),
) -> TeachingSessionDetailRead:
    try:
        session = create_or_reuse_session(db, request.scenario_id, request.virtual_student_id, owner_hash)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return build_session_detail(session)


@router.get('/history')
def get_session_history(db: Session = Depends(db_session), owner_hash: str = Depends(practice_owner),
    page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), student_id: int | None = Query(None, gt=0)):
    return list_session_history(db, owner_hash, page=page, page_size=page_size, student_id=student_id)


@router.get('/growth')
def get_growth(db: Session = Depends(db_session), owner_hash: str = Depends(practice_owner),
    student_id: int | None = Query(None, gt=0), rubric_version: int = Query(2, ge=1, le=2)):
    return list_session_history(db, owner_hash, page_size=20, student_id=student_id, rubric_version=rubric_version)['items']


@router.get('/legacy-count')
def legacy_count(db: Session = Depends(db_session), owner_hash: str = Depends(practice_owner)):
    return {'count': db.scalar(select(func.count()).select_from(TeachingSession).where(TeachingSession.owner_hash.is_(None))) or 0}


@router.post('/import-legacy')
def import_legacy(request: Request, db: Session = Depends(db_session), owner_hash: str = Depends(practice_owner)):
    if request.client and request.client.host not in {'127.0.0.1', '::1', 'testclient'}:
        raise HTTPException(status_code=403, detail='旧记录只能在本机导入')
    db.execute(text('BEGIN IMMEDIATE'))
    result = db.execute(update(TeachingSession).where(TeachingSession.owner_hash.is_(None)).values(owner_hash=owner_hash))
    db.commit()
    return {'imported': result.rowcount}


@router.get("/{session_id}", response_model=TeachingSessionDetailRead)
def get_session(
    session_id: int,
    db: Session = Depends(db_session),
    owner_hash: str = Depends(practice_owner),
) -> TeachingSessionDetailRead:
    return build_session_detail(get_session_or_404(db, session_id, owner_hash))


@router.post("/{session_id}/messages", response_model=TeachingSessionDetailRead)
def send_message(
    session_id: int,
    request: SessionMessageRequest,
    db: Session = Depends(db_session),
    owner_hash: str = Depends(practice_owner),
    client: LLMClient = Depends(llm_client_dependency),
) -> TeachingSessionDetailRead:
    session = get_session_or_404(db, session_id, owner_hash)
    try:
        return send_teacher_message(db, session, request.teacher_text, client, request.request_id, request.expected_version)
    except SessionConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LLMConfigurationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except LLMServiceError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/{session_id}/end", response_model=TeachingSessionDetailRead)
def finish_session(
    session_id: int,
    db: Session = Depends(db_session),
    owner_hash: str = Depends(practice_owner),
    client: LLMClient = Depends(llm_client_dependency),
) -> TeachingSessionDetailRead:
    try:
        return end_session(db, get_session_or_404(db, session_id, owner_hash), client)
    except SessionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{session_id}/evaluation", response_model=EvaluationReportRead)
def get_evaluation(
    session_id: int,
    db: Session = Depends(db_session),
    owner_hash: str = Depends(practice_owner),
) -> EvaluationReportRead:
    session = get_session_or_404(db, session_id, owner_hash)
    if session.evaluation is None or session.evaluation.narrative is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="教学评价尚未生成")
    return EvaluationEngine.to_read(session.evaluation, session.evaluation.narrative)


@router.post("/{session_id}/evaluation", response_model=EvaluationReportRead)
def create_evaluation(
    session_id: int,
    db: Session = Depends(db_session),
    owner_hash: str = Depends(practice_owner),
    client: LLMClient = Depends(llm_client_dependency),
) -> EvaluationReportRead:
    session = get_session_or_404(db, session_id, owner_hash)
    if session.status != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先结束实训再生成评价")
    return EvaluationEngine().evaluate_and_save(db, session, client)
