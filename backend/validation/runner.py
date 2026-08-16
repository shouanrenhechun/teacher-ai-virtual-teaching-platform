from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from app.core.config import get_settings
from app.services.llm import LLMClient, LLMContext, build_llm_client
from app.services.virtual_student import (
    VirtualStudentEngine,
    detect_teacher_behavior,
)
from app.services.virtual_student.prompt_builder import (
    misconception_prompt_mode,
    prompt_recent_history_count,
)

from .case_loader import load_student_profile, load_validation_cases
from .metrics import evaluate_run, extract_turn_indicators, summarize_metrics
from .models import (
    ValidationCase,
    ValidationReport,
    ValidationRunResult,
    ValidationTurnResult,
)


class RealValidationDisabledError(RuntimeError):
    """Raised before any real provider call when the safety switch is absent."""


@dataclass(frozen=True)
class ValidationConfig:
    provider: str
    model: str
    runs_per_case: int = 3
    real_validation_enabled: bool = False
    prompt_debug_enabled: bool = False
    report_dir: Path = Path(__file__).resolve().parent / "reports"
    student_profile_id: str = "student_a"

    @classmethod
    def from_environment(cls) -> ValidationConfig:
        settings = get_settings()
        try:
            runs = int(os.getenv("RUNS_PER_CASE", "3"))
        except ValueError as exc:
            raise ValueError("RUNS_PER_CASE 必须是正整数") from exc
        if runs <= 0 or runs > 20:
            raise ValueError("RUNS_PER_CASE 必须在 1 到 20 之间")
        return cls(
            provider=settings.llm_provider,
            model=settings.llm_model,
            runs_per_case=runs,
            real_validation_enabled=_is_true(
                os.getenv("RUN_REAL_LLM_VALIDATION", "false")
            ),
            prompt_debug_enabled=_is_true(
                os.getenv("VALIDATION_PROMPT_DEBUG", "false")
            ),
            report_dir=Path(
                os.getenv(
                    "VALIDATION_REPORT_DIR",
                    str(Path(__file__).resolve().parent / "reports"),
                )
            ),
            student_profile_id=os.getenv("VALIDATION_STUDENT_PROFILE", "student_a").strip()
            or "student_a",
        )


def run_validation(
    config: ValidationConfig,
    cases: Sequence[ValidationCase],
    *,
    client: LLMClient | None = None,
) -> ValidationReport:
    if config.provider == "real" and not config.real_validation_enabled:
        raise RealValidationDisabledError(
            "真实 LLM 验证未启用。请同时设置 LLM_PROVIDER=real 和 "
            "RUN_REAL_LLM_VALIDATION=true。"
        )

    if client is None:
        settings = get_settings()
        client = build_llm_client(settings)

    report_profile = load_student_profile(
        profile_id=config.student_profile_id,
        misconception_type="linear_kb",
    )

    all_runs: list[ValidationRunResult] = []
    for case in cases:
        for run_index in range(1, config.runs_per_case + 1):
            all_runs.append(_run_case(case, run_index, config, client))

    run_dicts = [run.to_dict() for run in all_runs]
    categories: dict[str, list[dict[str, Any]]] = {}
    for run in run_dicts:
        categories.setdefault(run["category"], []).append(run)

    failed_runs = [run for run in all_runs if run.status == "failed"]
    partial_runs = [run for run in all_runs if run.status == "partial"]
    failure_cases = tuple(
        failure
        for run in all_runs
        if (failure := _failure_case(run)) is not None
    )
    total_calls = sum(len(case.teacher_inputs) for case in cases) * config.runs_per_case
    successful_calls = sum(run.successful_calls for run in all_runs)
    api_failures = sum(
        1 for run in all_runs if run.status == "failed" and run.error is not None
    )

    return ValidationReport(
        generated_at=_now(),
        provider=config.provider,
        model=config.model,
        runs_per_case=config.runs_per_case,
        real_validation_enabled=config.real_validation_enabled,
        total_cases=len(cases),
        total_runs=len(all_runs),
        successful_runs=sum(1 for run in all_runs if run.status == "passed"),
        partial_runs=len(partial_runs),
        failed_runs=len(failed_runs),
        total_calls=total_calls,
        successful_calls=successful_calls,
        api_failures=api_failures,
        overall_metrics=summarize_metrics(run_dicts),
        category_metrics={
            category: summarize_metrics(category_runs)
            for category, category_runs in sorted(categories.items())
        },
        failure_cases=failure_cases,
        runs=tuple(run_dicts),
        student_profile_id=config.student_profile_id,
        student_profile_name=report_profile.name,
    )


def write_report(report: ValidationReport, report_dir: Path) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = report_dir / f"validation-report-{timestamp}.json"
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def estimate_calls(cases: Sequence[ValidationCase], runs_per_case: int) -> int:
    return sum(len(case.teacher_inputs) for case in cases) * runs_per_case


def _run_case(
    case: ValidationCase,
    run_index: int,
    config: ValidationConfig,
    client: LLMClient,
) -> ValidationRunResult:
    result = ValidationRunResult(
        case_id=case.case_id,
        category=case.category,
        mode=case.mode,
        run_index=run_index,
        provider=config.provider,
        student_profile_id=config.student_profile_id,
        student_profile_name="",
        started_at=_now(),
    )
    profile = load_student_profile(
        profile_id=config.student_profile_id,
        misconception_type=case.misconception_type,
    )
    result.student_profile_name = profile.name
    engine = VirtualStudentEngine(
        profile
    )
    conversation_history: list[tuple[str, str]] = []
    context_base = LLMContext(
        student_name=engine.profile.name,
        student_grade=engine.profile.grade,
        topic=(
            "完全平方公式"
            if case.misconception_type == "binomial_square"
            else "一次函数 k 与 b 的意义"
        ),
        student_profile_id=engine.profile.profile_id,
    )

    try:
        for sequence, teacher_input in enumerate(case.teacher_inputs, start=1):
            before = _snapshot_dict(engine.snapshot())
            behavior = detect_teacher_behavior(teacher_input)
            opportunity = engine.get_correction_opportunity(teacher_input)
            previous_teacher_text = next(
                (content for speaker, content in reversed(conversation_history) if speaker == "teacher"),
                "",
            )
            engine.update_from_teacher_text(teacher_input)
            prompt = engine.build_prompt(teacher_input, conversation_history)
            prompt_snapshot = engine.snapshot()
            prompt_misconception = next(
                iter(prompt_snapshot.misconceptions), None
            )
            response = client.respond(
                teacher_input,
                replace(context_base, system_prompt=prompt),
            )
            if not response or not response.strip():
                raise RuntimeError("LLM 返回了空学生回答")
            result.successful_calls += 1
            evidence = engine.apply_student_response_evidence(
                response.strip(),
                teacher_input,
                opportunity,
                previous_teacher_text=previous_teacher_text,
            )
            state_after = _snapshot_dict(engine.snapshot())
            status_before = before["misconceptions"][0].get("status", "active")
            status_after = state_after["misconceptions"][0].get("status", "active")
            result.turns.append(
                ValidationTurnResult(
                    sequence=sequence,
                    teacher_input=teacher_input,
                    student_response=response.strip(),
                    state_before=before,
                    state_after=state_after,
                    behavior=behavior.value,
                    indicators=extract_turn_indicators(
                        response,
                        state_after,
                        boundary_expected=case.expectations.get("boundary_refusal", False),
                    ),
                    student_response_evidence=evidence.to_dict(),
                    misconception_status_before=status_before,
                    misconception_status_after=status_after,
                    correction_opportunity=opportunity,
                    **(
                        {
                            "prompt_misconception_mode": misconception_prompt_mode(
                                prompt_misconception.status,
                                prompt_misconception.corrected,
                            )
                            if prompt_misconception
                            else "corrected_history",
                            "prompt_misconception_status": (
                                prompt_misconception.status
                                if prompt_misconception
                                else "corrected"
                            ),
                            "prompt_misconception_strength": (
                                prompt_misconception.strength
                                if prompt_misconception
                                else 0.0
                            ),
                            "prompt_recent_history_count": prompt_recent_history_count(
                                conversation_history,
                                teacher_input,
                            ),
                            "sanitized_system_prompt": _sanitize_prompt(prompt),
                        }
                        if config.prompt_debug_enabled
                        else {}
                    ),
                )
            )
            conversation_history.extend(
                [("teacher", teacher_input), ("student", response.strip())]
            )
        result.metrics = evaluate_run(case, result.turns)
        has_hard_failure = any(
            metric.applicable and not metric.passed and metric.level != "partial"
            for metric in result.metrics.values()
        )
        has_partial = any(
            metric.applicable and metric.level == "partial"
            for metric in result.metrics.values()
        )
        if has_hard_failure:
            result.status = "failed"
        elif has_partial:
            result.status = "partial"
    except Exception as exc:  # A failed case is data, not a suite-wide crash.
        result.status = "failed"
        result.error = _safe_error(exc)
    finally:
        result.finished_at = _now()
    return result


def _failure_case(run: ValidationRunResult) -> dict[str, Any] | None:
    failed_metrics = [
        name for name, metric in run.metrics.items() if metric.applicable and not metric.passed
    ]
    if run.status == "passed" and not failed_metrics:
        return None
    reasons = [
        metric.reason
        for metric in run.metrics.values()
        if metric.applicable and not metric.passed
    ]
    if run.error:
        reasons.insert(0, run.error)
    first_turn = run.turns[0] if run.turns else None
    return {
        "case_id": run.case_id,
        "category": run.category,
        "run_index": run.run_index,
        "teacher_input": first_turn.teacher_input if first_turn else None,
        "student_state_before": first_turn.state_before if first_turn else None,
        "student_response": first_turn.student_response if first_turn else None,
        "student_state_after": first_turn.state_after if first_turn else None,
        "failed_metrics": failed_metrics,
        "reason": "；".join(reasons) or "验证运行失败",
    }


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


def _safe_error(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    for secret_marker in ("sk-", "gho_", "Bearer "):
        if secret_marker.lower() in message.lower():
            return f"{type(exc).__name__}（敏感信息已隐藏）"
    return message[:300] or type(exc).__name__


def _sanitize_prompt(prompt: str) -> str:
    """Remove common token formats before a prompt is written to a report."""
    sanitized = prompt
    sanitized = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", sanitized)
    sanitized = re.sub(r"gho_[A-Za-z0-9_]+", "[REDACTED_GITHUB_TOKEN]", sanitized)
    sanitized = re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED_API_KEY]", sanitized)
    return sanitized


def _is_true(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运行虚拟学生一致性验证")
    parser.add_argument("--runs", type=int, help="覆盖 RUNS_PER_CASE")
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="只运行指定案例，可重复传入",
    )
    parser.add_argument("--report-dir", type=Path, help="覆盖报告输出目录")
    parser.add_argument(
        "--student-profile",
        dest="student_profile_id",
        help="选择验证学生画像，默认读取 VALIDATION_STUDENT_PROFILE",
    )
    args = parser.parse_args(argv)

    config = ValidationConfig.from_environment()
    if args.runs is not None:
        if args.runs <= 0 or args.runs > 20:
            parser.error("--runs 必须在 1 到 20 之间")
        config = replace(config, runs_per_case=args.runs)
    if args.report_dir is not None:
        config = replace(config, report_dir=args.report_dir)
    if args.student_profile_id is not None:
        config = replace(config, student_profile_id=args.student_profile_id)

    cases = load_validation_cases(case_ids=set(args.case_ids or []))
    if config.provider == "real":
        if not config.real_validation_enabled:
            print(
                "Real LLM validation is disabled. Set "
                "RUN_REAL_LLM_VALIDATION=true to enable it."
            )
            return 2
        print("Real LLM validation enabled")
        print(f"Provider: {config.provider}")
        print(f"Model: {config.model}")
        print(f"Student profile: {config.student_profile_id}")
        print(f"Runs per case: {config.runs_per_case}")
        print(f"Estimated calls: {estimate_calls(cases, config.runs_per_case)}")
    else:
        print("Mock validation mode enabled")

    report = run_validation(config, cases)
    path = write_report(report, config.report_dir)
    print(f"Report: {path}")
    print(json.dumps(report.to_dict()["basic"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
