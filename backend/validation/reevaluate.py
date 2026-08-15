"""Offline re-evaluation for saved validation reports.

This module never calls an LLM. It preserves the original evidence and writes
new analyzer output into a separate report file for before/after comparison.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.virtual_student import StudentResponseEvidenceAnalyzer


def reevaluate_report(input_path: Path, output_path: Path | None = None) -> Path:
    data: dict[str, Any] = json.loads(input_path.read_text(encoding="utf-8"))
    analyzer = StudentResponseEvidenceAnalyzer()

    for run in data.get("runs", []):
        previous_teacher_text = ""
        for turn in run.get("turns", []):
            original = dict(turn.get("student_response_evidence", {}))
            turn["original_student_response_evidence"] = original
            evidence = analyzer.analyze(
                str(turn.get("student_response", "")),
                teacher_text=str(turn.get("teacher_input", "")),
                previous_teacher_text=previous_teacher_text,
            )
            turn["reevaluated_student_response_evidence"] = evidence.to_dict()
            previous_teacher_text = str(turn.get("teacher_input", ""))

    target = output_path or input_path.with_name(
        f"{input_path.stem}-reevaluated{input_path.suffix}"
    )
    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline validation report re-evaluation")
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = reevaluate_report(args.report, args.output)
    print(f"Offline re-evaluation report: {output}")


if __name__ == "__main__":
    main()
