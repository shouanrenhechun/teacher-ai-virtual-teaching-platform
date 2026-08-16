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


def test_regression_case_a_detects_explicit_misconception() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "3 的话……我总觉得它越大，直线好像也会越陡？",
        teacher_text="在 y=2x+3 中，2 和 3 分别有什么作用？",
    )

    assert evidence.states_correct_conclusion is False
    assert evidence.shows_residual_misconception is True
    assert evidence.knowledge_precision == "incorrect"
    assert evidence.conceptual_uncertainty is False


def test_regression_case_b_separates_hedging_from_residual_doubt() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "嗯……我觉得 k 是控制直线有多陡的，k 越大越陡；b 应该是让直线上下移动的，就是整体往上或往下挪，不改变陡的程度……吧？不过我还是有点不太确定，可能 b 也会有一点点影响？",
        teacher_text="你能用自己的话说说 k 和 b 分别控制什么吗？",
    )

    assert evidence.states_correct_conclusion is True
    assert evidence.conclusion_level == "partial"
    assert evidence.shows_residual_misconception is True
    assert evidence.linguistic_hedging is True
    assert evidence.conceptual_uncertainty is True
    assert evidence.knowledge_precision == "partial"
    assert evidence.transfer_success is False


def test_regression_case_c_accepts_hedged_but_complete_transfer() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "嗯……我觉得它们一样陡吧，因为 k 都是 4，陡的程度应该由 k 决定。区别就是 b 不一样，一个在下面一点，一个在上面一点。",
        teacher_text="y=4x-2 和 y=4x+7 哪一条更陡？",
    )

    assert evidence.states_correct_conclusion is True
    assert evidence.explains_reason_correctly is True
    assert evidence.shows_residual_misconception is False
    assert evidence.linguistic_hedging is True
    assert evidence.conceptual_uncertainty is False
    assert evidence.transfer_success is True
    assert evidence.knowledge_precision == "correct"


def test_regression_case_d_rejects_correct_conclusion_with_residual_error() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "它们应该一样陡，因为 k 都一样，不过我还是觉得 +7 那条看起来可能更陡一点。",
        teacher_text="y=4x-2 和 y=4x+7 哪一条更陡？",
    )

    assert evidence.states_correct_conclusion is True
    assert evidence.conclusion_level == "partial"
    assert evidence.shows_residual_misconception is True
    assert evidence.conceptual_uncertainty is True
    assert evidence.transfer_success is False


def test_regression_case_e_marks_mechanical_repetition() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "k 控制斜率，b 控制纵截距。",
        teacher_text="k 控制斜率，b 控制纵截距。",
        previous_teacher_text="k 控制斜率，b 控制纵截距。",
    )

    assert evidence.parrots_teacher is True
    assert evidence.transfer_success is False


def test_regression_case_f_accepts_complete_transfer_without_hedging() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "两条直线的 k 都是 -5，所以倾斜程度相同。b 一个是 2、一个是 -8，只会让直线的位置上下不同，不改变斜率。",
        teacher_text="y=-5x+2 和 y=-5x-8 哪一条更陡？",
    )

    assert evidence.states_correct_conclusion is True
    assert evidence.explains_reason_correctly is True
    assert evidence.shows_residual_misconception is False
    assert evidence.conceptual_uncertainty is False
    assert evidence.transfer_success is True
    assert evidence.knowledge_precision == "correct"


def test_regression_case_g_marks_slope_statement_as_partial_precision() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "k 越大，直线越陡。",
        teacher_text="你知道 k 对图像有什么影响吗？",
    )

    assert evidence.knowledge_precision == "partial"
    assert evidence.transfer_success is False


def test_direct_question_detects_b_increase_as_residual_misconception() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "b变大了，直线不是会更斜吗？",
        teacher_text="如果把 b 从 3 改成 5，图像会发生什么？",
    )

    assert evidence.shows_residual_misconception is True


def test_intercept_increase_as_more_sloped_is_residual_misconception() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "我感觉截距越大，倾斜程度也会大一点。",
        teacher_text="如果把 b 从 3 改成 5，图像会发生什么？",
    )

    assert evidence.shows_residual_misconception is True


def test_negative_b_increase_statement_is_not_residual_misconception() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "虽然 b 变大了，但直线不会变得更斜。",
        teacher_text="如果把 b 从 3 改成 5，图像会发生什么？",
    )

    assert evidence.shows_residual_misconception is False


def test_historical_misconception_correction_is_not_residual() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "以前我以为 b 越大会越陡，现在知道不是这样。",
        teacher_text="你现在还这样认为吗？",
    )

    assert evidence.shows_residual_misconception is False
