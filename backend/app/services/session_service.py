from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .evaluation_engine import EvaluationEngine
from .llm import LLMClient, LLMContext
from .teaching_behavior import TeachingBehaviorAnalyzer
from .virtual_student import StudentProfile, VirtualStudentEngine
from ..models import (
    DialogueRecord,
    Evaluation,
    TeachingBehaviorRecord,
    TeachingSession,
    TrainingScenario,
    VirtualStudent,
)
from ..schemas.session import (
    SessionHistoryItemRead,
    SessionStateRead,
    TeachingSessionDetailRead,
)
from ..schemas.teaching_behavior import TeachingBehaviorSummaryRead


def load_session(db: Session, session_id: int) -> TeachingSession | None:
    statement = (
        select(TeachingSession)
        .where(TeachingSession.id == session_id)
        .options(
            selectinload(TeachingSession.scenario),
            selectinload(TeachingSession.virtual_student).selectinload(
                VirtualStudent.knowledge_states
            ),
            selectinload(TeachingSession.dialogue_records),
            selectinload(TeachingSession.behavior_records),
            selectinload(TeachingSession.evaluation).selectinload(Evaluation.narrative),
        )
    )
    return db.scalar(statement)


def load_engine(session: TeachingSession) -> VirtualStudentEngine:
    profile = StudentProfile.from_record(session.virtual_student)
    engine = VirtualStudentEngine(profile)
    for record in sorted(session.dialogue_records, key=lambda item: item.sequence):
        if record.speaker == "teacher":
            engine.update_from_teacher_text(record.content)
    return engine


def build_session_detail(
    session: TeachingSession, engine: VirtualStudentEngine | None = None
) -> TeachingSessionDetailRead:
    engine = engine or load_engine(session)
    state = engine.classroom_state
    behavior_records = sorted(session.behavior_records, key=lambda item: item.id)
    counts = {
        "explanation_count": 0,
        "question_count": 0,
        "guided_question_count": 0,
        "example_count": 0,
        "feedback_count": 0,
        "correction_count": 0,
        "understanding_check_count": 0,
        "direct_answer_count": 0,
    }
    for record in behavior_records:
        key = f"{record.action_type}_count"
        if key in counts:
            counts[key] += 1

    evaluation = None
    if session.evaluation is not None and session.evaluation.narrative is not None:
        evaluation = EvaluationEngine.to_read(
            session.evaluation, session.evaluation.narrative
        )

    return TeachingSessionDetailRead(
        id=session.id,
        scenario_id=session.scenario_id,
        virtual_student_id=session.virtual_student_id,
        started_at=session.started_at,
        ended_at=session.ended_at,
        status=session.status,
        scenario=session.scenario,
        virtual_student=session.virtual_student,
        dialogue_records=sorted(session.dialogue_records, key=lambda item: item.sequence),
        behavior_records=behavior_records,
        behavior_summary=TeachingBehaviorSummaryRead(**counts),
        evaluation=evaluation,
        state=SessionStateRead(
            understanding=state.understanding,
            confusion=state.confusion,
            engagement=state.engagement,
            confidence=state.confidence,
        ),
    )


def create_or_reuse_session(
    db: Session, scenario_id: int, virtual_student_id: int
) -> TeachingSession:
    scenario = db.get(TrainingScenario, scenario_id)
    if scenario is None:
        raise LookupError("教学实训场景不存在")
    student = db.get(VirtualStudent, virtual_student_id)
    if student is None:
        raise LookupError("虚拟学生不存在")

    active_statement = select(TeachingSession).where(
        TeachingSession.scenario_id == scenario_id,
        TeachingSession.virtual_student_id == virtual_student_id,
        TeachingSession.status == "active",
    )
    existing = db.scalar(active_statement.order_by(TeachingSession.id.desc()))
    if existing is not None:
        return load_session(db, existing.id) or existing

    session = TeachingSession(
        scenario_id=scenario_id,
        virtual_student_id=virtual_student_id,
        started_at=datetime.now(UTC).replace(tzinfo=None),
        status="active",
    )
    db.add(session)
    db.commit()
    return load_session(db, session.id) or session


def list_session_history(db: Session) -> list[SessionHistoryItemRead]:
    statement = (
        select(TeachingSession)
        .where(TeachingSession.status == "completed")
        .options(
            selectinload(TeachingSession.scenario),
            selectinload(TeachingSession.virtual_student),
            selectinload(TeachingSession.evaluation),
        )
        .order_by(TeachingSession.started_at.asc(), TeachingSession.id.asc())
    )
    sessions = db.scalars(statement).all()
    return [
        SessionHistoryItemRead(
            id=item.id,
            started_at=item.started_at,
            ended_at=item.ended_at,
            status=item.status,
            scenario_id=item.scenario_id,
            topic=item.scenario.topic,
            virtual_student_name=item.virtual_student.name,
            overall_score=item.evaluation.overall_score if item.evaluation else None,
        )
        for item in sessions
    ]


def send_teacher_message(
    db: Session,
    session: TeachingSession,
    teacher_text: str,
    client: LLMClient,
) -> TeachingSessionDetailRead:
    if session.status != "active":
        raise RuntimeError("实训已结束，不能继续发送消息")

    engine = load_engine(session)
    next_sequence = max((record.sequence for record in session.dialogue_records), default=-1) + 1
    teacher_record = DialogueRecord(
        session_id=session.id,
        speaker="teacher",
        content=teacher_text.strip(),
        sequence=next_sequence,
        timestamp=datetime.now(UTC).replace(tzinfo=None),
    )
    db.add(teacher_record)
    db.flush()

    context = LLMContext(
        student_name=session.virtual_student.name,
        student_grade=session.virtual_student.grade,
        topic=session.scenario.topic,
    )
    behavior_analysis = TeachingBehaviorAnalyzer().analyze(
        teacher_text,
        llm_client=client,
        context=context,
    )
    engine.update_from_teacher_text(teacher_text)
    prompt = engine.build_prompt(teacher_text)
    student_text = client.respond(
        teacher_text,
        LLMContext(
            student_name=session.virtual_student.name,
            student_grade=session.virtual_student.grade,
            topic=session.scenario.topic,
            system_prompt=prompt,
        ),
    )
    if not student_text.strip():
        db.rollback()
        raise RuntimeError("学生回答为空，请重试")

    db.add(
        TeachingBehaviorRecord(
            session_id=session.id,
            dialogue_record_id=teacher_record.id,
            action_type=behavior_analysis.action_type.value,
            concept=behavior_analysis.concept,
            knowledge_accuracy=behavior_analysis.knowledge_accuracy,
            clarity=behavior_analysis.clarity,
            checked_understanding=behavior_analysis.checked_understanding,
            gave_answer_directly=behavior_analysis.gave_answer_directly,
            analysis_source=behavior_analysis.analysis_source,
            analysis_error=behavior_analysis.analysis_error,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    db.add(
        DialogueRecord(
            session_id=session.id,
            speaker="student",
            content=student_text.strip(),
            sequence=next_sequence + 1,
            timestamp=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    db.commit()
    refreshed = load_session(db, session.id)
    if refreshed is None:
        raise RuntimeError("实训会话保存失败")
    return build_session_detail(refreshed, engine)


def end_session(
    db: Session,
    session: TeachingSession,
    client: LLMClient | None = None,
) -> TeachingSessionDetailRead:
    if session.status == "active":
        session.status = "completed"
        session.ended_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
    if client is not None and (session.evaluation is None or session.evaluation.narrative is None):
        EvaluationEngine().evaluate_and_save(db, session, client)
    refreshed = load_session(db, session.id)
    if refreshed is None:
        raise RuntimeError("实训会话不存在")
    return build_session_detail(refreshed)
