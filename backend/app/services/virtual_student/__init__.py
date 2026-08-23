"""Rule-constrained virtual student state engine."""

from .behavior import TeachingBehavior, detect_teacher_behavior
from .classroom_intent import ClassroomAct, ClassroomDialogueIntent, analyze_classroom_dialogue
from .engine import (
    DynamicState,
    EngineSnapshot,
    KnowledgeStateValue,
    MisconceptionState,
    StudentProfile,
    VirtualStudentEngine,
    stable_profile_id,
)
from .prompt_builder import PromptBuilder
from .semantic import (
    BINOMIAL_SQUARE,
    LINEAR_KB,
    BinomialSquareSemanticEvaluator,
    DomainEvidence,
    MisconceptionSemanticEvaluator,
    get_semantic_evaluator,
)
from .evidence import (
    StudentResponseEvidence,
    StudentResponseEvidenceAnalyzer,
    correction_opportunity,
)
from .state_rules import is_evidence_insufficient, is_strong_correct_evidence

__all__ = [
    "DynamicState",
    "ClassroomAct",
    "ClassroomDialogueIntent",
    "EngineSnapshot",
    "KnowledgeStateValue",
    "MisconceptionState",
    "PromptBuilder",
    "LINEAR_KB",
    "BINOMIAL_SQUARE",
    "DomainEvidence",
    "MisconceptionSemanticEvaluator",
    "BinomialSquareSemanticEvaluator",
    "get_semantic_evaluator",
    "StudentProfile",
    "TeachingBehavior",
    "VirtualStudentEngine",
    "stable_profile_id",
    "detect_teacher_behavior",
    "analyze_classroom_dialogue",
    "StudentResponseEvidence",
    "StudentResponseEvidenceAnalyzer",
    "correction_opportunity",
    "is_evidence_insufficient",
    "is_strong_correct_evidence",
]
