from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.virtual_student import (
    KnowledgeStateValue,
    MisconceptionState,
    StudentProfile,
)

from .models import ValidationCase


CASE_DIR = Path(__file__).resolve().parent / "cases"


def load_student_a_profile(
    path: Path | None = None,
    *,
    misconception_type: str = "linear_kb",
) -> StudentProfile:
    profile_path = path or (
        CASE_DIR / "student_a_binomial_square.json"
        if misconception_type == "binomial_square"
        else CASE_DIR / "student_a.json"
    )
    data = _read_json(profile_path)
    return StudentProfile(
        name=str(data["name"]),
        grade=str(data["grade"]),
        base_level=float(data["base_level"]),
        personality_description=str(data["personality_description"]),
        initiative=float(data["initiative"]),
        confidence=float(data["confidence"]),
        knowledge_states=[
            KnowledgeStateValue(
                knowledge_point=str(item["knowledge_point"]),
                mastery=float(item["mastery"]),
            )
            for item in data["knowledge_states"]
        ],
        misconceptions=[
            MisconceptionState(
                name=str(item["name"]),
                concept=str(item["concept"]),
                description=str(item["description"]),
                strength=float(item["strength"]),
                correction_condition=str(item["correction_condition"]),
                semantic_type=str(item.get("semantic_type", misconception_type)),
            )
            for item in data["misconceptions"]
        ],
    )


def load_validation_cases(
    path: Path | None = None,
    case_ids: set[str] | None = None,
) -> list[ValidationCase]:
    raw_cases = _read_json(path or CASE_DIR / "validation_cases.json")
    cases = [ValidationCase.from_dict(item) for item in raw_cases]
    if case_ids:
        cases = [case for case in cases if case.case_id in case_ids]
        missing = case_ids - {case.case_id for case in cases}
        if missing:
            raise ValueError(f"未找到验证案例：{', '.join(sorted(missing))}")
    return cases


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)
