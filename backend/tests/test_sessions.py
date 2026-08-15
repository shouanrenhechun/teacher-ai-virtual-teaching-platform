from fastapi.testclient import TestClient

from app.main import app


def get_seed_ids(client: TestClient) -> tuple[int, list[int]]:
    scenario = client.get("/api/scenarios").json()[0]
    students = client.get("/api/virtual-students").json()
    return scenario["id"], [student["id"] for student in students]


def test_create_session_reuses_existing_active_session(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    with TestClient(app) as client:
        scenario_id, student_ids = get_seed_ids(client)
        first = client.post(
            "/api/sessions",
            json={"scenario_id": scenario_id, "virtual_student_id": student_ids[1]},
        )
        second = client.post(
            "/api/sessions",
            json={"scenario_id": scenario_id, "virtual_student_id": student_ids[1]},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["status"] == "active"


def test_full_mock_session_lifecycle_and_refresh(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    with TestClient(app) as client:
        scenario_id, student_ids = get_seed_ids(client)
        created = client.post(
            "/api/sessions",
            json={"scenario_id": scenario_id, "virtual_student_id": student_ids[2]},
        )
        assert created.status_code == 200

        # Make the test repeatable if a previous interrupted run left an active session.
        if created.json()["dialogue_records"]:
            client.post(f"/api/sessions/{created.json()['id']}/end")
            created = client.post(
                "/api/sessions",
                json={"scenario_id": scenario_id, "virtual_student_id": student_ids[2]},
            )

        session_id = created.json()["id"]
        message = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "请比较 k 和 b 分别会改变什么？"},
        )
        refreshed = client.get(f"/api/sessions/{session_id}")
        ended = client.post(f"/api/sessions/{session_id}/end")
        after_end = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "再说一遍。"},
        )

    assert message.status_code == 200
    message_data = message.json()
    assert [item["speaker"] for item in message_data["dialogue_records"]] == [
        "teacher",
        "student",
    ]
    assert message_data["dialogue_records"][0]["content"].startswith("请比较")
    assert message_data["dialogue_records"][1]["content"]
    assert message_data["state"]["engagement"] >= 0

    assert refreshed.status_code == 200
    assert len(refreshed.json()["dialogue_records"]) == 2
    assert ended.status_code == 200
    assert ended.json()["status"] == "completed"
    assert ended.json()["ended_at"] is not None
    assert after_end.status_code == 409


def test_session_stores_behavior_analysis_and_summary(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    with TestClient(app) as client:
        scenario_id, student_ids = get_seed_ids(client)
        created = client.post(
            "/api/sessions",
            json={"scenario_id": scenario_id, "virtual_student_id": student_ids[0]},
        )
        if created.json()["dialogue_records"]:
            client.post(f"/api/sessions/{created.json()['id']}/end")
            created = client.post(
                "/api/sessions",
                json={"scenario_id": scenario_id, "virtual_student_id": student_ids[0]},
            )

        session_id = created.json()["id"]
        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "如果固定 k，只改变 b，图像会怎样？"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["behavior_summary"]["guided_question_count"] == 1
    assert data["behavior_summary"]["question_count"] == 0
    assert len(data["behavior_records"]) == 1
    assert data["behavior_records"][0]["action_type"] == "guided_question"
    assert data["behavior_records"][0]["knowledge_accuracy"] >= 0
