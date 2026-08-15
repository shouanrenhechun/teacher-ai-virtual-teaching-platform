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
    misconception = after.misconceptions[0]

    assert after.classroom_state.confusion > before.classroom_state.confusion
    assert misconception.triggered is True
    assert misconception.strength > before.misconceptions[0].strength


def test_targeted_correction_reduces_strength_and_can_correct_error() -> None:
    engine = make_student_a_engine()
    name = "b 越大，直线越陡"
    engine.mark_misconception_triggered(name)
    initial_strength = engine.snapshot().misconceptions[0].strength

    first = engine.apply_behavior(
        TeachingBehavior.TARGETED_CORRECTION,
        target_misconception=name,
    ).misconceptions[0]
    assert first.correction_started is True
    assert first.strength < initial_strength
    assert first.corrected is False

    for _ in range(4):
        engine.apply_behavior(TeachingBehavior.TARGETED_CORRECTION, target_misconception=name)

    final = engine.snapshot().misconceptions[0]
    assert final.strength == 0
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
