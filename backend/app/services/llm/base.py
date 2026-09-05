from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class LLMContext:
    """Small, provider-neutral context passed by future teaching services."""

    student_name: str = "学生 A"
    student_grade: str = "初二"
    topic: str = "一次函数 k 与 b 的意义"
    system_prompt: str | None = None
    conversation_history: tuple[tuple[str, str], ...] = ()
    task_context: str = ""
    student_profile_id: str = "student_a"
    misconception_status: str = "active"
    misconception_semantic_type: str = "linear_kb"
    previous_student_evidence: Mapping[str, object] | None = None
    misconception_stable_correct_evidence_count: int = 0
    misconception_transfer_evidence: int = 0
    student_confidence: float = 0.5
    confidence_style: str = "自然表达，不刻意改变知识判断。"
    response_style: str = "回答自然、简短，符合课堂中的学生表达。"
    confirmation_seeking: str = "必要时根据教师提示确认自己的理解。"
    correction_style: str = "接受证据后逐步修正，不因教师一句话立即宣称完全掌握。"


class LLMError(RuntimeError):
    """Base error for user-facing LLM failures."""


class LLMConfigurationError(LLMError):
    """Raised when the selected provider is not configured correctly."""


class LLMServiceError(LLMError):
    """Raised when the selected provider cannot return a response."""


class LLMClient(ABC):
    provider: str

    @abstractmethod
    def respond(self, teacher_text: str, context: LLMContext | None = None) -> str:
        """Return the virtual student's response to one teacher message."""

    def analyze_behavior(
        self, teacher_text: str, context: LLMContext | None = None
    ) -> Any:
        """Return structured behavior data for the analyzer to validate."""
        raise LLMServiceError("当前 LLM 客户端不支持教学行为分析")

    def analyze_evaluation(
        self, evaluation_prompt: str, context: LLMContext | None = None
    ) -> Any:
        """Return qualitative evaluation data for the evaluation engine to validate."""
        raise LLMServiceError("当前 LLM 客户端不支持教学评价分析")
