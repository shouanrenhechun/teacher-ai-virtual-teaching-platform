from tests.test_virtual_student_engine import make_student_a_engine


def _set_status(engine, status: str, *, corrected: bool = False) -> None:
    misconception = engine._misconceptions[0]
    misconception.status = status
    misconception.corrected = corrected


def test_active_direct_answer_and_parroting_cannot_correct() -> None:
    engine = make_student_a_engine()

    evidence = engine.apply_student_response_evidence(
        "k 控制斜率，b 控制纵截距。",
        "答案就是 k 控制斜率，b 控制纵截距。",
        {"opportunity_strength": 0.2},
        previous_teacher_text="答案就是 k 控制斜率，b 控制纵截距。",
    )

    state = engine.snapshot().misconceptions[0]
    assert evidence.parrots_teacher is True
    assert state.corrected is False
    assert state.status == "active"
    assert state.stable_correct_evidence_count == 0


def test_one_transfer_is_only_a_correction_candidate() -> None:
    engine = make_student_a_engine()
    _set_status(engine, "provisional")

    engine.apply_student_response_evidence(
        "两条直线一样陡，因为 k 都是 -3；b 不同只会让位置上下移动。",
        "y=-3x+1 和 y=-3x+6 哪条更陡？",
    )

    state = engine.snapshot().misconceptions[0]
    assert state.transfer_evidence == 1
    assert state.stable_correct_evidence_count == 1
    assert state.corrected is False
    assert state.status == "provisional"


def test_independent_explanation_then_transfer_can_correct() -> None:
    engine = make_student_a_engine()
    _set_status(engine, "provisional")

    engine.apply_student_response_evidence(
        "k 决定倾斜程度，b 主要改变上下位置，因为 k 控制陡峭程度，b 改变截距位置。",
        "请用自己的话解释 k 和 b。",
    )
    engine.apply_student_response_evidence(
        "两条直线一样陡，因为 k 都是 -3；b 不同只会让位置上下移动。",
        "y=-3x+1 和 y=-3x+6 哪条更陡？",
    )

    state = engine.snapshot().misconceptions[0]
    assert state.stable_correct_evidence_count == 2
    assert state.corrected is True
    assert state.status == "corrected"
    assert state.strength > 0.05


def test_vague_error_free_response_is_insufficient_without_weakening() -> None:
    engine = make_student_a_engine()
    _set_status(engine, "provisional")
    before = engine.snapshot().misconceptions[0]

    evidence = engine.apply_student_response_evidence(
        "应该差不多吧。",
        "你能说明 b 改变了什么吗？",
    )

    after = engine.snapshot().misconceptions[0]
    assert evidence.evidence_insufficient is True
    assert after.status == "provisional"
    assert after.strength == before.strength


def test_new_residual_misconception_can_weaken_provisional() -> None:
    engine = make_student_a_engine()
    _set_status(engine, "provisional")

    engine.apply_student_response_evidence(
        "我还是觉得 b 越大越陡。",
        "你现在还这样认为吗？",
    )

    state = engine.snapshot().misconceptions[0]
    assert state.status == "weakening"
    assert state.corrected is False
    assert state.stable_correct_evidence_count == 0


def test_corrected_state_can_roll_back_on_explicit_residual_error() -> None:
    engine = make_student_a_engine()
    _set_status(engine, "corrected", corrected=True)
    engine._misconceptions[0].stable_correct_evidence_count = 2

    engine.apply_student_response_evidence(
        "但是我还是觉得 b 越大越陡。",
        "你现在还这样认为吗？",
    )

    state = engine.snapshot().misconceptions[0]
    assert state.corrected is False
    assert state.status == "weakening"
    assert state.stable_correct_evidence_count == 0
