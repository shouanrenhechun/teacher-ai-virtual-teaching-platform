"""Offline re-evaluation for saved validation reports.

This module never calls an LLM. It preserves the original evidence and writes
new analyzer output into a separate report file for before/after comparison.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.virtual_student import (
    StudentResponseEvidenceAnalyzer,
    VirtualStudentEngine,
    detect_teacher_behavior,
)
from .case_loader import load_student_profile, load_validation_cases
from .metrics import evaluate_run, summarize_metrics
from .models import ValidationTurnResult


def reevaluate_report(input_path: Path, output_path: Path | None = None) -> Path:
    data: dict[str, Any] = json.loads(input_path.read_text(encoding="utf-8"))
    analyzer = StudentResponseEvidenceAnalyzer()
    cases = {case.case_id: case for case in load_validation_cases()}
    reevaluated_runs: list[dict[str, Any]] = []

    for run in data.get("runs", []):
        previous_teacher_text = ""
        reevaluated_turns: list[ValidationTurnResult] = []
        case = cases.get(str(run.get("case_id", "")))
        engine = None
        if case is not None:
            profile_id = str(data.get("student_profile_id", "student_a"))
            engine = VirtualStudentEngine(
                load_student_profile(
                    profile_id=profile_id,
                    misconception_type=case.misconception_type,
                )
            )
        for turn in run.get("turns", []):
            original = dict(turn.get("student_response_evidence", {}))
            turn["original_student_response_evidence"] = original
            teacher_input = str(turn.get("teacher_input", ""))
            student_response = str(turn.get("student_response", ""))
            if engine is not None:
                state_before = _snapshot_dict(engine.snapshot())
                behavior = detect_teacher_behavior(teacher_input).value
                opportunity = engine.get_correction_opportunity(teacher_input)
                engine.update_from_teacher_text(teacher_input)
                evidence = engine.apply_student_response_evidence(
                    student_response,
                    teacher_input,
                    opportunity,
                    previous_teacher_text=previous_teacher_text,
                )
                state_after = _snapshot_dict(engine.snapshot())
                turn["reevaluated_state_before"] = state_before
                turn["reevaluated_state_after"] = state_after
                turn["reevaluated_misconception_status_before"] = _status(state_before)
                turn["reevaluated_misconception_status_after"] = _status(state_after)
                turn["reevaluated_correction_opportunity"] = opportunity
            else:
                state_before = dict(turn.get("state_before", {}))
                state_after = dict(turn.get("state_after", {}))
                behavior = str(turn.get("behavior", "neutral"))
                opportunity = dict(turn.get("correction_opportunity", {}))
                evidence = analyzer.analyze(
                    student_response,
                    teacher_text=teacher_input,
                    previous_teacher_text=previous_teacher_text,
                )
            turn["reevaluated_student_response_evidence"] = evidence.to_dict()
            reevaluated_turns.append(
                _turn_from_dict(
                    turn,
                    evidence=evidence.to_dict(),
                    state_before=state_before,
                    state_after=state_after,
                    behavior=behavior,
                    correction_opportunity=opportunity,
                )
            )
            previous_teacher_text = teacher_input

        if case is not None and reevaluated_turns:
            metrics = evaluate_run(case, reevaluated_turns)
            metric_dict = {
                name: result.to_dict() for name, result in metrics.items()
            }
            run["reevaluated_metrics"] = metric_dict
            run["reevaluated_status"] = _status_from_metrics(metric_dict)
            reevaluated_runs.append({**run, "metrics": metric_dict})

    target = output_path or input_path.with_name(
        f"{input_path.stem}-reevaluated{input_path.suffix}"
    )
    if reevaluated_runs:
        categories: dict[str, list[dict[str, Any]]] = {}
        for run in reevaluated_runs:
            categories.setdefault(str(run["category"]), []).append(run)
        statuses = [str(run["reevaluated_status"]) for run in reevaluated_runs]
        original_basic = dict(data.get("basic", {}))
        data["reevaluated_basic"] = {
            **original_basic,
            "successful_runs": statuses.count("passed"),
            "partial_runs": statuses.count("partial"),
            "failed_runs": statuses.count("failed"),
        }
        data["reevaluated_overall_metrics"] = summarize_metrics(reevaluated_runs)
        data["reevaluated_category_metrics"] = {
            category: summarize_metrics(category_runs)
            for category, category_runs in sorted(categories.items())
        }
    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def _turn_from_dict(
    data: dict[str, Any],
    *,
    evidence: dict[str, object],
    state_before: dict[str, Any] | None = None,
    state_after: dict[str, Any] | None = None,
    behavior: str | None = None,
    correction_opportunity: dict[str, object] | None = None,
) -> ValidationTurnResult:
    """Build the metric-layer turn object without touching the original report fields."""
    return ValidationTurnResult(
        sequence=int(data.get("sequence", 1)),
        teacher_input=str(data.get("teacher_input", "")),
        student_response=str(data.get("student_response", "")),
        state_before=state_before if state_before is not None else dict(data.get("state_before", {})),
        state_after=state_after if state_after is not None else dict(data.get("state_after", {})),
        behavior=behavior or str(data.get("behavior", "neutral")),
        indicators=dict(data.get("indicators", {})),
        student_response_evidence=evidence,
        misconception_status_before=str(
            data.get("misconception_status_before", "active")
        ),
        misconception_status_after=str(
            data.get("misconception_status_after", "active")
        ),
        correction_opportunity=correction_opportunity or dict(data.get("correction_opportunity", {})),
    )


def _status(snapshot: dict[str, Any]) -> str:
    misconceptions = snapshot.get("misconceptions", [])
    return str(misconceptions[0].get("status", "active")) if misconceptions else "active"


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    return {
        "knowledge_states": [
            {
                "knowledge_point": item.knowledge_point,
                "mastery": item.mastery,
            }
            for item in snapshot.knowledge_states
        ],
        "misconceptions": [
            {
                "name": item.name,
                "concept": item.concept,
                "description": item.description,
                "semantic_type": item.semantic_type,
                "strength": item.strength,
                "correction_condition": item.correction_condition,
                "triggered": item.triggered,
                "correction_started": item.correction_started,
                "corrected": item.corrected,
                "status": item.status,
                "clean_evidence_streak": item.clean_evidence_streak,
                "transfer_evidence": item.transfer_evidence,
                "stable_correct_evidence_count": item.stable_correct_evidence_count,
            }
            for item in snapshot.misconceptions
        ],
        "classroom_state": {
            "understanding": snapshot.classroom_state.understanding,
            "confusion": snapshot.classroom_state.confusion,
            "engagement": snapshot.classroom_state.engagement,
            "confidence": snapshot.classroom_state.confidence,
            "surface_recall": snapshot.classroom_state.surface_recall,
        },
    }


def _status_from_metrics(metrics: dict[str, dict[str, Any]]) -> str:
    hard_failure = any(
        item.get("applicable")
        and not item.get("passed")
        and item.get("level") != "partial"
        for item in metrics.values()
    )
    if hard_failure:
        return "failed"
    if any(
        item.get("applicable") and item.get("level") == "partial"
        for item in metrics.values()
    ):
        return "partial"
    return "passed"


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline validation report re-evaluation")
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = reevaluate_report(args.report, args.output)
    print(f"Offline re-evaluation report: {output}")


if __name__ == "__main__":
    main()
