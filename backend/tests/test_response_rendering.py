from __future__ import annotations

import httpx

from app.core.config import Settings
from app.services.llm.base import LLMContext, LLMServiceError
from app.services.llm.real import RealLLMClient
from app.services.virtual_student import (
    DeterministicStudentRenderer,
    RealLLMStudentRenderer,
    StudentResponseConsistencyValidator,
    StudentResponsePipeline,
    StudentResponsePlanner,
    build_student_renderer_prompt,
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


def test_real_renderer_prompt_is_plan_bounded_and_keeps_recent_history() -> None:
    context = LLMContext(
        conversation_history=(
            ("teacher", "先看第一条题目。"),
            ("student", "我先试试。"),
        ),
        style_examples=("我先试着说一下。",),
    )
    plan = StudentResponsePlanner().build("为什么两条线一样陡？", context)
    prompt = build_student_renderer_prompt(plan, context)

    assert "只输出这一轮学生会说的话" in prompt
    assert "先看第一条题目" in prompt
    assert "我先试着说一下" in prompt
    assert "claim_full_mastery" in prompt
    assert "不要输出推理" not in prompt


def test_real_renderer_from_client_uses_structured_plan_request(monkeypatch) -> None:
    requests = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, *, headers, json):
            requests.append((url, headers, json))
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"reply":"我先试着回答。"}'}}]})

    monkeypatch.setattr("app.services.llm.real.httpx.Client", FakeClient)
    client = RealLLMClient(
        Settings(
            llm_provider="real",
            llm_api_key="test-key",
            llm_api_url="https://api.deepseek.com/chat/completions",
            llm_model="deepseek-v4-flash",
            llm_timeout_seconds=1,
            llm_temperature=0.7,
            llm_max_tokens=180,
        )
    )
    renderer = RealLLMStudentRenderer.from_client(client)
    context = LLMContext()
    plan = StudentResponsePlanner().build("请解释 k 和 b 的作用。", context)

    assert renderer.render(plan, context) == "我先试着回答。"
    assert requests[0][0] == "https://api.deepseek.com/chat/completions"
    assert requests[0][2]["model"] == "deepseek-v4-flash"
    assert requests[0][2]["temperature"] == 0.7
    assert requests[0][2]["max_tokens"] == 180
    assert "test-key" not in requests[0][2]["messages"][1]["content"]


def test_invalid_real_renderer_output_retries_once_then_falls_back() -> None:
    calls = 0

    def invalid_generator(plan, context):
        nonlocal calls
        calls += 1
        return "not-json"

    pipeline = _pipeline(RealLLMStudentRenderer(invalid_generator))
    response = pipeline.respond("请比较 y=2x+1 和 y=2x+3。", LLMContext())

    assert calls == 2
    assert "一样陡" in response
    assert pipeline.last_metadata['source'] == 'deterministic_fallback'
    assert pipeline.last_metadata['learning_evidence_allowed'] is False
    assert pipeline.last_metadata['failure_category'] == 'render_error_and_validation_rejection'
    assert [error['category'] for error in pipeline.last_metadata['render_errors']] == [
        'structured_output_invalid', 'structured_output_invalid'
    ]
    assert all('test-key' not in str(error) for error in pipeline.last_metadata['render_errors'])


def test_mock_response_is_explicitly_eligible_for_demo_learning_evidence() -> None:
    pipeline = _pipeline()
    pipeline.respond('请比较 y=2x+1 和 y=2x+3。', LLMContext())
    assert pipeline.last_metadata['source'] == 'mock'
    assert pipeline.last_metadata['learning_evidence_allowed'] is True


def test_renderer_failure_metadata_is_categorized_without_exception_text() -> None:
    def failing_generator(plan, context):
        raise LLMServiceError('HTTP 502 secret-key-must-not-be-recorded')

    pipeline = _pipeline(RealLLMStudentRenderer(failing_generator))
    pipeline.respond('请比较 y=2x+1 和 y=2x+3。', LLMContext())
    assert pipeline.last_metadata['source'] == 'deterministic_fallback'
    assert pipeline.last_metadata['learning_evidence_allowed'] is False
    assert pipeline.last_metadata['render_errors'][0]['category'] == 'provider_http'
    assert pipeline.last_metadata['render_errors'][0]['http_status'] == 502
    assert 'secret-key-must-not-be-recorded' not in str(pipeline.last_metadata)


def test_fake_bad_renderer_is_rejected_retried_and_falls_back() -> None:
    calls = 0

    def bad_generator(plan, context):
        nonlocal calls
        calls += 1
        return {"reply": "我完全明白了，k 决定斜率和倾斜程度，b 只决定位置，我已经完全掌握了。"}

    pipeline = _pipeline(RealLLMStudentRenderer(bad_generator))
    response = pipeline.respond("请解释 k 和 b 的作用。", LLMContext(misconception_status="active"))

    assert calls == 2
    assert pipeline.validator_rejections == 2
    assert pipeline.retry_count == 1
    assert pipeline.fallback_count == 1
    assert "可能" in response or "还是" in response


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
