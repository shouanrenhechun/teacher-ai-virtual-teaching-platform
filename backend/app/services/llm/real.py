from __future__ import annotations

import json
from typing import Any

import httpx

from ...core.config import Settings
from .base import LLMClient, LLMConfigurationError, LLMContext, LLMServiceError


class RealLLMClient(LLMClient):
    """Generic OpenAI-compatible HTTP client kept behind the LLMClient interface."""

    provider = "real"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def respond(self, teacher_text: str, context: LLMContext | None = None) -> str:
        if not teacher_text.strip():
            raise LLMServiceError("教师输入不能为空")

        context = context or LLMContext()
        return self._chat(
            [
                {
                    "role": "system",
                    "content": context.system_prompt
                    or (
                        "你是教学实训中的虚拟初中生。请用简短中文回答教师，逐步暴露理解，"
                        f"当前主题是{context.topic}，学生是{context.student_name}。"
                    ),
                },
                {"role": "user", "content": teacher_text.strip()},
            ],
            temperature=0.7,
        )

    def analyze_behavior(
        self, teacher_text: str, context: LLMContext | None = None
    ) -> dict[str, Any]:
        if not teacher_text.strip():
            raise LLMServiceError("教师输入不能为空")

        context = context or LLMContext()
        content = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是教学行为结构化分析器。只输出一个 JSON 对象，不要 Markdown 或解释。"
                        "字段必须是 action_type、concept、knowledge_accuracy、clarity、"
                        "checked_understanding、gave_answer_directly。"
                        "action_type 只能是 explanation、question、guided_question、example、"
                        "feedback、correction、understanding_check、direct_answer。"
                        f"当前主题是{context.topic}。"
                    ),
                },
                {"role": "user", "content": teacher_text.strip()},
            ],
            temperature=0,
        )
        try:
            parsed = json.loads(self._strip_code_fence(content))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise LLMServiceError("教学行为模型返回的 JSON 无法解析") from exc
        if not isinstance(parsed, dict):
            raise LLMServiceError("教学行为模型返回的结构不是 JSON 对象")
        return parsed

    def analyze_evaluation(
        self, evaluation_prompt: str, context: LLMContext | None = None
    ) -> dict[str, Any]:
        context = context or LLMContext()
        content = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是教学训练辅助评价分析器。只输出一个 JSON 对象，不要 Markdown 或解释。"
                        "字段必须是 strengths、problems、suggestions、evidence_rounds。"
                        "前三项必须是基于记录的具体中文字符串数组，evidence_rounds 必须是引用记录轮次的整数数组。"
                        f"当前主题是{context.topic}。评分由程序计算，你不能修改分数。"
                    ),
                },
                {"role": "user", "content": evaluation_prompt},
            ],
            temperature=0,
        )
        try:
            parsed = json.loads(self._strip_code_fence(content))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise LLMServiceError("教学评价模型返回的 JSON 无法解析") from exc
        if not isinstance(parsed, dict):
            raise LLMServiceError("教学评价模型返回的结构不是 JSON 对象")
        return parsed

    def _chat(self, messages: list[dict[str, str]], *, temperature: float) -> str:
        if not self.settings.llm_api_key:
            raise LLMConfigurationError("real 模式未配置 LLM_API_KEY")
        if not self.settings.llm_api_url:
            raise LLMConfigurationError("real 模式未配置 LLM_API_URL")

        payload = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
                response = client.post(self.settings.llm_api_url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMServiceError("模型服务响应超时，请稍后重试") from exc
        except httpx.HTTPError as exc:
            raise LLMServiceError("模型服务暂时不可用，请稍后重试") from exc

        if response.is_error:
            raise LLMServiceError(f"模型服务返回错误（HTTP {response.status_code}）")

        try:
            data: dict[str, Any] = response.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMServiceError("模型服务返回了无法识别的结果") from exc

        if isinstance(content, list):
            content = "".join(
                item.get("text", "") for item in content if isinstance(item, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise LLMServiceError("模型服务没有返回有效内容")
        return content.strip()

    @staticmethod
    def _strip_code_fence(content: str) -> str:
        stripped = content.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            lines = stripped.splitlines()
            return "\n".join(lines[1:-1]).strip()
        return stripped
