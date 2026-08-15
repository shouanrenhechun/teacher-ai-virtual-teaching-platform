from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMContext:
    """Small, provider-neutral context passed by future teaching services."""

    student_name: str = "学生 A"
    student_grade: str = "初二"
    topic: str = "一次函数 k 与 b 的意义"
    system_prompt: str | None = None


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
