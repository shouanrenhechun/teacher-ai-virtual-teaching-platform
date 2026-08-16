"""Shared, small rules for evidence-backed misconception transitions."""

from __future__ import annotations

from collections.abc import Mapping


def is_strong_correct_evidence(evidence: Mapping[str, object]) -> bool:
    """Return whether one response is a stable-correction candidate."""
    return (
        bool(evidence.get("states_correct_conclusion"))
        and bool(evidence.get("explains_reason_correctly"))
        and bool(evidence.get("knowledge_precision") == "correct")
        and not bool(evidence.get("shows_residual_misconception"))
        and not bool(evidence.get("conceptual_uncertainty"))
        and not bool(evidence.get("parrots_teacher"))
    )


def is_evidence_insufficient(evidence: Mapping[str, object]) -> bool:
    """No error was expressed, but the response is not strong mastery evidence."""
    return (
        not bool(evidence.get("shows_residual_misconception"))
        and not is_strong_correct_evidence(evidence)
    )
