from fastapi.testclient import TestClient

from app.main import app
from app.services.llm.base import LLMContext
from app.services.llm.mock import MockLLMClient


def test_mock_client_returns_contextual_non_fixed_responses() -> None:
    client = MockLLMClient()
    first = client.respond(
        "老师，b 越大时直线会怎样？",
        LLMContext(student_name="学生 A"),
    )
    second = client.respond(
        "如果 k 变大，图像会更陡吗？",
        LLMContext(student_name="学生 A"),
    )

    assert first
    assert second
    assert first != second
    assert "b" in first.lower()
    assert "k" in second.lower()


def test_mock_llm_api_returns_student_text(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_API_KEY", "")

    with TestClient(app) as client:
        response = client.post(
            "/api/llm/respond",
            json={
                "teacher_text": "请比较 k 和 b 分别会改变什么。",
                "student_name": "学生 A",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "mock"
    assert data["student_text"]


def test_real_llm_without_api_key_returns_friendly_error(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_API_KEY", "")

    with TestClient(app) as client:
        response = client.post(
            "/api/llm/respond",
            json={"teacher_text": "请解释 b 的意义。"},
        )

    assert response.status_code == 503
    assert "LLM_API_KEY" in response.json()["detail"]
