from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, Field

from ..llm.base import LLMContext
from ..llm.praise_response import PraiseResponsePolicy
from .response_plan import StudentResponsePlan


class StudentLanguageRenderer(ABC):
    @abstractmethod
    def render(self, plan: StudentResponsePlan, context: LLMContext | None = None) -> str:
        raise NotImplementedError


class DeterministicStudentRenderer(StudentLanguageRenderer):
    """Render only facts already selected by StudentResponsePlanner."""

    def render(self, plan: StudentResponsePlan, context: LLMContext | None = None) -> str:
        context = context or LLMContext()
        shape = plan.response_shape
        if shape == "praise":
            return PraiseResponsePolicy.respond(context, previous_response=self._previous_response(context))
        if shape == "classroom_ack":
            style = " ".join(plan.style_constraints.values())
            if any(marker in style for marker in ("低自信", "谨慎", "先确认", "不太愿意强行猜")):
                options = ("好，我准备一下。", "好的，我先看下一步。", "嗯，我跟着继续。")
            elif any(marker in style for marker in ("自信", "直接", "明确给出")):
                options = ("好，下一题。", "可以，继续。", "好，我们往下看。")
            else:
                options = ("好的，我们继续。", "好，我们接着看。", "嗯，继续。")
            return self._select_text(plan, options)
        if shape == "out_of_scope":
            return self._style(
                plan,
                "这部分我还没学过，暂时只能用初二学过的一次函数知识回答。",
                "这个内容我还没学过，不太懂，我想先按初二范围来理解。",
                "这个我还没学过，超出现在的范围了，我暂时不能用这些知识解释。",
            )
        if shape == "off_topic":
            return self._style(
                plan,
                "这个和现在的一次函数问题无关，我们还是先看 k 和 b 吧。",
                "这个好像不是这节课的问题，可以回到一次函数吗？",
                "这不是当前的一次函数问题，我们先继续讨论直线图像吧。",
            )
        if shape in {"clarify", "missing_task"}:
            return self._style(
                plan,
                "我来试着做，不过需要先知道要用哪道题、哪些条件。",
                "我想先试一下，可以把题目和条件给我吗？",
                "我来试。要用哪道题、哪些条件？",
            )
        if shape == "rate_model":
            return f"我试着把数量记为 x、总费用记为 y：y={plan.content_facts['rate']}x+{plan.content_facts['base']}。"
        if shape == "calculate_value":
            return self._calculate_value(plan)
        if shape == "single_equation":
            equations = plan.content_facts.get("equations", ())
            if equations:
                slope, intercept = equations[0]
                return f"我看到的是 y={slope}x+{intercept}，先根据题目给的条件代入计算。"
            return "我需要先看清题目中的具体条件。"
        if shape == "intercept_followup":
            intercepts = plan.content_facts.get("intercepts", ())
            value = intercepts[0] if intercepts else "这个数"
            return f"{value} 元是起始费用，对应 x=0 时的 y 值，也就是纵轴交点的纵坐标（截距）。"
        if shape == "intercept_change":
            if plan.misconception_status == "corrected":
                return self._style(plan, "改变 b 只会让直线整体向上或向下移动，位置和斜率不变。", "我觉得改变 b 主要是让直线位置移动，斜率应该不变。", "改 b 只会让直线上下移动，斜率不变。")
            if plan.misconception_status in {"weakening", "provisional"}:
                return self._style(plan, "我现在倾向于认为直线只是向上或向下移动，但还想确认倾斜程度是否真的不变。", "我觉得应该是位置变了，不过对斜率会不会受影响还不太确定。", "应该会移动；至于会不会更陡，我还要再确认。")
            return self._style(plan, "b 变大后，我觉得直线会更陡，也会向上移动。", "我不太确定，b 变大后直线会上移，而且可能也会更斜一点。", "b 变大了，直线会上移，也会更陡。")
        if shape == "compare_same_slope":
            slope = plan.content_facts["slopes"][0]
            return self._style(
                plan,
                f"两条直线一样陡，因为它们的斜率都是 {slope}；b 只会改变上下位置，斜率不变。",
                f"我觉得应该一样陡，因为斜率都是 {slope}，b 只会让位置不同，斜率不变。",
                f"一样陡，斜率都是 {slope}；b 只改变上下位置，斜率不变。",
            )
        if shape == "compare_same_steepness":
            return "两条直线一样陡，因为斜率的绝对值相等；符号不同表示方向不同。"
        if shape == "compare_steepness":
            slopes = plan.content_facts["slopes"]
            first = slopes[0] if abs(float(slopes[0])) > abs(float(slopes[1])) else slopes[1]
            return f"我想应该比较斜率的绝对值，{first} 的绝对值更大，所以那条更陡。"
        if shape == "role_question":
            return self._role_response(plan)
        if shape == "direct_answer_wrong":
            return self._style(
                plan,
                "我也觉得 b 变大以后直线会更陡一些，但我还说不清原因。",
                "我不太敢确定……我感觉 b 大一点可能也会让直线更斜。",
                "我觉得 b 越大直线就越陡，应该是这样。",
            )
        if shape == "direct_answer_correct":
            return self._style(
                plan,
                "我先记住 k 决定倾斜、b 决定截距，但还需要自己比较图像才能确认。",
                "我先记下 k 决定倾斜、b 决定截距，不过还不敢说自己已经理解了。",
                "我记住 k 管倾斜、b 管截距了，但最好再给我一道题判断一次。",
            )
        if shape == "understanding_check":
            if plan.misconception_status == "corrected":
                return self._style(plan, "听懂了：k 决定倾斜程度，b 只改变截距和上下位置。", "我觉得现在听懂了，k 管倾斜，b 管截距和上下位置。", "懂了，k 管倾斜，b 管位置。")
            if plan.misconception_status in {"weakening", "provisional"}:
                return self._style(plan, "大部分听懂了，我开始觉得 b 改变的是位置，不过还想再确认理由。", "我懂了一部分，b 应该主要改变位置，但还想再看一个例子。", "基本懂了，b 应该改位置；再问我一道题吧。")
            return self._style(plan, "还没有完全听懂，我还是容易把 b 变大和直线变陡混在一起。", "我还不太明白，总觉得 b 变大后直线也可能更斜。", "还没完全懂，我仍觉得 b 越大直线可能越陡。")
        if shape == "compare_intercept":
            if plan.misconception_status == "provisional":
                return self._style(plan, "我现在觉得 b 主要改变上下位置，但还想把理由再想清楚。", "我先判断是上下位置变了，不过还不确定该怎样说明理由。", "b 应该只改位置，理由我还要再想一下。")
            return self._style(plan, "斜率保持不变，所以直线一样陡；截距改变会让直线整体上下移动。", "我觉得斜率不变时应该还是一样陡，截距只会让位置上下变化。", "一样陡，因为斜率没变；截距变化只改变上下位置。")
        if shape == "correction_ack":
            return self._style(plan, "这样看，截距改变的是上下位置，斜率没有变；我想再用一组图像确认。", "我开始明白了：截距只改位置，不会改变斜率，不过我还想再确认一次。", "明白了，截距管位置，斜率才管倾斜；可以再出一道题检查我。")
        if shape == "intercept_steepness":
            if plan.misconception_status == "corrected":
                return self._style(plan, "b 增大时，直线只会上移；斜率不变，倾斜程度仍由 k 决定。", "我觉得不会，b 只改变上下位置；斜率还是由 k 决定。", "不会，b 管位置，k 才管倾斜程度。")
            if plan.misconception_status in {"weakening", "provisional"}:
                return self._style(plan, "我原来觉得 b 越大会越陡，但现在看应该只是位置改变，倾斜程度由 k 决定。", "我之前有点混淆，现在觉得 b 应该只改位置，斜率还是看 k。", "我刚才混淆了；b 改位置，k 才决定陡不陡。")
            return self._style(plan, "我感觉 b 变大以后直线会更陡一些，但我还说不清原因。", "我不太确定，我觉得 b 变大后直线会上移，而且可能也会更斜一点。", "我觉得 b 越大直线就越陡，也会向上移动。")
        if shape == "slope_intercept":
            if plan.misconception_status == "active":
                return self._style(
                    plan,
                    "k 应该影响倾斜程度，但我还是觉得 b 变大也可能让直线更陡。",
                    "我觉得 k 和倾斜有关，不过我不太确定，b 变大后可能也会更斜。",
                    "k 控制倾斜；b 我觉得也可能影响陡峭程度。",
                )
            return self._style(plan, "k 决定倾斜程度，b 决定截距和上下位置，因为改变 b 不会改变斜率。", "我觉得 k 决定倾斜，b 只改变上下位置，因为斜率并没有随 b 改变。", "k 管倾斜，b 管截距和位置；b 不会改变斜率。")
        if shape == "reason_request":
            if plan.misconception_status == "corrected":
                return self._style(plan, "因为直线的斜率由 k 决定，改变 b 只会改变与 y 轴的交点。", "我觉得原因是 k 没变，所以斜率不变；b 只改变 y 轴交点。", "因为 k 决定斜率，b 只移动 y 轴交点。")
            return self._style(plan, "我现在只能说 k 可能影响倾斜、b 可能影响位置，还需要具体图像来说明原因。", "我有一点猜测，但还不能把理由说清楚，可以给我一个具体例子吗？", "我还没把公式和图像完全对应起来，需要比较两条直线。")
        if shape == "slope_question":
            return self._style(plan, "k 改变会影响直线的斜率和倾斜程度，我可以画两条线具体比较。", "我觉得 k 改变会让倾斜程度变化，不过想画图再确认一下。", "k 决定斜率；k 改变，直线的倾斜程度也会变。")
        if shape == "visual_compare":
            return self._style(plan, "我愿意画图比较，先固定一个量再改变另一个量，应该能看出区别。", "我想先画两条直线比较一下，这样更容易确认自己的判断。", "可以，直接画两条线比较倾斜程度和位置。")
        return "我还不太确定，想先看一个具体例子。"

    @staticmethod
    def _calculate_value(plan: StudentResponsePlan) -> str:
        equations = plan.content_facts.get("equations", ())
        if not equations:
            return "我需要先知道题目中的具体条件。"
        values = plan.content_facts.get("values", ())
        if values:
            suffix = "这就是与纵轴相交时的纵坐标。" if plan.content_facts.get("x") == "0" else ""
            return f"把 x={plan.content_facts.get('x')} 代入，y 分别是 {'、'.join(values)}。{suffix}"
        return "我先把题目中的函数代入计算，还需要确认给出的横坐标。"

    @staticmethod
    def _role_response(plan: StudentResponsePlan) -> str:
        equations = plan.content_facts.get("equations", ())
        if plan.misconception_status in {"corrected", "provisional"} and equations:
            slope, intercept = equations[0]
            return f"{slope} 是斜率，决定倾斜程度；{intercept} 是截距，决定与 y 轴的交点和上下位置。"
        return "k 应该影响倾斜程度，但我还是觉得 b 变大也可能让直线更陡。"

    @staticmethod
    def _style(plan: StudentResponsePlan, natural: str, cautious: str, direct: str) -> str:
        style = " ".join(plan.style_constraints.values())
        previous = plan.style_constraints.get("previous_response", "")
        if plan.style_constraints.get("repeat_teacher") == "true" and previous:
            return previous
        if any(marker in style for marker in ("低自信", "谨慎", "先确认", "不太愿意强行猜")):
            variants = DeterministicStudentRenderer._natural_variants(cautious)
        elif any(marker in style for marker in ("自信", "直接", "明确给出")):
            variants = DeterministicStudentRenderer._natural_variants(direct)
        else:
            variants = DeterministicStudentRenderer._natural_variants(natural)
        return DeterministicStudentRenderer._select_text(plan, variants)

    @staticmethod
    def _select_text(plan: StudentResponsePlan, variants: tuple[str, ...]) -> str:
        previous = plan.style_constraints.get("previous_response", "")
        offset = plan.turn_index % len(variants)
        ordered = variants[offset:] + variants[:offset]
        return next((variant for variant in ordered if variant != previous), ordered[0])

    @staticmethod
    def _natural_variants(sentence: str) -> tuple[str, ...]:
        second = sentence
        for old, new in (
            ("好的", "好"),
            ("我觉得", "我判断"),
            ("我现在只能说", "目前我只能说"),
            ("两条直线", "看这两条直线"),
            ("斜率保持不变", "因为斜率没变"),
        ):
            if old in second:
                second = second.replace(old, new, 1)
                break
        third = sentence
        for old, new in (
            ("我们继续", "接着看"),
            ("我觉得", "我先想想"),
            ("我还想", "我再想"),
            ("截距改变", "b 改变"),
            ("因为它们的斜率", "看它们的斜率"),
        ):
            if old in third:
                third = third.replace(old, new, 1)
                break
        if second == sentence:
            second = "我先判断一下：" + sentence
        if third == sentence:
            third = "我再核对一下：" + sentence
        fourth = "我把条件对照一下：" + sentence
        fifth = "先看这个结论：" + sentence
        return sentence, second, third, fourth, fifth

    @staticmethod
    def _previous_response(context: LLMContext) -> str | None:
        for speaker, content in reversed(context.conversation_history):
            if speaker == "student" and content.strip():
                return content.strip()
        return None


class ReplyPayload(BaseModel):
    reply: str = Field(min_length=1, max_length=1000)


class RealLLMStudentRenderer(StudentLanguageRenderer):
    """Safe renderer adapter; it does not perform network calls by itself."""

    def __init__(self, generator: Callable[[StudentResponsePlan, LLMContext], object] | None = None) -> None:
        self._generator = generator

    def render(self, plan: StudentResponsePlan, context: LLMContext | None = None) -> str:
        if self._generator is None:
            raise RuntimeError("Real renderer requires an explicit generator")
        raw = self._generator(plan, context or LLMContext())
        if isinstance(raw, str):
            payload = ReplyPayload.model_validate_json(raw)
        else:
            payload = ReplyPayload.model_validate(raw)
        return payload.reply.strip()


@dataclass(frozen=True)
class RenderValidation:
    passed: bool
    reasons: tuple[str, ...] = ()


class StudentResponseConsistencyValidator:
    """Validate a candidate against the plan without changing cognitive state."""

    def validate(self, plan: StudentResponsePlan, candidate: str) -> RenderValidation:
        text = (candidate or "").strip()
        if not text:
            return RenderValidation(False, ("empty_reply",))
        reasons: list[str] = []
        lowered = text.lower()
        if plan.response_shape == "out_of_scope" and not any(
            marker in text for marker in ("没学过", "不懂", "不会", "超出", "不知道")
        ):
            reasons.append("boundary_not_acknowledged")
        if plan.misconception_status == "active":
            complete_linear_claim = all(marker in text for marker in ("k", "斜率", "b", "位置"))
            if complete_linear_claim and not any(marker in text for marker in ("不确定", "可能", "还", "混淆")):
                reasons.append("active_state_cannot_claim_complete_understanding")
        if plan.misconception_status == "provisional" and any(
            marker in text for marker in ("完全掌握", "完全明白", "已经完全理解")
        ):
            reasons.append("provisional_cannot_claim_mastery")
        if "系统提示" in text or "prompt" in lowered or "misconception_status" in lowered:
            reasons.append("internal_state_leak")
        if plan.response_shape in {"praise", "classroom_ack"} and len(text) > 90:
            reasons.append("social_reply_overexplains")
        return RenderValidation(not reasons, tuple(reasons))


class StudentResponsePipeline:
    """One render, at most one retry, then deterministic fallback."""

    def __init__(
        self,
        planner: object,
        renderer: StudentLanguageRenderer,
        validator: StudentResponseConsistencyValidator | None = None,
        fallback: StudentLanguageRenderer | None = None,
    ) -> None:
        self.planner = planner
        self.renderer = renderer
        self.validator = validator or StudentResponseConsistencyValidator()
        self.fallback = fallback or DeterministicStudentRenderer()

    def respond(self, teacher_text: str, context: LLMContext | None = None) -> str:
        context = context or LLMContext()
        plan = self.planner.build(teacher_text, context)
        candidate = self._safe_render(plan, context)
        validation = self.validator.validate(plan, candidate)
        if validation.passed:
            return candidate
        retry = self._safe_render(plan, context)
        if self.validator.validate(plan, retry).passed:
            return retry
        return self.fallback.render(plan, context)

    def _safe_render(self, plan: StudentResponsePlan, context: LLMContext) -> str:
        try:
            return self.renderer.render(plan, context)
        except Exception:
            # Invalid JSON, transport adapters, and empty candidates all take
            # the same bounded path: one retry, then deterministic fallback.
            return ""
