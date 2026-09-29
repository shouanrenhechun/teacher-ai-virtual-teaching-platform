from __future__ import annotations

import json
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.api.llm_routes import llm_client_dependency  # noqa: E402
from app.database import session as database  # noqa: E402
from app.main import app  # noqa: E402
from app.services.llm.mock import MockLLMClient  # noqa: E402


OWNER_TOKEN = "a" * 64
TEACHER_TURNS = [
    "在 y=2x+3 中，2 和 3 分别有什么作用？你觉得哪个会影响直线的倾斜程度？",
    "我先告诉你：k 决定倾斜程度，b 只改变截距和上下位置。你能用自己的话说说为什么吗？",
]


def _json_metadata(value: str | dict | None) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"raw": parsed}
        except json.JSONDecodeError:
            return {"raw": value}
    return {}


def main() -> int:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = BACKEND_DIR / "audits" / f"mock_classroom_two_rounds_{timestamp}.json"
    mock_client = MockLLMClient()
    previous_engine = database.engine
    previous_bind = database.SessionLocal.kw.get("bind")
    previous_overrides = app.dependency_overrides.copy()
    report: dict = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": "mock",
        "model": None,
        "mode": "offline deterministic Mock; no remote API calls",
        "scenario_title": "一次函数：k 与 b 的意义",
        "rounds_per_student": 2,
        "teacher_turns": TEACHER_TURNS,
        "students": [],
    }

    try:
        with tempfile.TemporaryDirectory(prefix="mock-classroom-") as temp_dir:
            db_path = Path(temp_dir) / "isolated-test.db"
            isolated_engine = create_engine(
                f"sqlite:///{db_path.as_posix()}",
                connect_args={"check_same_thread": False},
            )
            database.engine = isolated_engine
            database.DATABASE_DIR = Path(temp_dir)
            database.DATABASE_PATH = db_path
            database.SessionLocal.configure(bind=isolated_engine)
            app.dependency_overrides[llm_client_dependency] = lambda: mock_client

            with TestClient(app, headers={"X-Practice-Token": OWNER_TOKEN}) as client:
                scenarios_response = client.get("/api/scenarios")
                students_response = client.get("/api/virtual-students")
                scenarios_response.raise_for_status()
                students_response.raise_for_status()
                scenario = next(
                    item for item in scenarios_response.json()
                    if item["title"] == "一次函数：k 与 b 的意义"
                )
                students_by_name = {
                    item["name"]: item for item in students_response.json()
                }

                for student_name in ("学生 A", "学生 B", "学生 C"):
                    student = students_by_name[student_name]
                    created = client.post(
                        "/api/sessions",
                        json={
                            "scenario_id": scenario["id"],
                            "virtual_student_id": student["id"],
                        },
                    )
                    created.raise_for_status()
                    current = created.json()
                    session_id = current["id"]
                    turns = []

                    for round_number, teacher_text in enumerate(TEACHER_TURNS, start=1):
                        response = client.post(
                            f"/api/sessions/{session_id}/messages",
                            json={
                                "teacher_text": teacher_text,
                                "request_id": str(uuid.uuid4()),
                                "expected_version": current["version"],
                            },
                        )
                        response.raise_for_status()
                        current = response.json()
                        student_record = next(
                            item for item in reversed(current["dialogue_records"])
                            if item["speaker"] == "student"
                        )
                        trace_round = current["cognitive_trace"]["rounds"][-1]
                        behavior = current["behavior_records"][-1]
                        turns.append(
                            {
                                "round": round_number,
                                "teacher_input": teacher_text,
                                "student_response": student_record["content"],
                                "response_metadata": _json_metadata(
                                    student_record.get("response_metadata")
                                ),
                                "teaching_behavior": behavior,
                                "student_evidence": trace_round.get("evidence"),
                                "misconception_before": trace_round.get("misconception_before"),
                                "misconception_after": trace_round.get("misconception_after"),
                                "state_before": trace_round.get("state_before"),
                                "state_after": trace_round.get("state_after"),
                                "response_source": trace_round.get("response_source"),
                                "learning_evidence_allowed": trace_round.get(
                                    "learning_evidence_allowed"
                                ),
                            }
                        )

                    ended = client.post(f"/api/sessions/{session_id}/end")
                    ended.raise_for_status()
                    completed = ended.json()
                    report["students"].append(
                        {
                            "student_name": student_name,
                            "session_id": session_id,
                            "session_status": completed["status"],
                            "dialogue_records": completed["dialogue_records"],
                            "turns": turns,
                            "behavior_summary": completed["behavior_summary"],
                            "cognitive_trace": completed["cognitive_trace"],
                            "evaluation": completed.get("evaluation"),
                        }
                    )

            isolated_engine.dispose()
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        database.SessionLocal.configure(bind=previous_bind)
        database.engine = previous_engine

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Provider: mock")
    print("Students: A, B, C")
    print("Rounds per student: 2")
    print("Remote API calls: 0")
    print(f"Report: {report_path}")
    for student in report["students"]:
        print(f"\n{student['student_name']} (session {student['session_id']})")
        for turn in student["turns"]:
            print(f"  第{turn['round']}轮教师：{turn['teacher_input']}")
            print(f"  第{turn['round']}轮学生：{turn['student_response']}")
            print(f"  来源：{turn['response_source']}；学习证据允许：{turn['learning_evidence_allowed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
