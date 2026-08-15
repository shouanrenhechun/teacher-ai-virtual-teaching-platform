from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.llm.base import LLMClient, LLMContext, LLMServiceError
from app.services.llm.mock import MockLLMClient
from validation.case_loader import load_validation_cases
from validation.runner import (
    RealValidationDisabledError,
    ValidationConfig,
    run_validation,
    write_report,
)


def test_validation_cases_cover_required_categories() -> None:
    cases = load_validation_cases()
    assert len(cases) == 19
    categories = {case.category for case in cases}
    assert {
        "普通开场",
        "直接询问错误知识点",
        "教师直接告诉答案",
        "启发式纠正",
        "追问理解",
        "教师错误讲解",
        "超纲诱导",
        "课堂无关问题",
        "多轮：无有效纠正",
        "多轮：有效纠正",
        "多轮：错误教学",
    } <= categories


def test_mock_validation_runs_and_exports_report(tmp_path: Path) -> None:
    cases = load_validation_cases()
    config = ValidationConfig(
        provider="mock",
        model="mock",
        runs_per_case=1,
        report_dir=tmp_path,
    )

    report = run_validation(config, cases, client=MockLLMClient())
    path = write_report(report, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["provider"] == "mock"
    assert payload["basic"]["total_cases"] == 19
    assert payload["basic"]["total_runs"] == 19
    assert payload["basic"]["total_calls"] == 27
    assert payload["basic"]["api_failures"] == 0
    assert payload["overall_metrics"]["Role Consistency"]["total"] == 19
    assert payload["category_metrics"]["多轮：有效纠正"]
    assert payload["failure_cases"]
    assert "LLM_API_KEY" not in path.read_text(encoding="utf-8")


def test_mock_effective_correction_reduces_misconception() -> None:
    case = next(
        case
        for case in load_validation_cases()
        if case.case_id == "trajectory_effective_correction"
    )
    report = run_validation(
        ValidationConfig(provider="mock", model="mock", runs_per_case=1),
        [case],
        client=MockLLMClient(),
    )
    run = report.runs[0]
    assert run["metrics"]["Correctability"]["passed"] is True
    first_strength = run["turns"][0]["state_before"]["misconceptions"][0]["strength"]
    final_strength = run["turns"][-1]["state_after"]["misconceptions"][0]["strength"]
    assert final_strength < first_strength


def test_real_provider_requires_explicit_safety_switch() -> None:
    config = ValidationConfig(
        provider="real",
        model="test-model",
        runs_per_case=1,
        real_validation_enabled=False,
    )
    case = load_validation_cases(case_ids={"opening_01"})[0]

    with pytest.raises(RealValidationDisabledError):
        run_validation(config, [case], client=MockLLMClient())


class FailingValidationClient(LLMClient):
    provider = "real"

    def respond(self, teacher_text: str, context: LLMContext | None = None) -> str:
        raise LLMServiceError("模拟模型服务超时")


def test_real_validation_failure_is_saved_without_crashing_suite(tmp_path: Path) -> None:
    case = load_validation_cases(case_ids={"opening_01"})[0]
    config = ValidationConfig(
        provider="real",
        model="test-model",
        runs_per_case=1,
        real_validation_enabled=True,
        report_dir=tmp_path,
    )

    report = run_validation(config, [case], client=FailingValidationClient())

    assert report.failed_runs == 1
    assert report.api_failures == 1
    assert report.failure_cases[0]["case_id"] == "opening_01"
    assert "超时" in report.failure_cases[0]["reason"]
