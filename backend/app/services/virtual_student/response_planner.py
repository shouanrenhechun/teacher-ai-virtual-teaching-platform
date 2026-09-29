from __future__ import annotations

import re

from ..llm.base import LLMContext
from .classroom_intent import ClassroomAct, ClassroomDialogueIntent, analyze_classroom_dialogue
from .dialogue_intent import LinearDialogueIntent, analyze_linear_dialogue_intent
from .linear_math import equations, rate_model, number, display
from .propositions import assess_claims
from .response_plan import StudentResponsePlan
from .task_context import active_task


class StudentResponsePlanner:
    """Translate current classroom meaning into a language-independent plan."""

    def build(self, teacher_text: str, context: LLMContext | None = None) -> StudentResponsePlan:
        context = context or LLMContext()
        text = re.split(r'口误[，,:：]?|更正为[：:]?|改成[：:]?\s*(?=y=|\()', teacher_text.strip())[-1]
        if context.misconception_semantic_type == "binomial_square" or any(word in context.topic for word in ("完全平方", "平方公式")):
            from .binomial_plan import build_binomial_plan
            return build_binomial_plan(text, context)
        classroom = analyze_classroom_dialogue(text, conversation_history=context.conversation_history)
        intent = analyze_linear_dialogue_intent(
            text,
            classroom_intent=classroom,
            conversation_history=context.conversation_history,
        )
        task = active_task(context.conversation_history, text) or context.task_context
        intent_text = text
        if intent.contextual_follow_up or (
            not classroom.has_subject_content
            and classroom.has(ClassroomAct.QUESTION)
        ) or (
            not equations(text)
            and any(marker in text for marker in ("代进去", "发现了什么", "观察到什么"))
            and bool(equations(task))
        ):
            previous_teacher = task or self._previous_teacher_text(context)
            if previous_teacher and not equations(text):
                intent_text = f"{previous_teacher} {text}"
                intent = analyze_linear_dialogue_intent(intent_text, conversation_history=context.conversation_history)
        task_equations = equations(intent_text) or equations(task)
        facts: dict[str, object] = {}
        facts['classroom_act'] = classroom.primary_act.value
        facts["fee_context"] = bool(rate_model(task) or rate_model(text))
        if task_equations:
            slopes = tuple(item[0] for item in task_equations)
            intercepts = tuple(item[1] for item in task_equations)
            facts.update(
                equations=task_equations,
                slopes=slopes,
                intercepts=intercepts,
                same_slope=len(set(slopes)) == 1,
                same_steepness=len({abs(number(value)) for value in slopes}) == 1,
            )
        model = rate_model(text)
        if model:
            facts.update(rate=model[0], base=model[1])
        x_matches = list(re.finditer(r"x=([+-]?(?:\d+/\d+|\d+(?:\.\d+)?))", intent_text.replace(" ", "")))
        x_match = x_matches[-1] if x_matches else None
        if x_match:
            x_value = number(x_match.group(1))
            facts["x"] = display(x_value)
            facts["values"] = tuple(
                display(number(slope) * x_value + number(intercept))
                for slope, intercept in task_equations
            )
        elif "横坐标" in intent.normalized or "纵轴" in intent.normalized or "y轴" in intent.normalized:
            facts["x"] = "0"
            facts["values"] = tuple(intercept for _, intercept in task_equations)

        shape, task_type, goal, includes = self._classify(
            text,
            classroom,
            intent,
            task_equations,
            model,
            context,
            allow_equation_comparison=bool(equations(text)) or intent_text != text,
        )
        return StudentResponsePlan(
            teacher_text=text,
            semantic_type=context.misconception_semantic_type,
            topic=context.topic,
            task_type=task_type,
            task_context=task,
            response_goal=goal,
            misconception_status=context.misconception_status,
            misconception_strength=context.misconception_strength,
            current_belief_stance=self._stance(context),
            content_facts=facts,
            must_include=includes,
            style_constraints={
                "confidence_style": context.confidence_style,
                "response_style": context.response_style,
                "confirmation_seeking": context.confirmation_seeking,
                "verbosity": context.verbosity if hasattr(context, "verbosity") else "一到三句话",
                "correction_style": context.correction_style,
                "style_examples": "\n".join(context.style_examples),
                "previous_response": next(
                    (
                        content.strip()
                        for speaker, content in reversed(context.conversation_history)
                        if speaker == "student" and content.strip()
                    ),
                    "",
                ),
                "repeat_teacher": "true"
                if any(
                    speaker == "teacher" and content.strip() == text
                    for speaker, content in context.conversation_history
                )
                else "false",
            },
            response_shape=shape,
            turn_index=context.turn_index or len(context.conversation_history) // 2,
        )

    @staticmethod
    def _previous_teacher_text(context: LLMContext) -> str:
        return next(
            (
                content
                for speaker, content in reversed(context.conversation_history)
                if speaker == "teacher" and content.strip()
            ),
            "",
        )

    @staticmethod
    def _stance(context: LLMContext) -> str:
        return {
            "active": "holds_misconception",
            "weakening": "conflicted",
            "provisional": "mostly_correct_but_unstable",
            "corrected": "stable_correct",
        }.get(context.misconception_status, "unknown")

    @classmethod
    def _classify(
        cls,
        text: str,
        classroom: ClassroomDialogueIntent,
        intent: LinearDialogueIntent,
        task_equations: tuple[tuple[str, str], ...],
        model: tuple[str, str] | None,
        context: LLMContext,
        *,
        allow_equation_comparison: bool,
    ) -> tuple[str, str, str, tuple[str, ...]]:
        normalized = intent.normalized
        claim = assess_claims(text)
        if intent.out_of_scope:
            return "out_of_scope", "boundary", "refuse_out_of_scope", ("knowledge_boundary",)
        if classroom.primary_act is ClassroomAct.FEEDBACK and not classroom.has_subject_content:
            return "praise", "social", "acknowledge_praise", ()
        if classroom.primary_act in {
            ClassroomAct.GREETING, ClassroomAct.ORGANIZATION, ClassroomAct.TRANSITION,
            ClassroomAct.CLOSURE, ClassroomAct.ENCOURAGEMENT, ClassroomAct.ACKNOWLEDGEMENT,
            ClassroomAct.CONTINUATION,
        } and (not classroom.has_subject_content or classroom.primary_act in {ClassroomAct.ORGANIZATION, ClassroomAct.TRANSITION}):
            return "classroom_ack", "social", "acknowledge_instruction", ()
        if classroom.primary_act is ClassroomAct.OFF_TOPIC:
            return "off_topic", "clarification", "request_clarification", ("return_to_topic",)
        if classroom.primary_act is ClassroomAct.UNCERTAIN:
            return "clarify", "clarification", "request_clarification", ()
        if model:
            return "rate_model", "calculation", "calculate", ("rate_model",)

        if task_equations and ("x=" in normalized or "横坐标" in normalized or "纵轴" in normalized):
            return "calculate_value", "calculation", "calculate", ("equation_value",)
        if classroom.has(ClassroomAct.OFF_TOPIC):
            return "off_topic", "clarification", "request_clarification", ()
        if classroom.has(ClassroomAct.DIRECT_ANSWER):
            if claim.correct is not True:
                return "direct_answer_wrong", "explanation", "acknowledge_instruction", ("residual_misconception",)
            return "direct_answer_correct", "explanation", "acknowledge_instruction", ("surface_recall",)
        if len(task_equations) == 1 and any(marker in normalized for marker in ("特征", "对应", "交点")):
            return "intercept_followup", "explanation", "answer_question", ("intercept_role",)
        if intent.asks_understanding:
            return "understanding_check", "explanation", "express_uncertainty", ("current_understanding",)
        if allow_equation_comparison and len(task_equations) >= 2:
            first, second = task_equations[0], task_equations[1]
            if len({item[0] for item in task_equations}) == 1:
                return "compare_same_slope", "compare", "make_judgment", ("same_slope", "same_steepness", str(first[0]))
            if abs(number(first[0])) == abs(number(second[0])):
                return "compare_same_steepness", "compare", "make_judgment", ("same_steepness",)
            return "compare_steepness", "compare", "make_judgment", ("slope_magnitude",)
        if len(task_equations) == 1 and any(
            marker in normalized for marker in ("分别有什么作用", "分别表示什么", "2和3")
        ):
            return "role_question", "explanation", "answer_question", ("slope_role", "intercept_role")
        if len(task_equations) == 1 and intent.is_question:
            return "single_equation", "calculation", "answer_question", ("equation",)
        if any(marker in normalized for marker in ("复述", "分别改变什么")) and (
            intent.mentions_slope or intent.mentions_intercept
        ):
            return "slope_intercept", "explanation", "answer_question", ("slope_role", "intercept_role")
        if (
            intent.mentions_intercept
            and intent.changes_intercept
            and not intent.mentions_slope
            and not intent.mentions_steepness
        ):
            return "intercept_change", "explanation", "answer_question", ("intercept_position", "slope_unchanged")
        if intent.compares_intercept_change:
            return "compare_intercept", "compare", "compare", ("intercept_position", "slope_unchanged")
        if intent.correction_statement:
            return "correction_ack", "explanation", "reconsider", ("correct_relation",)
        if intent.mentions_intercept and intent.mentions_steepness:
            return "intercept_steepness", "explanation", "answer_question", ("intercept_position", "slope_relation")
        if intent.mentions_slope and intent.mentions_intercept:
            return "slope_intercept", "explanation", "answer_question", ("slope_role", "intercept_role")
        if intent.asks_reason:
            return "reason_request", "explanation", "explain_reason", ("reason",)
        if intent.mentions_slope:
            return "slope_question", "explanation", "answer_question", ("slope_role",)
        if task_equations and any(marker in normalized for marker in ("比较", "例子", "图像")):
            return "visual_compare", "compare", "compare", ("comparison",)
        if not classroom.has_subject_content and classroom.has(ClassroomAct.QUESTION):
            return "missing_task", "clarification", "request_clarification", ("task_conditions",)
        return "clarify", "clarification", "request_clarification", ("task_conditions",)
