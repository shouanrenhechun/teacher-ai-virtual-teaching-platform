from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.teaching_behavior import TeachingActionType
from app.services.llm.base import LLMContext
from app.services.llm.mock import MockLLMClient
from app.services.teaching_behavior import TeachingBehaviorAnalyzer
from app.services.virtual_student import (
    ClassroomAct,
    TeachingBehavior,
    VirtualStudentEngine,
    analyze_classroom_dialogue,
    detect_teacher_behavior,
)
from validation.case_loader import load_student_profile


CLASSROOM_CASES = (
    ("同学你好。", ClassroomAct.GREETING, TeachingActionType.CLASSROOM_INTERACTION),
    ("我们开始上课。", ClassroomAct.GREETING, TeachingActionType.CLASSROOM_INTERACTION),
    ("准备好了吗？", ClassroomAct.GREETING, TeachingActionType.CLASSROOM_INTERACTION),
    ("今天继续学习。", ClassroomAct.TRANSITION, TeachingActionType.CLASSROOM_INTERACTION),
    ("先回顾一下昨天的内容。", ClassroomAct.TRANSITION, TeachingActionType.CLASSROOM_INTERACTION),
    ("请看黑板。", ClassroomAct.ORGANIZATION, TeachingActionType.CLASSROOM_INTERACTION),
    ("先写在草稿纸上。", ClassroomAct.ORGANIZATION, TeachingActionType.CLASSROOM_INTERACTION),
    ("给你一分钟想一想。", ClassroomAct.ORGANIZATION, TeachingActionType.CLASSROOM_INTERACTION),
    ("先别急着回答。", ClassroomAct.ORGANIZATION, TeachingActionType.CLASSROOM_INTERACTION),
    ("请坐。", ClassroomAct.ORGANIZATION, TeachingActionType.CLASSROOM_INTERACTION),
    ("注意听。", ClassroomAct.ORGANIZATION, TeachingActionType.CLASSROOM_INTERACTION),
    ("别紧张，大胆说。", ClassroomAct.ENCOURAGEMENT, TeachingActionType.FEEDBACK),
    ("没关系，慢慢想。", ClassroomAct.ENCOURAGEMENT, TeachingActionType.FEEDBACK),
    ("再试一次。", ClassroomAct.ENCOURAGEMENT, TeachingActionType.FEEDBACK),
    ("已经很接近答案了。", ClassroomAct.ENCOURAGEMENT, TeachingActionType.FEEDBACK),
    ("差一点，再想想。", ClassroomAct.CORRECTIVE_FEEDBACK, TeachingActionType.FEEDBACK),
    ("你回答得很好。", ClassroomAct.FEEDBACK, TeachingActionType.FEEDBACK),
    ("你回答的很好。", ClassroomAct.FEEDBACK, TeachingActionType.FEEDBACK),
    ("回答正确。", ClassroomAct.FEEDBACK, TeachingActionType.FEEDBACK),
    ("你的第一步是对的。", ClassroomAct.FEEDBACK, TeachingActionType.FEEDBACK),
    ("对，就是这个意思。", ClassroomAct.FEEDBACK, TeachingActionType.FEEDBACK),
    ("这里不太对。", ClassroomAct.CORRECTIVE_FEEDBACK, TeachingActionType.FEEDBACK),
    ("前面正确，后面再检查一下。", ClassroomAct.FEEDBACK, TeachingActionType.FEEDBACK),
    ("再说一遍。", ClassroomAct.ELABORATION_REQUEST, TeachingActionType.QUESTION),
    ("说完整一点。", ClassroomAct.ELABORATION_REQUEST, TeachingActionType.QUESTION),
    ("能说清楚一点吗？", ClassroomAct.ELABORATION_REQUEST, TeachingActionType.QUESTION),
    ("请把理由补充完整。", ClassroomAct.ELABORATION_REQUEST, TeachingActionType.QUESTION),
    ("结合图像再说说。", ClassroomAct.ELABORATION_REQUEST, TeachingActionType.QUESTION),
    ("用自己的话讲一遍。", ClassroomAct.ELABORATION_REQUEST, TeachingActionType.QUESTION),
    ("我们继续。", ClassroomAct.TRANSITION, TeachingActionType.CLASSROOM_INTERACTION),
    ("接着看下一题。", ClassroomAct.TRANSITION, TeachingActionType.CLASSROOM_INTERACTION),
    ("回到刚才的问题。", ClassroomAct.TRANSITION, TeachingActionType.CLASSROOM_INTERACTION),
    ("现在换一道题。", ClassroomAct.TRANSITION, TeachingActionType.CLASSROOM_INTERACTION),
    ("今天先到这里。", ClassroomAct.CLOSURE, TeachingActionType.CLASSROOM_INTERACTION),
    ("下课。", ClassroomAct.CLOSURE, TeachingActionType.CLASSROOM_INTERACTION),
    ("课后再练习。", ClassroomAct.CLOSURE, TeachingActionType.CLASSROOM_INTERACTION),
    ("嗯。", ClassroomAct.ACKNOWLEDGEMENT, TeachingActionType.CLASSROOM_INTERACTION),
    ("好的。", ClassroomAct.ACKNOWLEDGEMENT, TeachingActionType.CLASSROOM_INTERACTION),
    ("可以。", ClassroomAct.ACKNOWLEDGEMENT, TeachingActionType.CLASSROOM_INTERACTION),
    ("继续。", ClassroomAct.TRANSITION, TeachingActionType.CLASSROOM_INTERACTION),
    ("然后呢？", ClassroomAct.CONTINUATION, TeachingActionType.CLASSROOM_INTERACTION),
)


@pytest.mark.parametrize(("teacher_text", "expected_act", "expected_action"), CLASSROOM_CASES)
def test_classroom_short_dialogue_is_not_off_topic_and_has_consistent_behavior(
    teacher_text: str,
    expected_act: ClassroomAct,
    expected_action: TeachingActionType,
) -> None:
    classroom = analyze_classroom_dialogue(teacher_text)
    report_behavior = TeachingBehaviorAnalyzer().analyze(teacher_text)
    state_behavior = detect_teacher_behavior(teacher_text)

    assert classroom.act is expected_act
    assert classroom.off_topic is False
    assert report_behavior.action_type is expected_action
    if expected_act is ClassroomAct.ELABORATION_REQUEST:
        assert state_behavior is TeachingBehavior.EFFECTIVE_QUESTION
    else:
        assert state_behavior is TeachingBehavior.NEUTRAL

    response = MockLLMClient().respond(
        teacher_text,
        LLMContext(
            student_profile_id="student_a",
            misconception_status="active",
            conversation_history=(
                ("teacher", "比较两条直线后，你发现什么？"),
                ("student", "我觉得 b 越大直线越陡。"),
            ),
        ),
    )
    assert response.strip()
    assert "无关" not in response
    assert "不是这节课" not in response


@pytest.mark.parametrize("teacher_text", ("今天天气怎么样？", "你喜欢篮球吗？", "给我讲个笑话。"))
def test_genuine_off_topic_dialogue_is_still_redirected(teacher_text: str) -> None:
    classroom = analyze_classroom_dialogue(teacher_text)
    response = MockLLMClient().respond(teacher_text, LLMContext())

    assert classroom.off_topic is True
    assert "无关" in response or "不是这节课" in response
    assert detect_teacher_behavior(teacher_text) is TeachingBehavior.NEUTRAL


@pytest.mark.parametrize(
    "teacher_text",
    (
        "你回答得很好。",
        "没关系，慢慢想。",
        "请看黑板。",
        "我们继续。",
        "今天先到这里。",
    ),
)
def test_non_content_classroom_interaction_does_not_change_cognitive_state(
    teacher_text: str,
) -> None:
    engine = VirtualStudentEngine(load_student_profile("student_a"))
    before = engine.snapshot()
    opportunity = engine.get_correction_opportunity(teacher_text)

    engine.update_from_teacher_text(teacher_text)
    response = MockLLMClient().respond(
        teacher_text,
        LLMContext(student_profile_id="student_a", misconception_status="active"),
    )
    evidence = engine.apply_student_response_evidence(response, teacher_text, opportunity)

    assert engine.snapshot() == before
    assert evidence.evidence_insufficient is True


def test_affirmation_is_feedback_but_explicit_answer_is_direct_answer() -> None:
    analyzer = TeachingBehaviorAnalyzer()

    affirmation = analyzer.analyze("对，就是这样。")
    answer = analyzer.analyze("答案是：b 只影响截距，记住。")

    assert affirmation.action_type is TeachingActionType.FEEDBACK
    assert affirmation.gave_answer_directly is False
    assert detect_teacher_behavior("对，就是这样。") is TeachingBehavior.NEUTRAL
    assert answer.action_type is TeachingActionType.DIRECT_ANSWER
    assert answer.gave_answer_directly is True


def test_session_records_classroom_interactions_without_changing_cognition(monkeypatch) -> None:
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
        initial_trace = created.json()["cognitive_trace"]
        praised = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "你回答得很好。"},
        )
        organized = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "请看黑板。"},
        )
        client.post(f"/api/sessions/{session_id}/end")

    assert praised.status_code == 200
    assert praised.json()["behavior_records"][-1]["action_type"] == "feedback"
    assert praised.json()["behavior_summary"]["feedback_count"] == 1
    assert "无关" not in praised.json()["dialogue_records"][-1]["content"]

    data = organized.json()
    assert data["behavior_records"][-1]["action_type"] == "classroom_interaction"
    assert data["behavior_summary"]["classroom_interaction_count"] == 1
    assert data["cognitive_trace"]["current_state"] == initial_trace["current_state"]
    assert data["cognitive_trace"]["current_misconception"] == initial_trace["current_misconception"]
