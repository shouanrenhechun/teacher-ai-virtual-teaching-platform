"""Rule-constrained virtual student state engine."""

from .behavior import TeachingBehavior, detect_teacher_behavior
from .engine import (
    DynamicState,
    EngineSnapshot,
    KnowledgeStateValue,
    MisconceptionState,
    StudentProfile,
    VirtualStudentEngine,
)
from .prompt_builder import PromptBuilder
from .evidence import (
    StudentResponseEvidence,
    StudentResponseEvidenceAnalyzer,
    correction_opportunity,
)
from .state_rules import is_evidence_insufficient, is_strong_correct_evidence

__all__ = [
    "DynamicState",
    "EngineSnapshot",
    "KnowledgeStateValue",
    "MisconceptionState",
    "PromptBuilder",
    "StudentProfile",
    "TeachingBehavior",
    "VirtualStudentEngine",
    "detect_teacher_behavior",
    "StudentResponseEvidence",
    "StudentResponseEvidenceAnalyzer",
    "correction_opportunity",
    "is_evidence_insufficient",
    "is_strong_correct_evidence",
]
