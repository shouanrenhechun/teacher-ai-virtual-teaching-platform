from __future__ import annotations

from app.services.llm.base import LLMContext
from app.services.virtual_student import (
    DeterministicStudentRenderer,
    RealLLMStudentRenderer,
    StudentResponseConsistencyValidator,
    StudentResponsePipeline,
    StudentResponsePlanner,
)


def _pipeline(renderer=None):
    return StudentResponsePipeline(
        planner=StudentResponsePlanner(),
        renderer=renderer or DeterministicStudentRenderer(),
        validator=StudentResponseConsistencyValidator(),
    )


def test_plan_carries_facts_and_renderer_does_not_need_engine() -> None:
    context = LLMContext(misconception_status="active", misconception_strength=0.8)
    plan = StudentResponsePlanner().build("比较 y=2x+1 和 y=2x+3。", context)

    assert plan.response_goal == "make_judgment"
    assert plan.current_belief_stance == "holds_misconception"
    assert plan.content_facts["same_slope"] is True
    assert plan.content_facts["same_steepness"] is True
    assert "same_slope" in plan.must_include
    assert "claim_full_mastery" in plan.must_avoid

    response = DeterministicStudentRenderer().render(plan, context)
    assert "一样陡" in response
    assert plan.misconception_strength == 0.8


def test_active_candidate_that_suddenly_claims_complete_understanding_is_rejected() -> None:
    context = LLMContext(misconception_status="active")
    plan = StudentResponsePlanner().build("请解释 k 和 b 的作用。", context)
    result = StudentResponseConsistencyValidator().validate(
        plan, "k 决定斜率，b 改变位置，我已经完全掌握了。"
    )

    assert result.passed is False
    assert "active_state_cannot_claim_complete_understanding" in result.reasons


def test_provisional_mastery_claim_is_rejected() -> None:
    context = LLMContext(misconception_status="provisional")
    plan = StudentResponsePlanner().build("请解释 k 和 b 的作用。", context)
    result = StudentResponseConsistencyValidator().validate(
        plan, "我已经完全理解并完全掌握了。"
    )

    assert result.passed is False
    assert "provisional_cannot_claim_mastery" in result.reasons


def test_out_of_scope_candidate_must_acknowledge_boundary() -> None:
    context = LLMContext()
    plan = StudentResponsePlanner().build("请用线性代数的矩阵解释一次函数。", context)
    validator = StudentResponseConsistencyValidator()

    assert validator.validate(plan, "我知道矩阵可以表示线性变换。你还想问什么？").passed is False
    assert validator.validate(plan, "这个内容我还没学过，先按初二知识来回答。").passed is True


def test_real_renderer_accepts_structured_reply_without_calling_network() -> None:
    calls = []

    def generator(plan, context):
        calls.append((plan.response_goal, context.topic))
        return {"reply": "我先试着回答。"}

    plan = StudentResponsePlanner().build("今天我们继续学习一次函数。", LLMContext())
    response = RealLLMStudentRenderer(generator).render(plan, LLMContext())

    assert response == "我先试着回答。"
    assert calls == [(plan.response_goal, "一次函数 k 与 b 的意义")]


def test_invalid_real_renderer_output_retries_once_then_falls_back() -> None:
    calls = 0

    def invalid_generator(plan, context):
        nonlocal calls
        calls += 1
        return "not-json"

    response = _pipeline(RealLLMStudentRenderer(invalid_generator)).respond(
        "请比较 y=2x+1 和 y=2x+3。", LLMContext()
    )

    assert calls == 2
    assert "一样陡" in response


def test_deterministic_renderer_has_observable_profile_style_without_id_branch() -> None:
    planner = StudentResponsePlanner()
    teacher_text = "如果把 b 从 3 改成 5，图像会发生什么？"
    cautious = LLMContext(
        confidence_style="主观自信较低，常用应该和我觉得。",
        confirmation_seeking="喜欢先确认自己的理解。",
    )
    direct = LLMContext(confidence_style="表达直接、自信，先给出判断。")

    cautious_reply = _pipeline().respond(teacher_text, cautious)
    direct_reply = _pipeline().respond(teacher_text, direct)

    assert cautious_reply != direct_reply
    assert "不太确定" in cautious_reply or "应该" in cautious_reply
    assert "会上移" in direct_reply or "更陡" in direct_reply
