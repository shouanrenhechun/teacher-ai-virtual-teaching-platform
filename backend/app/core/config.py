from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv


LLMProvider = Literal["mock", "real"]
PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    llm_provider: LLMProvider
    llm_api_key: str
    llm_api_url: str
    llm_model: str
    llm_timeout_seconds: float


def get_settings() -> Settings:
    """Load backend-only configuration for the current request."""
    load_dotenv(PROJECT_ROOT / ".env")

    provider = os.getenv("LLM_PROVIDER", "mock").strip().lower()
    if provider not in {"mock", "real"}:
        raise ValueError("LLM_PROVIDER 只能是 mock 或 real")

    try:
        timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "15"))
    except ValueError as exc:
        raise ValueError("LLM_TIMEOUT_SECONDS 必须是数字") from exc
    if timeout <= 0 or timeout > 120:
        raise ValueError("LLM_TIMEOUT_SECONDS 必须在 0 到 120 秒之间")

    return Settings(
        llm_provider=provider,  # type: ignore[arg-type]
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_api_url=os.getenv(
            "LLM_API_URL", "https://api.openai.com/v1/chat/completions"
        ).strip(),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini").strip(),
        llm_timeout_seconds=timeout,
    )
