from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.llm.base import LLMContext
from app.services.llm.mock import MockLLMClient
from app.services.virtual_student import (
    ClassroomAct,
    TeachingBehavior,
    VirtualStudentEngine,
    analyze_classroom_dialogue,
    detect_teacher_behavior,
)
from validation.case_loader import load_student_profile


CORRECT_EVIDENCE = {
    "states_correct_conclusion": True,
    "explains_reason_correctly": True,
    "shows_residual_misconception": False,
    "conceptual_uncertainty": False,
    "evidence_insufficient": False,
}


def _context(
    status: str,
    evidence: dict[str, object],
    *,
    stable_count: int = 0,
    transfer_evidence: int = 0,
    history: tuple[tuple[str, str], ...] = (),
    profile_id: str = "student_a",
    confidence: float = 0.55,
    confidence_style: str = "自然表达，不刻意改变知识判断。",
    response_style: str = "回答自然、简短，符合课堂中的学生表达。",
    confirmation_seeking: str = "必要时根据教师提示确认自己的理解。",
    correction_style: str = "接受证据后逐步修正。",
) -> LLMContext:
    return LLMContext(
        student_profile_id=profile_id,
        misconception_status=status,
        previous_student_evidence=evidence,
        misconception_stable_correct_evidence_count=stable_count,
        misconception_transfer_evidence=transfer_evidence,
        conversation_history=history,
        student_confidence=confidence,
        confidence_style=confidence_style,
        response_style=response_style,
        confirmation_seeking=confirmation_seeking,
        correction_style=correction_style,
    )


def test_corrected_praise_is_short_acceptance_without_false_self_check() -> None:
    response = MockLLMClient().respond(
        "回答得很好。",
        _context("corrected", CORRECT_EVIDENCE, stable_count=2, transfer_evidence=1),
    )

    assert response == "谢谢老师。"
    assert "检查" not in response
    assert "验证" not in response


def test_provisional_praise_expresses_progress_without_claiming_mastery() -> None:
    response = MockLLMClient().respond(
        "你说得没错。",
        _context("provisional", CORRECT_EVIDENCE, stable_count=1),
    )

    assert "思路清楚一些" in response
    assert "完全" not in response


def test_uncertain_praise_may_use_metacognitive_self_check() -> None:
    uncertain_evidence = {
        **CORRECT_EVIDENCE,
        "explains_reason_correctly": False,
        "conceptual_uncertainty": True,
        "evidence_insufficient": True,
    }

    response = MockLLMClient().respond(
        "很好。",
        _context("weakening", uncertain_evidence),
    )

    assert "检查一下自己的理由" in response


def test_actual_insufficient_evidence_overrides_an_old_corrected_status() -> None:
    response = MockLLMClient().respond(
        "很好。",
        _context("corrected", {"evidence_insufficient": True}),
    )

    assert "检查一下自己的理由" in response


def test_consecutive_praise_replies_are_deterministically_deduplicated() -> None:
    client = MockLLMClient()
    first = client.respond("回答得很好。", _context("corrected", CORRECT_EVIDENCE))
    history = (("teacher", "回答得很好。"), ("student", first))
    second_context = _context("corrected", CORRECT_EVIDENCE, history=history)

    second = client.respond("你回答得没错。", second_context)
    repeated_second = client.respond("你回答得没错。", second_context)

    assert first != second
    assert second == repeated_second


def test_session_praise_uses_latest_substantive_answer_and_skips_social_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    with TestClient(app) as client:
        scenario = client.get("/api/scenarios").json()[0]
        student = client.get("/api/virtual-students").json()[0]
        created = client.post(
            "/api/sessions",
            json={"scenario_id": scenario["id"], "virtual_student_id": student["id"]},
        )
        if created.json()["dialogue_records"]:
            client.post(f"/api/sessions/{created.json()['id']}/end")
            created = client.post(
                "/api/sessions",
                json={"scenario_id": scenario["id"], "virtual_student_id": student["id"]},
            )

        session_id = created.json()["id"]
        content_turn = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "比较 y=2x+3 和 y=2x-5，判断它们是否一样陡。"},
        ).json()
        first_praise = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "你回答得很好。"},
        ).json()
        second_praise = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "你回答得没错。"},
        ).json()
        client.post(f"/api/sessions/{session_id}/end")

    first_response = first_praise["dialogue_records"][-1]["content"]
    second_response = second_praise["dialogue_records"][-1]["content"]
    misconception_after_content = content_turn["cognitive_trace"]["current_misconception"]

    assert "检查一下自己的理由" not in first_response
    assert first_response != second_response
    assert first_praise["cognitive_trace"]["current_misconception"] == misconception_after_content
    assert second_praise["cognitive_trace"]["current_misconception"] == misconception_after_content


def test_praise_plus_explanation_request_executes_explanation_task() -> None:
    teacher_text = "你的解答说得很清楚，请进一步说明依据。"
    intent = analyze_classroom_dialogue(teacher_text)
    response = MockLLMClient().respond(
        teacher_text,
        _context("corrected", CORRECT_EVIDENCE),
    )

    assert intent.has(ClassroomAct.FEEDBACK)
    assert intent.has(ClassroomAct.ELABORATION_REQUEST)
    assert intent.primary_act is ClassroomAct.ELABORATION_REQUEST
    assert "因为" in response
    assert response not in {"谢谢老师。", "好的。", "嗯，谢谢老师。"}


def test_praise_plus_judgment_request_executes_explicit_math_task() -> None:
    teacher_text = "很好，你再判断一下 y=3x+1 和 y=3x-4。"
    intent = analyze_classroom_dialogue(teacher_text)
    response = MockLLMClient().respond(
        teacher_text,
        _context("corrected", CORRECT_EVIDENCE),
    )

    assert intent.has(ClassroomAct.FEEDBACK)
    assert intent.has(ClassroomAct.QUESTION)
    assert intent.primary_act is ClassroomAct.QUESTION
    assert "斜率都是 3" in response
    assert "一样陡" in response


def test_contextual_praise_plus_judgment_reuses_previous_problem() -> None:
    history = (
        ("teacher", "比较 y=2x+1 和 y=2x+3，判断它们是否一样陡。"),
        ("student", "它们一样陡，因为斜率都是 2。"),
    )
    teacher_text = "很好，你自己再判断一次。"
    response = MockLLMClient().respond(
        teacher_text,
        _context("corrected", CORRECT_EVIDENCE, history=history),
    )

    assert analyze_classroom_dialogue(teacher_text).has(ClassroomAct.QUESTION)
    assert "斜率都是 2" in response
    assert "一样陡" in response


def test_generic_calculation_request_never_degrades_to_acknowledgement() -> None:
    teacher_text = "不错，再算一下这个。"
    intent = analyze_classroom_dialogue(teacher_text)
    response = MockLLMClient().respond(
        teacher_text,
        _context("provisional", CORRECT_EVIDENCE),
    )

    assert intent.has(ClassroomAct.FEEDBACK)
    assert intent.has(ClassroomAct.QUESTION)
    assert response not in {"谢谢老师。", "好的。", "好。", "嗯，谢谢老师。"}
    assert "题目" in response or "条件" in response


def test_confirmation_seeking_profile_changes_provisional_style_without_id_rule() -> None:
    profile = load_student_profile("student_b")
    response = MockLLMClient().respond(
        "回答得很好。",
        _context(
            "provisional",
            CORRECT_EVIDENCE,
            profile_id="renamed_profile",
            confidence=profile.confidence,
            confidence_style=profile.confidence_style,
            response_style=profile.response_style,
            confirmation_seeking=profile.confirmation_seeking,
            correction_style=profile.correction_style,
        ),
    )

    assert response == "谢谢老师，我想再做一道题确认一下。"


@pytest.mark.parametrize("profile_id", ("student_a", "student_b"))
def test_pure_praise_only_changes_small_social_state(profile_id: str) -> None:
    engine = VirtualStudentEngine(load_student_profile(profile_id))
    before = engine.export_state()

    engine.update_from_teacher_text("回答得很好。")
    response = MockLLMClient().respond(
        "回答得很好。",
        _context("active", {"evidence_insufficient": True}),
    )
    evidence = engine.apply_student_response_evidence(response, "回答得很好。")
    after = engine.export_state()

    assert detect_teacher_behavior("回答得很好。") is TeachingBehavior.PRAISE
    assert after["knowledge_states"] == before["knowledge_states"]
    assert after["misconceptions"] == before["misconceptions"]
    assert after["classroom_state"]["understanding"] == before["classroom_state"]["understanding"]
    assert after["classroom_state"]["confusion"] == before["classroom_state"]["confusion"]
    assert after["classroom_state"]["surface_recall"] == before["classroom_state"]["surface_recall"]
    assert after["classroom_state"]["engagement"] == pytest.approx(
        before["classroom_state"]["engagement"] + 0.02
    )
    assert after["classroom_state"]["confidence"] == pytest.approx(
        before["classroom_state"]["confidence"] + 0.02
    )
    assert evidence.evidence_insufficient is True


@pytest.mark.parametrize(
    "teacher_text, expected_act",
    (
        ("我们继续。", ClassroomAct.TRANSITION),
        ("好，下一个。", ClassroomAct.TRANSITION),
        ("先看这里。", ClassroomAct.ORGANIZATION),
        ("大家注意一下。", ClassroomAct.ORGANIZATION),
    ),
)
def test_classroom_management_phrases_are_not_promoted_to_tasks(
    teacher_text: str,
    expected_act: ClassroomAct,
) -> None:
    intent = analyze_classroom_dialogue(teacher_text)

    assert intent.primary_act is expected_act
    assert not intent.has(ClassroomAct.QUESTION)
    assert not intent.has(ClassroomAct.GUIDED_QUESTION)
