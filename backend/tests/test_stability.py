import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import db_session
from app.core.config import Settings
from app.main import app
from app.services.llm.base import LLMContext, LLMServiceError
from app.services.llm.real import RealLLMClient


def seed_ids(client: TestClient) -> tuple[int, int]:
    scenario = client.get("/api/scenarios").json()[0]
    student = next(item for item in client.get("/api/virtual-students").json() if item["name"] == "学生 A")
    return scenario["id"], student["id"]


def fresh_session(client: TestClient) -> int:
    scenario_id, student_id = seed_ids(client)
    created = client.post(
        "/api/sessions",
        json={"scenario_id": scenario_id, "virtual_student_id": student_id},
    )
    assert created.status_code == 200
    if created.json()["dialogue_records"]:
        ended = client.post(f"/api/sessions/{created.json()['id']}/end")
        assert ended.status_code == 200
        created = client.post(
            "/api/sessions",
            json={"scenario_id": scenario_id, "virtual_student_id": student_id},
        )
    return created.json()["id"]


def test_invalid_session_inputs_and_missing_session_are_safe(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    with TestClient(app) as client:
        invalid_scenario = client.post(
            "/api/sessions",
            json={"scenario_id": 999999, "virtual_student_id": 1},
        )
        invalid_student = client.post(
            "/api/sessions",
            json={"scenario_id": 1, "virtual_student_id": 999999},
        )
        invalid_payload = client.post(
            "/api/sessions",
            json={"scenario_id": 0, "virtual_student_id": 0},
        )
        missing_session = client.get("/api/sessions/999999/evaluation")

    assert invalid_scenario.status_code == 404
    assert invalid_student.status_code == 404
    assert invalid_payload.status_code == 422
    assert missing_session.status_code == 404


def test_duplicate_end_is_idempotent_and_report_remains_available(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    with TestClient(app) as client:
        session_id = fresh_session(client)
        message = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "请比较 k 和 b 的作用。"},
        )
        first_end = client.post(f"/api/sessions/{session_id}/end")
        second_end = client.post(f"/api/sessions/{session_id}/end")

    assert message.status_code == 200
    assert first_end.status_code == 200
    assert second_end.status_code == 200
    assert first_end.json()["status"] == second_end.json()["status"] == "completed"
    assert first_end.json()["ended_at"] == second_end.json()["ended_at"]
    assert second_end.json()["evaluation"]["overall_score"] >= 0


def test_mock_demo_flow_exposes_misconception_then_correction_and_report(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    with TestClient(app) as client:
        session_id = fresh_session(client)
        exposed = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "老师，b 越大时直线会怎样？"},
        )
        corrected = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "不对，b 不影响斜率，只改变截距位置。"},
        )
        guided = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "如果固定 k，只改变 b，图像会怎样？"},
        )
        checked = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "你能复述一下 b 的作用吗？"},
        )
        ended = client.post(f"/api/sessions/{session_id}/end")

    assert exposed.status_code == 200
    assert "b" in exposed.json()["dialogue_records"][1]["content"].lower()
    assert corrected.status_code == 200
    assert guided.status_code == 200
    assert checked.status_code == 200
    assert guided.json()["behavior_summary"]["correction_count"] == 1
    report = ended.json()["evaluation"]
    assert ended.status_code == 200
    assert report["overall_score"] >= 0
    assert report["key_teaching_snippets"]
    assert "不替代专业教师" in report["disclaimer"]


def test_database_failure_returns_safe_503(monkeypatch) -> None:
    def failing_db():
        raise SQLAlchemyError("simulated database failure")

    app.dependency_overrides[db_session] = failing_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/scenarios")
    finally:
        app.dependency_overrides.pop(db_session, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "数据库暂时不可用，请稍后重试"


class TimeoutHttpClient:
    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, *_args, **_kwargs):
        raise httpx.TimeoutException("simulated timeout")


class MalformedJsonHttpClient:
    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, *_args, **_kwargs):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not-json"}}]},
        )


def real_client() -> RealLLMClient:
    return RealLLMClient(
        Settings(
            llm_provider="real",
            llm_api_key="test-key",
            llm_api_url="https://example.invalid/chat",
            llm_model="test-model",
            llm_timeout_seconds=1,
        )
    )


def test_real_llm_timeout_is_converted_to_friendly_error(monkeypatch) -> None:
    monkeypatch.setattr("app.services.llm.real.httpx.Client", TimeoutHttpClient)

    with pytest.raises(LLMServiceError, match="超时"):
        real_client().respond("请解释 b 的意义。", LLMContext())


def test_real_llm_malformed_json_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr("app.services.llm.real.httpx.Client", MalformedJsonHttpClient)

    with pytest.raises(LLMServiceError, match="JSON"):
        real_client().analyze_behavior("请分析这句教学话语。", LLMContext())
