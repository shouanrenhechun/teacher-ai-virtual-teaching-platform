from __future__ import annotations

from ...core.config import Settings, get_settings
from .base import LLMClient
from .mock import MockLLMClient
from .real import RealLLMClient


def build_llm_client(settings: Settings | None = None) -> LLMClient:
    settings = settings or get_settings()
    if settings.llm_provider == "mock":
        return MockLLMClient()
    if settings.llm_provider == "real":
        return RealLLMClient(settings)
    raise ValueError("不支持的 LLM_PROVIDER")
