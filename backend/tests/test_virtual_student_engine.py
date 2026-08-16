from app.services.virtual_student import (
    KnowledgeStateValue,
    MisconceptionState,
    PromptBuilder,
    StudentProfile,
    TeachingBehavior,
    VirtualStudentEngine,
    detect_teacher_behavior,
)


def make_student_a_engine() -> VirtualStudentEngine:
    profile = StudentProfile(
        name="学生 A",
        grade="初二",
        base_level=0.68,
        personality_description="偏谨慎，不太主动提问。",
        initiative=0.3,
        confidence=0.55,
        knowledge_states=[
            KnowledgeStateValue("一次函数基本定义", 0.85),
            KnowledgeStateValue("一次函数图像基础", 0.65),
            KnowledgeStateValue("k 的意义", 0.4),
            KnowledgeStateValue("b 的意义", 0.35),
        ],
        misconceptions=[
            MisconceptionState(
                name="b 越大，直线越陡",
                concept="k 与 b 的意义",
                description="混淆 b 对截距和平移的影响。",
                strength=0.8,
                correction_condition="固定 k、改变 b 进行图像对比。",
            )
        ],
    )
    return VirtualStudentEngine(profile)


def test_engine_initializes_all_state_values_in_range() -> None:
    engine = make_student_a_engine()
    snapshot = engine.snapshot()

    assert 0 <= snapshot.classroom_state.understanding <= 1
    assert 0 <= snapshot.classroom_state.confusion <= 1
    assert 0 <= snapshot.classroom_state.engagement <= 1
    assert 0 <= snapshot.classroom_state.confidence <= 1
    assert snapshot.misconceptions[0].triggered is False
    assert snapshot.misconceptions[0].corrected is False


def test_effective_example_increases_understanding_without_exceeding_one() -> None:
    engine = make_student_a_engine()
    before = engine.classroom_state

    after = engine.apply_behavior(TeachingBehavior.EFFECTIVE_EXAMPLE).classroom_state

    assert after.understanding > before.understanding
    assert after.confusion < before.confusion
    assert all(0 <= value <= 1 for value in vars(after).values())


def test_effective_question_increases_engagement() -> None:
    engine = make_student_a_engine()
    before = engine.classroom_state.engagement

    after = engine.apply_behavior(TeachingBehavior.EFFECTIVE_QUESTION).classroom_state

    assert after.engagement > before


def test_direct_answer_only_increases_surface_recall() -> None:
    engine = make_student_a_engine()
    before = engine.snapshot()
    before_mastery = [item.mastery for item in before.knowledge_states]

    after = engine.apply_behavior(TeachingBehavior.DIRECT_ANSWER)

    assert after.classroom_state.surface_recall > before.classroom_state.surface_recall
    assert after.classroom_state.understanding == before.classroom_state.understanding
    assert [item.mastery for item in after.knowledge_states] == before_mastery


def test_incorrect_explanation_increases_confusion_and_triggers_error() -> None:
    engine = make_student_a_engine()
    before = engine.snapshot()

    after = engine.apply_behavior(
        TeachingBehavior.INCORRECT_EXPLANATION,
        target_misconception="b 越大，直线越陡",
    )
    evidence = engine.apply_student_response_evidence(
        "我还是觉得 b 越大，直线越陡。",
        "b 越大，直线当然越陡。",
    )
    misconception = after.misconceptions[0]

    assert after.classroom_state.confusion > before.classroom_state.confusion
    assert evidence.shows_residual_misconception is True
    updated = engine.snapshot().misconceptions[0]
    assert updated.triggered is True
    assert updated.strength >= before.misconceptions[0].strength


def test_student_evidence_reduces_strength_and_can_correct_error() -> None:
    engine = make_student_a_engine()
    name = "b 越大，直线越陡"
    engine.mark_misconception_triggered(name)
    initial_strength = engine.snapshot().misconceptions[0].strength

    engine.apply_behavior(
        TeachingBehavior.TARGETED_CORRECTION,
        target_misconception=name,
    )
    assert engine.snapshot().misconceptions[0].strength == initial_strength
    engine.apply_student_response_evidence(
        "k 决定倾斜程度，b 只改变上下位置。",
        "固定 k 改变 b。",
    )
    engine.apply_student_response_evidence(
        "这两条直线的 k 都是 -3，所以倾斜程度一样；b 只让它们上下移动。",
        "比较 y=-3x+1 和 y=-3x+6。",
    )

    final = engine.snapshot().misconceptions[0]
    assert final.strength <= initial_strength
    assert final.corrected is True
    assert final.triggered is False


def test_teacher_text_rules_and_prompt_builder_include_required_context() -> None:
    engine = make_student_a_engine()
    correction = "固定 k 改变 b，b 不影响斜率，只改变截距位置。"

    assert detect_teacher_behavior(correction) is TeachingBehavior.TARGETED_CORRECTION
    engine.update_from_teacher_text(correction)
    prompt = PromptBuilder().build(engine, "请观察这两条直线有什么不同。")

    for expected in (
        "初二",
        "一次函数基本定义",
        "b 越大，直线越陡",
        "understanding=",
        "偏谨慎",
        "请观察这两条直线有什么不同",
        "不得突然获得尚未掌握的知识",
    ):
        assert expected in prompt


def test_guided_evidence_reduces_misconception_gradually() -> None:
    engine = make_student_a_engine()
    strengths = [engine.snapshot().misconceptions[0].strength]

    for teacher_text in (
        "比较 y=2x+3 和 y=2x+5，它们的 k 相同，倾斜程度会不会一样？",
        "如果图像只是整体上下移动，那么 b 改变的到底是什么？",
        "你现在用自己的话说说 k 和 b 分别控制什么？",
    ):
        opportunity = engine.get_correction_opportunity(teacher_text)
        engine.update_from_teacher_text(teacher_text)
        engine.apply_student_response_evidence(
            "k 可能影响倾斜程度，b 可能影响位置，但我还需要验证。",
            teacher_text,
            opportunity,
        )
        strengths.append(engine.snapshot().misconceptions[0].strength)

    assert strengths == sorted(strengths, reverse=True)
    assert strengths[0] > strengths[-1] > 0


def test_prompt_builder_includes_bounded_prior_dialogue() -> None:
    engine = make_student_a_engine()
    prompt = PromptBuilder().build(
        engine,
        "如果只改变 b，直线会怎样？",
        [
            ("teacher", "先比较两条直线。"),
            ("student", "我好像把 b 和 k 弄反了。"),
        ],
    )

    assert "【最近对话】" in prompt
    assert "Teacher: 先比较两条直线。" in prompt
    assert "Student: 我好像把 b 和 k 弄反了。" in prompt


def _prompt_for_misconception_status(status: str, *, corrected: bool = False) -> str:
    engine = make_student_a_engine()
    misconception = engine._misconceptions[0]
    misconception.status = status
    misconception.corrected = corrected
    return PromptBuilder().build(engine, "请说说你的想法。")


def test_prompt_active_keeps_strong_misconception() -> None:
    prompt = _prompt_for_misconception_status("active")

    assert "Prompt模式=strong_misconception" in prompt
    assert "你目前比较确信" in prompt
    assert "不要无缘无故放弃" in prompt


def test_prompt_weakening_allows_conflict_without_forcing_old_error() -> None:
    prompt = _prompt_for_misconception_status("weakening")

    assert "Prompt模式=conflicted" in prompt
    assert "开始怀疑" in prompt
    assert "不要为了维持旧设定而强行重复错误" in prompt


def test_prompt_provisional_prefers_correct_understanding_without_persona_pressure() -> None:
    prompt = _prompt_for_misconception_status("provisional")

    assert "Prompt模式=mostly_correct_unstable" in prompt
    assert "目前倾向于认为" in prompt
    assert "不要主动为了维持角色而重新加入旧错误" in prompt
    assert "你目前比较确信" not in prompt


def test_prompt_corrected_keeps_old_error_as_history_only() -> None:
    prompt = _prompt_for_misconception_status("corrected", corrected=True)

    assert "历史错误（不可作为当前信念）" in prompt
    assert "Prompt模式=corrected_history" in prompt
    assert "你以前曾有过" in prompt
    assert "你目前比较确信" not in prompt


def test_prompt_status_rollback_returns_to_conflicted_mode() -> None:
    provisional = _prompt_for_misconception_status("provisional")
    weakening = _prompt_for_misconception_status("weakening")

    assert "Prompt模式=mostly_correct_unstable" in provisional
    assert "Prompt模式=conflicted" in weakening
    assert "开始怀疑" in weakening
