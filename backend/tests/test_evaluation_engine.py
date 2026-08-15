from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.evaluation import EvaluationQualitativeAnalysis
from app.services.evaluation_engine import EVALUATION_WEIGHTS, EvaluationEngine
from app.services.llm.base import LLMClient, LLMContext


class InvalidEvaluationClient(LLMClient):
    provider = "invalid-evaluation-test"

    def respond(self, teacher_text: str, context: LLMContext | None = None) -> str:
        return "学生回答"

    def analyze_evaluation(
        self, evaluation_prompt: str, context: LLMContext | None = None
    ) -> dict[str, object]:
        return {"strengths": "这不是字符串数组"}


def behavior(action_type: str, accuracy: float = 0.9) -> SimpleNamespace:
    return SimpleNamespace(
        action_type=action_type,
        knowledge_accuracy=accuracy,
    )


def test_evaluation_scores_use_central_weights_and_observable_counts() -> None:
    assert round(sum(EVALUATION_WEIGHTS.values()), 5) == 1
    session = SimpleNamespace(
        behavior_records=[
            behavior("guided_question"),
            behavior("example"),
            behavior("understanding_check"),
            behavior("correction"),
            behavior("direct_answer", accuracy=0.8),
        ]
    )

    scores = EvaluationEngine().calculate_scores(session)

    assert scores["knowledge_accuracy"] == 88.0
    assert scores["questioning"] > 0
    assert scores["misconception_diagnosis"] > 0
    assert 0 <= scores["overall_score"] <= 100


def test_invalid_qualitative_llm_uses_rule_report() -> None:
    session = SimpleNamespace(
        virtual_student=SimpleNamespace(name="学生 A"),
        scenario=SimpleNamespace(topic="一次函数 k 与 b 的意义"),
        behavior_records=[],
        dialogue_records=[],
    )
    engine = EvaluationEngine()

    result, source, error = engine._qualitative_analysis(
        session,
        {
            "knowledge_accuracy": 0.0,
            "questioning": 0.0,
            "feedback": 0.0,
            "misconception_diagnosis": 0.0,
            "scaffolding": 0.0,
            "overall_score": 0.0,
        },
        {},
        InvalidEvaluationClient(),
    )

    assert isinstance(result, EvaluationQualitativeAnalysis)
    assert result.strengths
    assert result.problems
    assert source == "fallback"
    assert error


def get_seed_ids(client: TestClient) -> tuple[int, int]:
    scenario = client.get("/api/scenarios").json()[0]
    student = client.get("/api/virtual-students").json()[0]
    return scenario["id"], student["id"]


def test_completed_session_returns_evaluation_with_real_evidence(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    with TestClient(app) as client:
        scenario_id, student_id = get_seed_ids(client)
        created = client.post(
            "/api/sessions",
            json={"scenario_id": scenario_id, "virtual_student_id": student_id},
        )
        if created.json()["dialogue_records"]:
            client.post(f"/api/sessions/{created.json()['id']}/end")
            created = client.post(
                "/api/sessions",
                json={"scenario_id": scenario_id, "virtual_student_id": student_id},
            )

        session_id = created.json()["id"]
        for teacher_text in (
            "如果固定 k，只改变 b，图像会怎样？",
            "例如固定 k=2，比较 b=1 和 b=3。",
            "答案是 b 只影响截距，记住。",
        ):
            response = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"teacher_text": teacher_text},
            )
            assert response.status_code == 200

        ended = client.post(f"/api/sessions/{session_id}/end")
        fetched = client.get(f"/api/sessions/{session_id}/evaluation")
        history = client.get("/api/sessions/history")

    assert ended.status_code == 200
    report = ended.json()["evaluation"]
    assert report["overall_score"] == ended.json()["evaluation"]["overall_score"]
    for field in (
        "knowledge_accuracy",
        "questioning",
        "feedback",
        "misconception_diagnosis",
        "scaffolding",
    ):
        assert 0 <= report[field] <= 100
    assert report["strengths"]
    assert report["problems"]
    assert report["suggestions"]
    assert report["key_teaching_snippets"]
    assert any("如果固定 k" in item["teacher_text"] for item in report["key_teaching_snippets"])
    assert "不替代专业教师" in report["disclaimer"]
    assert fetched.status_code == 200
    assert fetched.json()["session_id"] == session_id
    assert history.status_code == 200
    history_item = next(item for item in history.json() if item["id"] == session_id)
    assert history_item["topic"]
    assert history_item["virtual_student_name"]
    assert history_item["overall_score"] == report["overall_score"]
