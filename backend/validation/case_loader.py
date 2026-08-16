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
PROFILE_FILES = {
    "student_a": CASE_DIR / "student_a.json",
    "student_b": CASE_DIR / "student_b.json",
}


def load_student_profile(
    profile_id: str = "student_a",
    path: Path | None = None,
    *,
    misconception_type: str = "linear_kb",
) -> StudentProfile:
    if path is None:
        try:
            profile_path = PROFILE_FILES[profile_id]
        except KeyError as exc:
            raise ValueError(f"未找到虚拟学生画像：{profile_id}") from exc
    else:
        profile_path = path

    if misconception_type != "linear_kb" and profile_id == "student_b":
        raise ValueError("Student B 当前只支持 linear_kb 验证")

    data = _read_json(profile_path)
    return StudentProfile(
        profile_id=str(data.get("profile_id", profile_id)),
        name=str(data["name"]),
        grade=str(data["grade"]),
        base_level=float(data["base_level"]),
        personality_description=str(data["personality_description"]),
        initiative=float(data["initiative"]),
        confidence=float(data["confidence"]),
        confidence_style=str(data.get("confidence_style", "自然表达，不刻意改变知识判断。")),
        response_style=str(data.get("response_style", "回答自然、简短，符合课堂中的学生表达。")),
        guessing_tendency=str(data.get("guessing_tendency", "遇到不确定内容时可以先给出有限猜测。")),
        confirmation_seeking=str(data.get("confirmation_seeking", "必要时根据教师提示确认自己的理解。")),
        verbosity=str(data.get("verbosity", "一到三句话。")),
        correction_style=str(data.get("correction_style", "接受证据后逐步修正，不因教师一句话立即宣称完全掌握。")),
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
    return load_student_profile(
        profile_id="student_a",
        path=profile_path,
        misconception_type=misconception_type,
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
