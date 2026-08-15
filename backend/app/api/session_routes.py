from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

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


def get_session_or_404(db: Session, session_id: int):
    session = load_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="实训会话不存在")
    return session


@router.post("", response_model=TeachingSessionDetailRead)
def create_session(
    request: SessionCreateRequest,
    db: Session = Depends(db_session),
) -> TeachingSessionDetailRead:
    try:
        session = create_or_reuse_session(db, request.scenario_id, request.virtual_student_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return build_session_detail(session)


@router.get("/history", response_model=list[SessionHistoryItemRead])
def get_session_history(
    db: Session = Depends(db_session),
) -> list[SessionHistoryItemRead]:
    return list_session_history(db)


@router.get("/{session_id}", response_model=TeachingSessionDetailRead)
def get_session(
    session_id: int,
    db: Session = Depends(db_session),
) -> TeachingSessionDetailRead:
    return build_session_detail(get_session_or_404(db, session_id))


@router.post("/{session_id}/messages", response_model=TeachingSessionDetailRead)
def send_message(
    session_id: int,
    request: SessionMessageRequest,
    db: Session = Depends(db_session),
    client: LLMClient = Depends(llm_client_dependency),
) -> TeachingSessionDetailRead:
    session = get_session_or_404(db, session_id)
    if session.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="实训已结束，不能继续发送消息")
    try:
        return send_teacher_message(db, session, request.teacher_text, client)
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
    client: LLMClient = Depends(llm_client_dependency),
) -> TeachingSessionDetailRead:
    return end_session(db, get_session_or_404(db, session_id), client)


@router.get("/{session_id}/evaluation", response_model=EvaluationReportRead)
def get_evaluation(
    session_id: int,
    db: Session = Depends(db_session),
) -> EvaluationReportRead:
    session = get_session_or_404(db, session_id)
    if session.evaluation is None or session.evaluation.narrative is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="教学评价尚未生成")
    return EvaluationEngine.to_read(session.evaluation, session.evaluation.narrative)


@router.post("/{session_id}/evaluation", response_model=EvaluationReportRead)
def create_evaluation(
    session_id: int,
    db: Session = Depends(db_session),
    client: LLMClient = Depends(llm_client_dependency),
) -> EvaluationReportRead:
    session = get_session_or_404(db, session_id)
    if session.status != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先结束实训再生成评价")
    return EvaluationEngine().evaluate_and_save(db, session, client)
