"""Provider-independent LLM abstraction layer."""

from .base import LLMClient, LLMContext


def build_llm_client(settings=None):
    """Load the provider factory lazily to keep renderer imports acyclic."""
    from .factory import build_llm_client as _build_llm_client

    return _build_llm_client(settings)

__all__ = ["LLMClient", "LLMContext", "build_llm_client"]
