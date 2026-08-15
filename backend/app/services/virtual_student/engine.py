from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Any

from .behavior import TeachingBehavior, detect_teacher_behavior
from .evidence import StudentResponseEvidence, StudentResponseEvidenceAnalyzer, correction_opportunity


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


@dataclass
class KnowledgeStateValue:
    knowledge_point: str
    mastery: float

    def __post_init__(self) -> None:
        self.mastery = _clamp(self.mastery)


@dataclass
class MisconceptionState:
    name: str
    concept: str
    description: str
    strength: float
    correction_condition: str
    triggered: bool = False
    correction_started: bool = False
    corrected: bool = False
    status: str = "active"
    clean_evidence_streak: int = 0
    transfer_evidence: int = 0

    def __post_init__(self) -> None:
        self.strength = _clamp(self.strength)
        if self.status not in {"active", "weakening", "provisional", "corrected"}:
            self.status = "active"
        if self.corrected:
            self.status = "corrected"


@dataclass(frozen=True)
class DynamicState:
    understanding: float
    confusion: float
    engagement: float
    confidence: float
    surface_recall: float = 0.0

    def __post_init__(self) -> None:
        for field_name in ("understanding", "confusion", "engagement", "confidence", "surface_recall"):
            object.__setattr__(self, field_name, _clamp(getattr(self, field_name)))


@dataclass
class StudentProfile:
    name: str
    grade: str
    base_level: float
    personality_description: str
    initiative: float
    confidence: float
    knowledge_states: list[KnowledgeStateValue] = field(default_factory=list)
    misconceptions: list[MisconceptionState] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.base_level = _clamp(self.base_level)
        self.initiative = _clamp(self.initiative)
        self.confidence = _clamp(self.confidence)

    @classmethod
    def from_record(cls, record: Any) -> StudentProfile:
        """Adapt the existing ORM record without coupling the engine to SQLAlchemy."""
        return cls(
            name=record.name,
            grade=record.grade,
            base_level=record.base_level,
            personality_description=record.personality_description,
            initiative=record.initiative,
            confidence=record.confidence,
            knowledge_states=[
                KnowledgeStateValue(item.knowledge_point, item.mastery)
                for item in record.knowledge_states
            ],
            misconceptions=[
                MisconceptionState(
                    name=item.name,
                    concept=item.concept,
                    description=item.description,
                    strength=item.strength,
                    correction_condition=item.correction_condition,
                )
                for item in record.misconceptions
            ],
        )


@dataclass(frozen=True)
class EngineSnapshot:
    knowledge_states: tuple[KnowledgeStateValue, ...]
    misconceptions: tuple[MisconceptionState, ...]
    classroom_state: DynamicState


class VirtualStudentEngine:
    """A transparent, finite-state teaching simulation engine."""

    def __init__(self, profile: StudentProfile) -> None:
        self.profile = deepcopy(profile)
        self._knowledge = {
            item.knowledge_point: deepcopy(item) for item in profile.knowledge_states
        }
        self._misconceptions = deepcopy(profile.misconceptions)
        self._classroom_state = DynamicState(
            understanding=profile.base_level,
            confusion=_clamp(0.45 - profile.base_level * 0.2),
            engagement=profile.initiative,
            confidence=profile.confidence,
        )

    @property
    def classroom_state(self) -> DynamicState:
        return self._classroom_state

    def snapshot(self) -> EngineSnapshot:
        return EngineSnapshot(
            knowledge_states=tuple(deepcopy(list(self._knowledge.values()))),
            misconceptions=tuple(deepcopy(self._misconceptions)),
            classroom_state=self._classroom_state,
        )

    def knowledge_boundary(self) -> dict[str, list[str]]:
        mastered = []
        partial = []
        not_ready = []
        for item in self._knowledge.values():
            if item.mastery >= 0.7:
                mastered.append(item.knowledge_point)
            elif item.mastery >= 0.4:
                partial.append(item.knowledge_point)
            else:
                not_ready.append(item.knowledge_point)
        return {"mastered": mastered, "partial": partial, "not_ready": not_ready}

    def mark_misconception_triggered(self, name: str) -> bool:
        misconception = self._find_misconception(name)
        if misconception is None or misconception.corrected:
            return False
        misconception.triggered = True
        return True

    def apply_behavior(
        self,
        behavior: TeachingBehavior | str,
        *,
        target_misconception: str | None = None,
    ) -> EngineSnapshot:
        behavior = TeachingBehavior(behavior)
        state = self._classroom_state

        if behavior is TeachingBehavior.EFFECTIVE_EXAMPLE:
            self._classroom_state = replace(
                state,
                understanding=state.understanding + 0.05,
                confusion=state.confusion - 0.03,
                engagement=state.engagement + 0.03,
                confidence=state.confidence + 0.02,
                surface_recall=state.surface_recall + 0.02,
            )
            self._increase_knowledge_if_related(0.03)
        elif behavior is TeachingBehavior.EFFECTIVE_QUESTION:
            self._classroom_state = replace(
                state,
                engagement=state.engagement + 0.08,
                confidence=state.confidence + 0.01,
            )
        elif behavior is TeachingBehavior.DIRECT_ANSWER:
            self._classroom_state = replace(
                state,
                engagement=state.engagement - 0.02,
                surface_recall=state.surface_recall + 0.15,
            )
        elif behavior is TeachingBehavior.INCORRECT_EXPLANATION:
            self._classroom_state = replace(
                state,
                understanding=state.understanding - 0.05,
                confusion=state.confusion + 0.12,
                confidence=state.confidence - 0.05,
            )
        elif behavior is TeachingBehavior.TARGETED_CORRECTION:
            self._apply_targeted_correction(target_misconception)
        elif behavior is TeachingBehavior.NEUTRAL:
            pass

        return self.snapshot()

    def update_from_teacher_text(self, teacher_text: str) -> EngineSnapshot:
        """Apply the small rule set to a teacher utterance."""
        behavior = detect_teacher_behavior(teacher_text)
        target = self._infer_target_misconception(teacher_text, behavior)
        return self.apply_behavior(behavior, target_misconception=target)

    def get_correction_opportunity(self, teacher_text: str) -> dict[str, object]:
        behavior = detect_teacher_behavior(teacher_text)
        return correction_opportunity(behavior.value, teacher_text)

    def apply_student_response_evidence(
        self,
        response: str,
        teacher_text: str,
        opportunity: dict[str, object] | None = None,
        *,
        previous_teacher_text: str = "",
    ) -> StudentResponseEvidence:
        """Update misconception state only after inspecting the student's answer."""
        evidence = StudentResponseEvidenceAnalyzer().analyze(
            response,
            teacher_text=teacher_text,
            previous_teacher_text=previous_teacher_text,
        )
        misconception = self._find_misconception(None)
        if misconception is None:
            return evidence

        opportunity_strength = float(
            (opportunity or self.get_correction_opportunity(teacher_text)).get(
                "opportunity_strength", 0.0
            )
        )
        has_opportunity = opportunity_strength > 0
        misconception.triggered = evidence.shows_residual_misconception
        misconception.correction_started = misconception.correction_started or has_opportunity

        if evidence.shows_residual_misconception:
            misconception.corrected = False
            misconception.clean_evidence_streak = 0
            if evidence.states_correct_conclusion and evidence.explains_reason_correctly:
                reduction = 0.12 * max(opportunity_strength, 0.5)
                misconception.status = "provisional"
            elif evidence.states_correct_conclusion:
                reduction = 0.08 * max(opportunity_strength, 0.5)
                misconception.status = "provisional"
            elif evidence.shows_uncertainty and has_opportunity:
                reduction = 0.04 * max(opportunity_strength, 0.5)
                misconception.status = "weakening"
            else:
                reduction = -0.03 if not has_opportunity else 0.0
                misconception.status = "active"
            misconception.strength = _clamp(misconception.strength - reduction)
        else:
            if evidence.states_correct_conclusion:
                misconception.clean_evidence_streak += 1
            if evidence.transfer_success:
                misconception.transfer_evidence += 1
            if evidence.states_correct_conclusion and evidence.explains_reason_correctly:
                reduction = 0.15 if evidence.transfer_success else 0.1
                misconception.strength = _clamp(misconception.strength - reduction)
                misconception.status = "provisional"
            elif evidence.states_correct_conclusion:
                misconception.strength = _clamp(misconception.strength - 0.05)
                misconception.status = "provisional"
            elif has_opportunity:
                misconception.status = "weakening"

            if (
                (evidence.transfer_success or misconception.transfer_evidence > 0)
                and evidence.explains_reason_correctly
                and not evidence.shows_uncertainty
                and not evidence.parrots_teacher
                and misconception.clean_evidence_streak >= 2
            ):
                misconception.strength = min(misconception.strength, 0.05)
                misconception.status = "corrected"
                misconception.corrected = True
                misconception.triggered = False

        return evidence

    def build_prompt(
        self,
        teacher_text: str,
        conversation_history: list[tuple[str, str]] | None = None,
    ) -> str:
        from .prompt_builder import PromptBuilder

        return PromptBuilder().build(self, teacher_text, conversation_history)

    def _apply_targeted_correction(self, target_misconception: str | None) -> None:
        self._classroom_state = replace(
            self._classroom_state,
            understanding=self._classroom_state.understanding + 0.04,
            confusion=self._classroom_state.confusion - 0.1,
            engagement=self._classroom_state.engagement + 0.05,
            confidence=self._classroom_state.confidence + 0.03,
        )

    def _increase_knowledge_if_related(self, amount: float) -> None:
        for item in self._knowledge.values():
            if any(keyword in item.knowledge_point.lower() for keyword in ("k", "b", "图像")):
                item.mastery = _clamp(item.mastery + amount)

    def _find_misconception(self, name: str | None) -> MisconceptionState | None:
        if name:
            for item in self._misconceptions:
                if item.name == name:
                    return item
            return None
        return next((item for item in self._misconceptions if not item.corrected), None)

    def _infer_target_misconception(
        self,
        teacher_text: str,
        behavior: TeachingBehavior,
    ) -> str | None:
        if behavior not in {
            TeachingBehavior.TARGETED_CORRECTION,
            TeachingBehavior.INCORRECT_EXPLANATION,
            TeachingBehavior.EFFECTIVE_EXAMPLE,
            TeachingBehavior.EFFECTIVE_QUESTION,
        }:
            return None
        text = teacher_text.lower()
        if "b" in text:
            for item in self._misconceptions:
                if "b" in item.name.lower() or "b" in item.concept.lower():
                    return item.name
        return next((item.name for item in self._misconceptions if not item.corrected), None)
