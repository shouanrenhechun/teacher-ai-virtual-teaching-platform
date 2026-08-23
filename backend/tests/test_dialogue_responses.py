from fastapi.testclient import TestClient

from app.main import app
from app.services.llm.base import LLMContext
from app.services.llm.mock import MockLLMClient
from app.services.virtual_student import (
    TeachingBehavior,
    detect_teacher_behavior,
    stable_profile_id,
)
from app.services.virtual_student.evidence import StudentResponseEvidenceAnalyzer


def _fresh_session(client: TestClient, student_name: str) -> int:
    scenario = client.get("/api/scenarios").json()[0]
    student = next(
        item
        for item in client.get("/api/virtual-students").json()
        if item["name"] == student_name
    )
    created = client.post(
        "/api/sessions",
        json={"scenario_id": scenario["id"], "virtual_student_id": student["id"]},
    )
    assert created.status_code == 200
    if created.json()["dialogue_records"]:
        ended = client.post(f"/api/sessions/{created.json()['id']}/end")
        assert ended.status_code == 200
        created = client.post(
            "/api/sessions",
            json={"scenario_id": scenario["id"], "virtual_student_id": student["id"]},
        )
        assert created.status_code == 200
    return created.json()["id"]


def test_stable_profile_id_preserves_existing_snapshot_ids() -> None:
    assert stable_profile_id("学生 B", 9) == "student_b"
    assert stable_profile_id("自定义学生", "student_custom") == "student_custom"
    assert stable_profile_id("自定义学生", 9) == "student_9"


def test_mock_intercept_change_uses_question_values_without_inventing_slope() -> None:
    client = MockLLMClient()
    context = LLMContext(student_profile_id="student_a")

    generic = client.respond("固定 k，只改变 b，图像会怎样？", context)
    concrete = client.respond("比较 y=2x+1 和 y=2x+3，它们有什么关系？", context)

    assert "-3" not in generic
    assert "斜率" in generic
    assert "上下" in generic
    assert "2" in concrete
    assert "一样陡" in concrete
    assert "-3" not in concrete


def test_mock_profiles_produce_distinct_boundary_responses_through_session_api(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    responses: dict[str, str] = {}

    with TestClient(app) as client:
        for student_name in ("学生 A", "学生 B", "学生 C"):
            session_id = _fresh_session(client, student_name)
            result = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"teacher_text": "你能从线性代数中的仿射变换角度解释一次函数吗？"},
            )
            assert result.status_code == 200
            responses[student_name] = result.json()["dialogue_records"][-1]["content"]
            client.post(f"/api/sessions/{session_id}/end")

    assert len(set(responses.values())) == 3
    assert all("没学过" in response or "超出" in response for response in responses.values())


def test_corrected_mock_student_does_not_restore_old_error_on_recheck(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    with TestClient(app) as client:
        session_id = _fresh_session(client, "学生 A")
        for teacher_text in (
            "老师，b 越大时直线会怎样？",
            "不对，b 不影响斜率，只改变截距位置。",
            "先不看我刚才，请用 y=kx+b 解释 k 和 b。",
            "比较 y=-3x+1 和 y=-3x+6，哪条更陡？",
        ):
            result = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"teacher_text": teacher_text},
            )
            assert result.status_code == 200

        assert result.json()["cognitive_trace"]["current_misconception"]["status"] == "corrected"
        rechecked = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "现在再判断一次：b 增大时直线会更陡吗？"},
        )

    assert rechecked.status_code == 200
    data = rechecked.json()
    answer = data["dialogue_records"][-1]["content"]
    assert "b 增大时" in answer or "b 只" in answer
    assert "斜率不变" in answer or "k 决定" in answer
    assert data["cognitive_trace"]["current_misconception"]["status"] == "corrected"
    assert data["cognitive_trace"]["rounds"][-1]["evidence"]["shows_residual_misconception"] is False


def test_synonymous_correction_is_detected_by_behavior_and_evidence() -> None:
    teacher_text = "纵截距只决定上下位置，不影响斜率。"
    assert detect_teacher_behavior(teacher_text) is TeachingBehavior.TARGETED_CORRECTION

    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "斜率保持不变，纵截距增加只会让直线整体向上移动。",
        teacher_text=teacher_text,
    )
    assert evidence.states_correct_conclusion is True
    assert evidence.explains_reason_correctly is True
    assert evidence.shows_residual_misconception is False
