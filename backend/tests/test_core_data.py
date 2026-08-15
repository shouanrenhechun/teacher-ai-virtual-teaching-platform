from fastapi.testclient import TestClient

from app.database.session import Base
from app.main import app


def test_core_tables_are_registered() -> None:
    expected_tables = {
        "training_scenarios",
        "virtual_students",
        "knowledge_states",
        "misconceptions",
        "teaching_sessions",
        "dialogue_records",
        "evaluations",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())


def test_list_scenarios_returns_seed_data() -> None:
    with TestClient(app) as client:
        response = client.get("/api/scenarios")

    assert response.status_code == 200
    data = response.json()
    target = next(item for item in data if item["title"] == "一次函数：k 与 b 的意义")
    assert target["subject"] == "初中数学"
    assert target["grade"] == "初二"
    assert target["topic"] == "一次函数"


def test_list_virtual_students_returns_related_data() -> None:
    with TestClient(app) as client:
        response = client.get("/api/virtual-students")

    assert response.status_code == 200
    data = response.json()
    assert {item["name"] for item in data} >= {"学生 A", "学生 B", "学生 C"}
    student_a = next(item for item in data if item["name"] == "学生 A")
    assert 0 <= student_a["base_level"] <= 1
    assert len(student_a["knowledge_states"]) >= 1
    assert all(0 <= item["mastery"] <= 1 for item in student_a["knowledge_states"])
    # Detailed misconception rules stay out of the public profile response.
    assert "misconceptions" not in student_a


def test_missing_core_data_returns_404() -> None:
    with TestClient(app) as client:
        scenario_response = client.get("/api/scenarios/999999")
        student_response = client.get("/api/virtual-students/999999")

    assert scenario_response.status_code == 404
    assert student_response.status_code == 404
