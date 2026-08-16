"""Offline replay of saved student responses through the current state engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.virtual_student import VirtualStudentEngine, detect_teacher_behavior

from .case_loader import load_student_a_profile, load_validation_cases
from .metrics import evaluate_run
from .models import ValidationTurnResult
from .runner import _snapshot_dict


def replay_report(input_path: Path, output_path: Path | None = None) -> Path:
    data: dict[str, Any] = json.loads(input_path.read_text(encoding="utf-8"))
    replay_runs: list[dict[str, Any]] = []

    for old_run in data.get("runs", []):
        case = load_validation_cases(case_ids={str(old_run["case_id"])})[0]
        engine = VirtualStudentEngine(load_student_a_profile())
        history: list[tuple[str, str]] = []
        replay_turns: list[ValidationTurnResult] = []

        for old_turn in old_run.get("turns", []):
            teacher_input = str(old_turn.get("teacher_input", ""))
            response = str(old_turn.get("student_response", ""))
            before = _snapshot_dict(engine.snapshot())
            behavior = detect_teacher_behavior(teacher_input)
            opportunity = engine.get_correction_opportunity(teacher_input)
            previous_teacher_text = next(
                (
                    content
                    for speaker, content in reversed(history)
                    if speaker == "teacher"
                ),
                "",
            )
            engine.update_from_teacher_text(teacher_input)
            evidence = engine.apply_student_response_evidence(
                response,
                teacher_input,
                opportunity,
                previous_teacher_text=previous_teacher_text,
            )
            after = _snapshot_dict(engine.snapshot())
            replay_turns.append(
                ValidationTurnResult(
                    sequence=int(old_turn["sequence"]),
                    teacher_input=teacher_input,
                    student_response=response,
                    state_before=before,
                    state_after=after,
                    behavior=behavior.value,
                    indicators=dict(old_turn.get("indicators", {})),
                    student_response_evidence=evidence.to_dict(),
                    misconception_status_before=before["misconceptions"][0]["status"],
                    misconception_status_after=after["misconceptions"][0]["status"],
                    correction_opportunity=opportunity,
                )
            )
            history.extend([("teacher", teacher_input), ("student", response)])

        replay_dicts = [turn.to_dict() for turn in replay_turns]
        old_final = _first_misconception(old_run.get("turns", [])[-1].get("state_after", {}))
        new_final = _first_misconception(replay_dicts[-1].get("state_after", {}))
        replay_runs.append(
            {
                "run_index": old_run["run_index"],
                "old_status": old_run.get("status"),
                "old_final_misconception": old_final,
                "old_correctability": old_run.get("metrics", {}).get("Correctability"),
                "new_final_misconception": new_final,
                "new_metrics": {
                    name: metric.to_dict()
                    for name, metric in evaluate_run(case, replay_turns).items()
                },
                "turns": replay_dicts,
            }
        )

    data["state_replay"] = {
        "source_report": str(input_path),
        "runs": replay_runs,
    }
    target = output_path or input_path.with_name(
        f"{input_path.stem}-state-replayed{input_path.suffix}"
    )
    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def _first_misconception(snapshot: dict[str, Any]) -> dict[str, Any]:
    misconceptions = snapshot.get("misconceptions", [])
    return dict(misconceptions[0]) if misconceptions else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline state replay for validation reports")
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = replay_report(args.report, args.output)
    print(f"Offline state replay report: {output}")


if __name__ == "__main__":
    main()
