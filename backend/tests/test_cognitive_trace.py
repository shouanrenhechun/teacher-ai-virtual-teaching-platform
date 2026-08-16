from fastapi.testclient import TestClient

from app.main import app


def test_session_exposes_read_only_cognitive_trace(monkeypatch) -> None:
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

        response = client.post(
            f"/api/sessions/{created.json()['id']}/messages",
            json={"teacher_text": "请比较固定 k、改变 b 后图像会怎样？"},
        )

    assert response.status_code == 200
    trace = response.json()["cognitive_trace"]
    assert trace["initial_misconception"]["status"] == "active"
    assert trace["current_misconception"]["strength"] >= 0
    assert len(trace["rounds"]) == 1
    assert trace["rounds"][0]["teacher_text"].startswith("请比较")
    assert trace["rounds"][0]["evidence"] is not None
    assert "linguistic_hedging" in trace["rounds"][0]["evidence"]
    assert "surface_recall" in trace["rounds"][0]["state_after"]
