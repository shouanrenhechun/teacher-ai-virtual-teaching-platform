from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.session import SessionLocal
from app.main import app
from app.models import TeachingSessionSnapshot, VirtualStudent
from app.services.session_service import backfill_session_snapshots


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


def test_session_trace_is_frozen_when_global_student_profile_changes(monkeypatch) -> None:
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
        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "请比较固定 k、改变 b 后图像会怎样？"},
        )
        assert response.status_code == 200
        frozen_trace = response.json()["cognitive_trace"]

        with SessionLocal() as db:
            statement = (
                select(VirtualStudent)
                .where(VirtualStudent.id == student["id"])
                .options(selectinload(VirtualStudent.misconceptions))
            )
            record = db.scalar(statement)
            assert record is not None
            original_base_level = record.base_level
            original_strength = record.misconceptions[0].strength
            record.base_level = 0.01
            record.misconceptions[0].strength = 0.01
            db.commit()

        try:
            fetched = client.get(f"/api/sessions/{session_id}")
            assert fetched.status_code == 200
            assert fetched.json()["cognitive_trace"] == frozen_trace

            continued = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"teacher_text": "请再用自己的话解释 k 和 b 的作用。"},
            )
            assert continued.status_code == 200
            continued_trace = continued.json()["cognitive_trace"]
            assert continued_trace["initial_state"] == frozen_trace["initial_state"]
            assert continued_trace["initial_misconception"] == frozen_trace["initial_misconception"]
            assert continued_trace["rounds"][0] == frozen_trace["rounds"][0]
            assert len(continued_trace["rounds"]) == 2
            with SessionLocal() as db:
                snapshot = db.get(TeachingSessionSnapshot, session_id)
                assert snapshot is not None
                assert snapshot.profile_json
                assert snapshot.engine_state_json
                assert snapshot.cognitive_trace_json
        finally:
            with SessionLocal() as db:
                statement = (
                    select(VirtualStudent)
                    .where(VirtualStudent.id == student["id"])
                    .options(selectinload(VirtualStudent.misconceptions))
                )
                record = db.scalar(statement)
                assert record is not None
                record.base_level = original_base_level
                record.misconceptions[0].strength = original_strength
                db.commit()


def test_legacy_session_without_snapshot_is_backfilled(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    with TestClient(app) as client:
        scenario = client.get("/api/scenarios").json()[0]
        student = client.get("/api/virtual-students").json()[1]
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

        with SessionLocal() as db:
            snapshot = db.get(TeachingSessionSnapshot, session_id)
            assert snapshot is not None
            db.delete(snapshot)
            db.commit()
            assert backfill_session_snapshots(db) == 1
            restored = db.get(TeachingSessionSnapshot, session_id)
            assert restored is not None

        fetched = client.get(f"/api/sessions/{session_id}")
        assert fetched.status_code == 200
        assert fetched.json()["cognitive_trace"]["rounds"] == []
