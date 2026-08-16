from app.services.virtual_student import MisconceptionState, StudentResponseEvidenceAnalyzer


def binomial_misconception() -> MisconceptionState:
    return MisconceptionState(
        name="括号平方遗漏中间项",
        concept="完全平方公式",
        description="认为括号平方只需分别平方每一项。",
        strength=0.8,
        correction_condition="先写成两个相同括号相乘。",
        semantic_type="binomial_square",
    )


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


def test_binomial_residual_shortcut_is_detected() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "(x+3)^2=x²+9。",
        teacher_text="(x+3)^2 等于什么？",
        misconception=binomial_misconception(),
    )

    assert evidence.shows_residual_misconception is True
    assert evidence.knowledge_precision == "incorrect"


def test_binomial_residual_separate_square_statement_is_detected() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "括号平方就是每一项分别平方，不需要中间项。",
        misconception=binomial_misconception(),
    )

    assert evidence.shows_residual_misconception is True


def test_binomial_residual_cross_terms_can_be_omitted_is_detected() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "确实有两个 ab，不过这两项最后应该可以省掉吧。",
        misconception=binomial_misconception(),
    )

    assert evidence.shows_residual_misconception is True
    assert evidence.knowledge_precision != "correct"


def test_binomial_residual_cross_terms_need_not_be_written_is_detected() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "会出现 3x 和 3x，但是平方的时候中间项不用写吧。",
        misconception=binomial_misconception(),
    )

    assert evidence.shows_residual_misconception is True


def test_binomial_residual_cross_terms_can_be_ignored_is_detected() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "我知道会乘出交叉项，但感觉它们可以忽略。",
        misconception=binomial_misconception(),
    )

    assert evidence.shows_residual_misconception is True


def test_binomial_residual_real_r4_response_is_detected() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "就是 x·2 和 2·x 这两项吧……可它们应该能省略掉吧？",
        misconception=binomial_misconception(),
    )

    assert evidence.shows_residual_misconception is True
    assert evidence.knowledge_precision != "correct"


def test_binomial_correct_cross_terms_must_be_kept_are_not_residual() -> None:
    for response in (
        "中间项不能省，因为 ab 和 ba 都真实存在。",
        "原来我刚才把两个 2x 忽略了，这是不对的。",
    ):
        evidence = StudentResponseEvidenceAnalyzer().analyze(
            response,
            misconception=binomial_misconception(),
        )

        assert evidence.shows_residual_misconception is False


def test_binomial_historical_omission_correction_is_not_residual() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "我以前以为中间项可以省掉，现在知道两个 ab 必须合并成 2ab。",
        misconception=binomial_misconception(),
    )

    assert evidence.shows_residual_misconception is False


def test_binomial_historical_correction_is_not_residual() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "我以前以为要分别平方，现在知道还会有交叉项。",
        misconception=binomial_misconception(),
    )

    assert evidence.shows_residual_misconception is False


def test_binomial_cross_term_explanation_is_correct() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "(x+3)(x+3) 展开有 3x+3x，所以中间是 6x。",
        teacher_text="你能解释中间项从哪里来吗？",
        misconception=binomial_misconception(),
    )

    assert evidence.states_correct_conclusion is True
    assert evidence.explains_reason_correctly is True
    assert evidence.shows_residual_misconception is False
    assert evidence.knowledge_precision == "correct"


def test_binomial_surface_formula_recall_is_not_transfer() -> None:
    formula = "(a+b)^2=a²+2ab+b²"
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        formula,
        teacher_text=formula,
        previous_teacher_text=formula,
        misconception=binomial_misconception(),
    )

    assert evidence.parrots_teacher is True
    assert evidence.transfer_success is False
    assert evidence.evidence_insufficient is True


def test_binomial_transfer_with_coefficients_is_correct() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "(2x+3)^2=4x²+12x+9，中间的 12x 来自两个 6x。",
        teacher_text="再做一个变式：(2x+3)^2。",
        misconception=binomial_misconception(),
    )

    assert evidence.explains_reason_correctly is True
    assert evidence.transfer_success is True
    assert evidence.shows_residual_misconception is False


def test_binomial_negative_transfer_without_middle_term_fails() -> None:
    evidence = StudentResponseEvidenceAnalyzer().analyze(
        "(x-5)^2=x²+25。",
        teacher_text="验证变式：(x-5)^2。",
        misconception=binomial_misconception(),
    )

    assert evidence.transfer_success is False
    assert evidence.shows_residual_misconception is True
