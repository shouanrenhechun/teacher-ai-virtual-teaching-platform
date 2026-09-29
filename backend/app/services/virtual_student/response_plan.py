from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class StudentResponsePlan:
    """Immutable bridge between cognitive meaning and student wording.

    The plan contains semantic facts and expression constraints.  It does not
    contain a mutable engine and cannot update the student's cognitive state.
    """

    semantic_type: str
    topic: str
    task_type: str
    task_context: str
    response_goal: str
    misconception_status: str
    misconception_strength: float
    current_belief_stance: str
    content_facts: Mapping[str, object] = field(default_factory=dict)
    must_include: tuple[str, ...] = ()
    must_avoid: tuple[str, ...] = (
        "claim_full_mastery",
        "introduce_unlearned_knowledge",
        "contradict_current_belief",
        "erase_residual_misconception",
        "fabricate_transfer_success",
        "fabricate_explanation",
        "answer_outside_boundary",
        "reveal_internal_state_numbers",
        "mention_system_prompt",
        "mention_misconception_status",
    )
    style_constraints: Mapping[str, str] = field(default_factory=dict)
    response_shape: str = "clarify"
    turn_index: int = 0
    teacher_text: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "content_facts", MappingProxyType(dict(self.content_facts)))
        object.__setattr__(self, "style_constraints", MappingProxyType(dict(self.style_constraints)))
        object.__setattr__(self, "misconception_strength", max(0.0, min(1.0, float(self.misconception_strength))))
