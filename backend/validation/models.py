from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidationCase:
    case_id: str
    category: str
    mode: str
    title: str
    teacher_inputs: tuple[str, ...]
    expectations: dict[str, bool]
    misconception_type: str = "linear_kb"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValidationCase:
        inputs = tuple(str(item).strip() for item in data.get("teacher_inputs", []))
        if not inputs or any(not item for item in inputs):
            raise ValueError(f"验证案例 {data.get('id', '<unknown>')} 缺少教师输入")
        mode = str(data.get("mode", "single"))
        if mode not in {"single", "trajectory"}:
            raise ValueError(f"验证案例 {data.get('id', '<unknown>')} 的 mode 无效")
        return cls(
            case_id=str(data["id"]),
            category=str(data["category"]),
            mode=mode,
            title=str(data["title"]),
            teacher_inputs=inputs,
            expectations={
                str(key): bool(value)
                for key, value in dict(data.get("expectations", {})).items()
            },
            misconception_type=str(data.get("misconception_type", "linear_kb")),
        )


@dataclass(frozen=True)
class MetricResult:
    passed: bool
    applicable: bool
    reason: str
    evidence: tuple[str, ...] = ()
    level: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "applicable": self.applicable,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "level": self.level,
        }


@dataclass
class ValidationTurnResult:
    sequence: int
    teacher_input: str
    student_response: str
    state_before: dict[str, Any]
    state_after: dict[str, Any]
    behavior: str
    indicators: dict[str, bool] = field(default_factory=dict)
    student_response_evidence: dict[str, object] = field(default_factory=dict)
    misconception_status_before: str = "active"
    misconception_status_after: str = "active"
    correction_opportunity: dict[str, object] = field(default_factory=dict)
    prompt_misconception_mode: str | None = None
    prompt_misconception_status: str | None = None
    prompt_misconception_strength: float | None = None
    prompt_recent_history_count: int | None = None
    sanitized_system_prompt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "sequence": self.sequence,
            "teacher_input": self.teacher_input,
            "student_response": self.student_response,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "behavior": self.behavior,
            "indicators": self.indicators,
            "student_response_evidence": self.student_response_evidence,
            "misconception_status_before": self.misconception_status_before,
            "misconception_status_after": self.misconception_status_after,
            "correction_opportunity": self.correction_opportunity,
        }
        if self.prompt_misconception_mode is not None:
            payload.update(
                {
                    "prompt_misconception_mode": self.prompt_misconception_mode,
                    "prompt_misconception_status": self.prompt_misconception_status,
                    "prompt_misconception_strength": self.prompt_misconception_strength,
                    "prompt_recent_history_count": self.prompt_recent_history_count,
                    "sanitized_system_prompt": self.sanitized_system_prompt,
                }
            )
        return payload


@dataclass
class ValidationRunResult:
    case_id: str
    category: str
    mode: str
    run_index: int
    provider: str
    status: str = "passed"
    started_at: str = ""
    finished_at: str = ""
    successful_calls: int = 0
    error: str | None = None
    student_profile_id: str = "student_a"
    student_profile_name: str = "学生 A"
    turns: list[ValidationTurnResult] = field(default_factory=list)
    metrics: dict[str, MetricResult] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "mode": self.mode,
            "run_index": self.run_index,
            "provider": self.provider,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "successful_calls": self.successful_calls,
            "error": self.error,
            "student_profile_id": self.student_profile_id,
            "student_profile_name": self.student_profile_name,
            "turns": [turn.to_dict() for turn in self.turns],
            "metrics": {name: result.to_dict() for name, result in self.metrics.items()},
        }


@dataclass(frozen=True)
class ValidationReport:
    generated_at: str
    provider: str
    model: str
    runs_per_case: int
    real_validation_enabled: bool
    total_cases: int
    total_runs: int
    successful_runs: int
    partial_runs: int
    failed_runs: int
    total_calls: int
    successful_calls: int
    api_failures: int
    overall_metrics: dict[str, dict[str, Any]]
    category_metrics: dict[str, dict[str, Any]]
    failure_cases: tuple[dict[str, Any], ...]
    runs: tuple[dict[str, Any], ...]
    student_profile_id: str = "student_a"
    student_profile_name: str = "学生 A"

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "provider": self.provider,
            "model": self.model,
            "runs_per_case": self.runs_per_case,
            "real_validation_enabled": self.real_validation_enabled,
            "basic": {
                "total_cases": self.total_cases,
                "total_runs": self.total_runs,
                "successful_runs": self.successful_runs,
                "partial_runs": self.partial_runs,
                "failed_runs": self.failed_runs,
                "total_calls": self.total_calls,
                "successful_calls": self.successful_calls,
                "api_failures": self.api_failures,
            },
            "student_profile_id": self.student_profile_id,
            "student_profile_name": self.student_profile_name,
            "overall_metrics": self.overall_metrics,
            "category_metrics": self.category_metrics,
            "failure_cases": list(self.failure_cases),
            "runs": list(self.runs),
        }
