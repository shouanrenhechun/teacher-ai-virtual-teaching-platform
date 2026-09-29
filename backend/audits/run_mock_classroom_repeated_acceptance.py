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
sys.path.insert(0, str(BACKEND_DIR))

from app.api.llm_routes import llm_client_dependency  # noqa: E402
from app.database import session as database  # noqa: E402
from app.main import app  # noqa: E402
from app.services.llm.mock import MockLLMClient  # noqa: E402


OWNER_TOKEN = "a" * 64
STUDENTS = ("学生 A", "学生 B", "学生 C")
RUNS_PER_STUDENT = 2
TEACHER_TURNS = (
    "在 y=2x+3 中，2 和 3 分别有什么作用？哪个会影响直线的倾斜程度？",
    "你刚才说 b 可能影响倾斜。你为什么会这样想？能说说理由吗？",
    "答案是：k 决定直线的倾斜程度，b 决定纵截距和上下位置。你先用自己的话说说这两个作用。",
    "比较 y=2x+3 和 y=2x+5，哪条更陡？为什么？",
    "那如果只改变 b、不改变 k，图像会怎么变化？请说出理由。",
)


def _metadata(value: str | dict | None) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"raw": parsed}
        except json.JSONDecodeError:
            return {"raw": value}
    return {}


def _markdown(report: dict, json_path: Path) -> str:
    lines = [
        "# A/B/C Mock 重复课堂验收记录",
        "",
        "## 测试概况",
        "",
        f"- 场景：{report['scenario_title']}",
        f"- Provider：{report['provider']}（{report['mode']}）",
        f"- 测试次数：每名学生 {RUNS_PER_STUDENT} 次，每次 {len(TEACHER_TURNS)} 轮；共 {len(report['sessions'])} 个会话、{sum(len(s['turns']) for s in report['sessions'])} 轮",
        "- 远程 API 调用：0；数据库：临时 SQLite",
        "- 说明：用于检查 Mock、会话 API、记录和规则状态流转，不代表真实模型自然度。",
        "",
        "## 教师话语脚本",
        "",
    ]
    for index, utterance in enumerate(TEACHER_TURNS, start=1):
        lines.append(f"{index}. {utterance}")
    lines.append("")

    for session in report["sessions"]:
        lines.extend(
            [
                f"## {session['student_name']} · 第 {session['run']} 次",
                "",
                f"会话 ID：{session['session_id']}；状态：{session['session_status']}。",
                "",
            ]
        )
        for turn in session["turns"]:
            evidence = turn.get("student_evidence") or {}
            before = turn.get("misconception_before") or {}
            after = turn.get("misconception_after") or {}
            behavior = turn.get("teaching_behavior") or {}
            lines.extend(
                [
                    f"### 第 {turn['round']} 轮",
                    "",
                    f"**教师：** {turn['teacher_input']}",
                    "",
                    f"**学生：** {turn['student_response']}",
                    "",
                    f"- 回复来源：{turn.get('response_source')}；重试：{turn['response_metadata'].get('retries', 0)}；允许作为学习证据：{turn.get('learning_evidence_allowed')}",
                    f"- 教师行为：{behavior.get('action_type')}；知识准确性：{behavior.get('knowledge_accuracy')}；清晰度：{behavior.get('clarity')}；直接给答案：{behavior.get('gave_answer_directly')}",
                    f"- 学生证据：结论={evidence.get('conclusion_level')}；解释={evidence.get('explains_reason_correctly')}；残留错误={evidence.get('shows_residual_misconception')}；概念性犹豫={evidence.get('conceptual_uncertainty')}；迁移={evidence.get('transfer_success')}；复述教师={evidence.get('parrots_teacher')}",
                    f"- 认知错误状态：{before.get('status')} / {before.get('strength')} → {after.get('status')} / {after.get('strength')}",
                    "",
                ]
            )
        evaluation = session.get("evaluation") or {}
        lines.extend(
            [
                "### 会话评价",
                "",
                f"- 五维：知识准确性 {evaluation.get('knowledge_accuracy')}；提问 {evaluation.get('questioning')}；反馈 {evaluation.get('feedback')}；错误诊断 {evaluation.get('misconception_diagnosis')}；支架式教学 {evaluation.get('scaffolding')}",
                f"- 综合分：{evaluation.get('overall_score')}",
                f"- 摘要：{evaluation.get('summary')}",
            ]
        )
        for problem in evaluation.get("problems") or []:
            lines.append(f"- 待改进：{problem}")
        lines.append("")

    lines.extend(
        [
            "## 重复性与结论",
            "",
            "请注意：该报告保留每个会话的逐轮回复和证据。Mock 是确定性规则模拟，同一输入可能返回相同话语；不能据此判断真实模型是否稳定，也不能把 Mock 回复当作真实学生行为。",
            "",
            f"完整原始 JSON：[{json_path.name}](./{json_path.name})。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    audits_dir = BACKEND_DIR / "audits"
    json_path = audits_dir / f"mock_classroom_repeated_{timestamp}.json"
    markdown_path = audits_dir / f"mock_classroom_repeated_{timestamp}.md"
    client_mock = MockLLMClient()
    original_engine = database.engine
    original_bind = database.SessionLocal.kw.get("bind")
    original_overrides = app.dependency_overrides.copy()
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": "mock",
        "model": None,
        "mode": "offline deterministic Mock; no remote API calls",
        "scenario_title": "一次函数：k 与 b 的意义",
        "runs_per_student": RUNS_PER_STUDENT,
        "rounds_per_session": len(TEACHER_TURNS),
        "teacher_turns": list(TEACHER_TURNS),
        "sessions": [],
    }

    try:
        with tempfile.TemporaryDirectory(prefix="mock-classroom-repeated-") as temp_dir:
            db_path = Path(temp_dir) / "isolated-test.db"
            isolated_engine = create_engine(
                f"sqlite:///{db_path.as_posix()}",
                connect_args={"check_same_thread": False},
            )
            database.engine = isolated_engine
            database.DATABASE_DIR = Path(temp_dir)
            database.DATABASE_PATH = db_path
            database.SessionLocal.configure(bind=isolated_engine)
            app.dependency_overrides[llm_client_dependency] = lambda: client_mock

            with TestClient(app, headers={"X-Practice-Token": OWNER_TOKEN}) as api:
                scenarios_response = api.get("/api/scenarios")
                students_response = api.get("/api/virtual-students")
                scenarios_response.raise_for_status()
                students_response.raise_for_status()
                scenario = next(
                    row for row in scenarios_response.json()
                    if row["title"] == report["scenario_title"]
                )
                students = {row["name"]: row for row in students_response.json()}

                for name in STUDENTS:
                    for run_number in range(1, RUNS_PER_STUDENT + 1):
                        created = api.post(
                            "/api/sessions",
                            json={
                                "scenario_id": scenario["id"],
                                "virtual_student_id": students[name]["id"],
                            },
                        )
                        created.raise_for_status()
                        current = created.json()
                        session_id = current["id"]
                        turns = []

                        for round_number, teacher_text in enumerate(TEACHER_TURNS, start=1):
                            response = api.post(
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
                                record for record in reversed(current["dialogue_records"])
                                if record["speaker"] == "student"
                            )
                            trace_round = current["cognitive_trace"]["rounds"][-1]
                            turns.append(
                                {
                                    "round": round_number,
                                    "teacher_input": teacher_text,
                                    "student_response": student_record["content"],
                                    "response_metadata": _metadata(
                                        student_record.get("response_metadata")
                                    ),
                                    "teaching_behavior": current["behavior_records"][-1],
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

                        ended = api.post(f"/api/sessions/{session_id}/end")
                        ended.raise_for_status()
                        completed = ended.json()
                        report["sessions"].append(
                            {
                                "student_name": name,
                                "run": run_number,
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
        app.dependency_overrides.update(original_overrides)
        database.SessionLocal.configure(bind=original_bind)
        database.engine = original_engine

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(report, json_path), encoding="utf-8")
    successful_sessions = sum(item["session_status"] == "completed" for item in report["sessions"])
    turns_total = sum(len(item["turns"]) for item in report["sessions"])
    print("Provider: mock")
    print("Students: A, B, C")
    print(f"Runs per student: {RUNS_PER_STUDENT}")
    print(f"Rounds per session: {len(TEACHER_TURNS)}")
    print(f"Completed sessions: {successful_sessions}/{len(report['sessions'])}")
    print(f"Saved dialogue turns: {turns_total}")
    print("Remote API calls: 0")
    print(f"JSON report: {json_path}")
    print(f"Readable report: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
