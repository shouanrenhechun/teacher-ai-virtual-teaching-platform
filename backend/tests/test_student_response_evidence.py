from app.services.virtual_student import StudentResponseEvidenceAnalyzer


def test_evidence_detects_persistent_misconception() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "我还是觉得 b 越大越陡。",
        teacher_text="如果只改变 b，直线会怎样？",
    )

    assert evidence.shows_residual_misconception is True
    assert evidence.evidence_level <= 1


def test_evidence_detects_partial_understanding_with_residual_error() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "应该是 k 决定斜率，不过我还是觉得 b 变大会稍微更陡。",
        teacher_text="你能解释 k 和 b 的作用吗？",
    )

    assert evidence.states_correct_conclusion is True
    assert evidence.conclusion_level == "partial"
    assert evidence.shows_residual_misconception is True
    assert evidence.evidence_level <= 2


def test_evidence_rejects_mechanical_repetition() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "k决定斜率，b决定纵截距。",
        teacher_text="k决定斜率，b决定纵截距。",
        previous_teacher_text="k决定斜率，b决定纵截距。",
    )

    assert evidence.parrots_teacher is True
    assert evidence.transfer_success is False


def test_evidence_accepts_complete_transfer_explanation() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "这两条直线的 k 都是 -3，所以倾斜程度相同。b 从1变成6只会让直线整体向上移动。",
        teacher_text="那 y=-3x+1 和 y=-3x+6 呢？",
    )

    assert evidence.states_correct_conclusion is True
    assert evidence.explains_reason_correctly is True
    assert evidence.transfer_success is True
    assert evidence.shows_residual_misconception is False
    assert evidence.evidence_level == 3


def test_evidence_accepts_transfer_with_a_new_common_slope() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "两条直线一样陡，因为它们的 k 都是 4；b 不同只会让位置上下移动。",
        teacher_text="y=4x-2 和 y=4x+7 哪一条更陡？",
    )

    assert evidence.transfer_success is True


def test_evidence_does_not_mark_corrected_when_answer_is_only_uncertain() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "好像是 b 改变位置，但我还不太确定。",
        teacher_text="你能说说 b 改变什么吗？",
    )

    assert evidence.shows_uncertainty is True
    assert evidence.transfer_success is False
