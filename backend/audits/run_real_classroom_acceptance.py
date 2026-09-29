"""Opt-in 3-profile, 5-turn Real LLM classroom acceptance through Session API.

Uses a disposable SQLite database and writes a timestamped transcript/evidence
report. Never records API credentials, authorization headers, or prompts.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


TEACHER_TURNS = (
    ("ordinary_question", "你觉得一次函数图像中，k 和 b 分别会影响什么？"),
    ("misconception_probe", "在 y=2x+3 中，2 和 3 分别有什么作用？你觉得哪个会影响倾斜程度？"),
    ("follow_up", "为什么？那前一个呢？请结合刚才的式子说说。"),
    ("direct_answer", "我告诉你结论：k 决定倾斜程度，b 只改变截距和上下位置。现在请用自己的话说说你怎么理解。"),
    ("transfer", "换一道新题：y=-3x+1 和 y=-3x+6 哪条更陡？为什么？"),
)
PROFILE_NAMES = {"student_a": "学生 A", "student_b": "学生 B", "student_c": "学生 C"}
OWNER_TOKEN = "d" * 64


def write_report(report: dict) -> Path:
    out = Path(__file__).with_name(
        "real_classroom_acceptance_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
    )
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> int:
    from app.core.config import get_settings

    settings = get_settings()
    enabled = os.getenv("RUN_REAL_LLM_VALIDATION", "false").strip().lower() == "true"
    if settings.llm_provider != "real" or not enabled:
        print("ABORTED: set LLM_PROVIDER=real and RUN_REAL_LLM_VALIDATION=true; no API calls made.")
        return 2
    if not settings.llm_api_key or not settings.llm_api_url or not settings.llm_model:
        print("ABORTED: LLM configuration incomplete; no API calls made.")
        return 2

    print("Real classroom acceptance enabled")
    print(f"Provider: {settings.llm_provider}")
    print(f"Model: {settings.llm_model}")
    print("Profiles: student_a, student_b, student_c")
    print("Rounds per profile: 5")
    print("Expected base calls: 33; renderer retry calls may increase this.")
    print("Database: disposable temporary SQLite; production/local DB will not be touched.")

    report: dict = {
        "status": "running",
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "profiles": {},
        "call_accounting": {
            "expected_base_calls": 33,
            "successful_renderer_turns": 0,
            "renderer_retry_calls": 0,
            "estimated_provider_calls": 0,
            "note": "Estimate counts one behavior-analysis call and one initial renderer call per turn, plus one evaluation call per session; renderer retries are counted from response metadata.",
        },
        "pipeline_accounting": {
            "validator_rejected_turns": 0,
            "degraded_turns": 0,
            "fallback_reasons": [],
        },
        "scoring_evidence_audit": {},
        "limitations": [
            "Style and naturalness judgments require human review of the raw transcripts.",
            "Evaluation uses the production scoring engine; this report does not alter scores or evidence.",
        ],
    }

    with tempfile.TemporaryDirectory(prefix="teaching-acceptance-") as temp_dir:
        os.environ["TEACHING_DATABASE_PATH"] = str(Path(temp_dir) / "acceptance.db")
        os.environ["LLM_PROVIDER"] = "real"

        from fastapi.testclient import TestClient
        from app.main import app
        from app.database.session import engine

        with TestClient(app, headers={"X-Practice-Token": OWNER_TOKEN}) as client:
            scenarios_response = client.get("/api/scenarios")
            students_response = client.get("/api/virtual-students")
            if scenarios_response.status_code != 200 or students_response.status_code != 200:
                report["status"] = "setup_failed"
                report["setup_errors"] = {
                    "scenarios_http": scenarios_response.status_code,
                    "students_http": students_response.status_code,
                }
            else:
                scenarios = scenarios_response.json()
                students = {item["name"]: item for item in students_response.json()}
                scenario = next(
                    (item for item in scenarios if item.get("topic") == "一次函数"),
                    scenarios[0] if scenarios else None,
                )
                if scenario is None or any(name not in students for name in PROFILE_NAMES.values()):
                    report["status"] = "setup_failed"
                    report["setup_errors"] = {
                        "scenario_found": scenario is not None,
                        "students_found": sorted(students),
                    }
                else:
                    report["status"] = "completed"
                    for profile_id, student_name in PROFILE_NAMES.items():
                        profile_result = {
                            "profile_id": profile_id,
                            "student_name": student_name,
                            "session_http": None,
                            "session_id": None,
                            "turns": [],
                            "evaluation_http": None,
                            "evaluation": None,
                        }
                        report["profiles"][profile_id] = profile_result
                        created = client.post(
                            "/api/sessions",
                            json={
                                "scenario_id": scenario["id"],
                                "virtual_student_id": students[student_name]["id"],
                            },
                        )
                        profile_result["session_http"] = created.status_code
                        if created.status_code != 200:
                            profile_result["session_error"] = created.text[:500]
                            report["status"] = "partial"
                            continue

                        session = created.json()
                        session_id = session["id"]
                        profile_result["session_id"] = session_id
                        for turn_no, (case_id, teacher_text) in enumerate(TEACHER_TURNS, start=1):
                            response = client.post(
                                f"/api/sessions/{session_id}/messages",
                                json={
                                    "teacher_text": teacher_text,
                                    "request_id": f"{profile_id}-acceptance-{turn_no}",
                                    "expected_version": session["version"],
                                },
                            )
                            if response.status_code != 200:
                                profile_result["turns"].append(
                                    {
                                        "round": turn_no,
                                        "case_id": case_id,
                                        "teacher_input": teacher_text,
                                        "http_status": response.status_code,
                                        "error": response.text[:500],
                                    }
                                )
                                report["status"] = "partial"
                                break

                            session = response.json()
                            dialogues = session.get("dialogue_records", [])
                            student_record = next(
                                (record for record in reversed(dialogues) if record.get("speaker") == "student"),
                                None,
                            )
                            trace_rounds = session.get("cognitive_trace", {}).get("rounds", [])
                            trace = trace_rounds[-1] if trace_rounds else {}
                            metadata_raw = student_record.get("response_metadata", "{}") if student_record else "{}"
                            try:
                                metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
                            except (TypeError, json.JSONDecodeError):
                                metadata = {"metadata_parse_error": True}
                            retries = int(metadata.get("retries", 0) or 0) if isinstance(metadata, dict) else 0
                            source = metadata.get("source") if isinstance(metadata, dict) else None
                            if source == "real":
                                report["call_accounting"]["successful_renderer_turns"] += 1
                            report["call_accounting"]["renderer_retry_calls"] += retries
                            if retries:
                                report["pipeline_accounting"]["validator_rejected_turns"] += 1
                            if source != "real":
                                report["pipeline_accounting"]["degraded_turns"] += 1
                            if isinstance(metadata, dict) and metadata.get("fallback_reason"):
                                report["pipeline_accounting"]["fallback_reasons"].append(
                                    {
                                        "profile_id": profile_id,
                                        "round": turn_no,
                                        "source": source,
                                        "reason": metadata["fallback_reason"],
                                    }
                                )
                            report["profiles"][profile_id]["turns"].append(
                                {
                                    "round": turn_no,
                                    "case_id": case_id,
                                    "teacher_input": teacher_text,
                                    "student_response": student_record.get("content") if student_record else None,
                                    "response_metadata": metadata,
                                    "validator_rejected_before_retry": bool(retries),
                                    "retry_count": retries,
                                    "degraded": source != "real",
                                    "behavior": next(
                                        (item for item in reversed(session.get("behavior_records", [])) if item.get("dialogue_record_id") == (dialogues[-2].get("id") if len(dialogues) >= 2 else None)),
                                        None,
                                    ),
                                    "state_after": trace.get("state_after"),
                                    "misconception_after": trace.get("misconception_after"),
                                    "student_response_evidence": trace.get("evidence"),
                                    "correction_opportunity": trace.get("correction_opportunity"),
                                }
                            )

                        ended = client.post(f"/api/sessions/{session_id}/end")
                        profile_result["evaluation_http"] = ended.status_code
                        if ended.status_code == 200:
                            final_session = ended.json()
                            evaluation = final_session.get("evaluation")
                            if evaluation is None:
                                evaluation_response = client.get(f"/api/sessions/{session_id}/evaluation")
                                profile_result["evaluation_http"] = evaluation_response.status_code
                                evaluation = evaluation_response.json() if evaluation_response.status_code == 200 else None
                            profile_result["evaluation"] = evaluation
                            if evaluation is None:
                                report["status"] = "partial"
                            else:
                                dimensions = evaluation.get("evidence", {}).get("dimensions", {})
                                report["scoring_evidence_audit"][profile_id] = {
                                    "rubric_version": evaluation.get("rubric_version"),
                                    "analysis_source": evaluation.get("analysis_source"),
                                    "scores": {
                                        key: evaluation.get(key)
                                        for key in (
                                            "knowledge_accuracy",
                                            "questioning",
                                            "feedback",
                                            "misconception_diagnosis",
                                            "scaffolding",
                                            "overall_score",
                                        )
                                    },
                                    "dimensions": dimensions,
                                    "key_teaching_snippets": evaluation.get("key_teaching_snippets", []),
                                    "temporal_reference_check": audit_temporal_references(
                                        dimensions, profile_result["turns"]
                                    ),
                                }
                        else:
                            profile_result["evaluation_error"] = ended.text[:500]
                            report["status"] = "partial"

        engine.dispose()

    report["call_accounting"]["estimated_provider_calls"] = (
        2 * sum(
            1
            for item in report["profiles"].values()
            for turn in item.get("turns", [])
            if turn.get("student_response") is not None
        )
        + report["call_accounting"]["renderer_retry_calls"]
        + sum(1 for item in report["profiles"].values() if item.get("evaluation") is not None)
    )
    path = write_report(report)
    print(f"Status: {report['status']}")
    print(f"Successful real renderer turns: {report['call_accounting']['successful_renderer_turns']} / 15")
    print(f"Estimated provider calls: {report['call_accounting']['estimated_provider_calls']}")
    print(f"Report: {path}")
    return 0 if report["status"] == "completed" else 1


def audit_temporal_references(dimensions: dict, turns: list[dict]) -> dict:
    """Check references are in-range and expose the associated teacher/student pair."""
    valid_rounds = {int(row["round"]) for row in turns if row.get("student_response") is not None}
    findings = []
    malformed = []
    for dimension, entries in dimensions.items():
        for entry in (entries if isinstance(entries, list) else []):
            for check in entry.get("checks", []):
                if not isinstance(check, dict):
                    continue
                refs = check.get("rounds", [])
                invalid = [ref for ref in refs if ref not in valid_rounds]
                if invalid:
                    malformed.append({"dimension": dimension, "criterion": check.get("criterion"), "invalid_rounds": invalid})
                findings.append(
                    {
                        "dimension": dimension,
                        "criterion": check.get("criterion"),
                        "value": check.get("value"),
                        "rounds": refs,
                        "reason": check.get("reason"),
                        "teacher_student_pairs": [
                            {
                                "round": ref,
                                "teacher": next((row["teacher_input"] for row in turns if row["round"] == ref), None),
                                "student": next((row["student_response"] for row in turns if row["round"] == ref), None),
                            }
                            for ref in refs if ref in valid_rounds
                        ],
                    }
                )
    return {
        "all_references_in_range": not malformed,
        "invalid_references": malformed,
        "checks": findings,
        "review_note": "逐项引用需结合相邻轮次审查：教师支架应归于教师行为及学生随后参与；纠错效果应引用纠错之后的独立学生回答，而不能只引用纠错前回答。",
    }


if __name__ == "__main__":
    raise SystemExit(main())
