from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .clause_splitter import split_linear_clauses
from .linear_math import NUMBER, equations, mask_equations, number
from .slope_claims import assess_slope_claims

LINEAR_KB = "linear_kb"
BINOMIAL_SQUARE = "binomial_square"


@dataclass(frozen=True)
class DomainEvidence:
    """Domain-specific evidence consumed by the generic state engine."""

    states_correct_conclusion: bool
    conclusion_level: str
    explains_reason_correctly: bool
    shows_residual_misconception: bool
    transfer_success: bool
    knowledge_precision: str
    slope_claim_status: str = "not_applicable"


class MisconceptionSemanticEvaluator:
    semantic_type = LINEAR_KB
    prompt_guidance = "k 决定倾斜程度，b 主要改变直线的上下位置。"
    knowledge_keywords = ("k", "b", "图像", "斜率", "截距")

    def analyze(self, response: str, teacher_text: str) -> DomainEvidence:
        raise NotImplementedError

    def matches_text(self, text: str) -> bool:
        normalized = _compact(text)
        return any(keyword in normalized for keyword in self.knowledge_keywords)

    def is_correction_evidence(self, text: str) -> bool:
        return self.matches_text(text)


class LinearKbSemanticEvaluator(MisconceptionSemanticEvaluator):
    """Semantic rules for the original y=kx+b misconception."""

    def analyze(self, response: str, teacher_text: str) -> DomainEvidence:
        normalized = _compact(response)
        teacher_normalized = _compact(teacher_text)
        has_k = _linear_k_role(normalized)
        has_b = _linear_b_role(normalized)
        residual = _linear_residual(response, teacher_normalized)
        negative_claim = _linear_negative_claim(response)
        self_correction = _has_explicit_linear_self_correction(normalized)
        slope_status = assess_slope_claims(response, teacher_text).status
        explains = (
            not residual
            and (
                (
                    has_k
                    and has_b
                    and any(
                        marker in normalized
                        for marker in (
                            "因为", "k相同", "k都", "斜率相同", "只改变b", "只会让直线",
                            "所以倾斜", "由k决定", "由k控制", "只看k", "k不变",
                            "斜率不变", "斜率保持不变", "倾斜程度不变", "一样陡", "同样陡",
                            "k决定", "k控制", "k影响", "决定倾斜", "决定斜率",
                            "只影响位置", "只改变位置", "只是上下", "只影响上下", "只改变上下",
                            "与b无关", "跟b无关", "b无关",
                        )
                    )
                )
                or (
                    negative_claim
                    and has_b
                    and any(
                        marker in normalized
                        for marker in ("位置", "上下", "上移", "下移", "平移", "移动", "挪")
                    )
                )
                or (self_correction and has_k)
                or (slope_status == "correct" and any(marker in normalized for marker in ("绝对值", "|k|")))
            )
        )
        if slope_status in {"incorrect", "insufficient_conditions"}:
            explains = False
        # A mixed answer can contain a correct conclusion and a residual error;
        # pure error vocabulary alone must not count as a correct conclusion.
        states_correct = (
            (has_k and (has_b or residual))
            or negative_claim
            or (self_correction and has_k)
            or slope_status == "correct"
        )
        if slope_status in {"incorrect", "insufficient_conditions"}:
            states_correct = has_b or negative_claim
            conclusion_level = "partial" if states_correct or slope_status == "insufficient_conditions" else "wrong"
        elif states_correct and not residual:
            conclusion_level = "correct"
        elif states_correct:
            conclusion_level = "partial"
        elif has_k or has_b:
            conclusion_level = "partial"
        else:
            conclusion_level = "wrong"
        slopes = [k for k, _ in equations(teacher_normalized)]
        is_transfer = len(slopes) >= 2 and len(set(slopes[:2])) == 1
        transfer = (
            is_transfer
            and states_correct
            and explains
            and any(marker in normalized for marker in ("一样", "相同", "同样"))
            and not residual
        )
        if slope_status == "incorrect":
            precision = "incorrect"
        elif slope_status == "insufficient_conditions":
            precision = "partial"
        elif residual and not (has_k and has_b):
            precision = "incorrect"
        elif explains and not residual:
            precision = "correct"
        else:
            precision = "partial" if has_k or has_b or residual else "incorrect"
        return DomainEvidence(
            states_correct_conclusion=states_correct,
            conclusion_level=conclusion_level,
            explains_reason_correctly=explains,
            shows_residual_misconception=residual,
            transfer_success=transfer,
            knowledge_precision=precision,
            slope_claim_status=slope_status,
        )

    def matches_text(self, text: str) -> bool:
        normalized = _compact(text)
        return any(
            marker in normalized
            for marker in ("k", "b", "斜率", "截距", "纵截距", "常数项", "倾斜")
        )

    def is_correction_evidence(self, text: str) -> bool:
        normalized = _compact(text)
        return any(
            marker in normalized
            for marker in (
                "b不影响斜率", "b只影响截距", "b改变的是位置", "k影响倾斜",
                "固定k改变b", "截距不影响斜率", "截距只决定上下位置",
                "常数项改变的是交点位置", "斜率不变", "倾斜程度不变",
            )
        )


class BinomialSquareSemanticEvaluator(MisconceptionSemanticEvaluator):
    """Semantic rules for (a+b)^2=a^2+b^2 and missing 2ab."""

    semantic_type = BINOMIAL_SQUARE
    prompt_guidance = "括号平方需要先理解两个相同括号相乘，交叉乘积会形成中间项。"
    knowledge_keywords = ("平方", "括号", "展开", "中间项", "交叉项", "2ab", "整式")

    def analyze(self, response: str, teacher_text: str) -> DomainEvidence:
        normalized = _compact(response)
        teacher_normalized = _compact(teacher_text)
        residual = _binomial_residual(normalized)
        has_middle_term = _has_middle_term(normalized)
        explains = _has_cross_term_explanation(normalized)
        states_correct = has_middle_term or explains
        if residual and not states_correct:
            conclusion_level = "wrong"
        elif residual or not states_correct:
            conclusion_level = "partial"
        elif explains:
            conclusion_level = "correct"
        else:
            conclusion_level = "partial"

        transfer_prompt = any(
            marker in teacher_normalized
            for marker in ("x+4", "2x+3", "x-5", "变式", "迁移", "负号")
        )
        transfer = (
            transfer_prompt
            and states_correct
            and explains
            and not residual
        )
        precision = "incorrect"
        if residual and not states_correct:
            precision = "incorrect"
        elif explains and not residual:
            precision = "correct"
        elif states_correct or residual:
            precision = "partial"
        return DomainEvidence(
            states_correct_conclusion=states_correct,
            conclusion_level=conclusion_level,
            explains_reason_correctly=explains,
            shows_residual_misconception=residual,
            transfer_success=transfer,
            knowledge_precision=precision,
        )

    def matches_text(self, text: str) -> bool:
        normalized = _compact(text)
        return any(marker in normalized for marker in self.knowledge_keywords)

    def is_correction_evidence(self, text: str) -> bool:
        normalized = _compact(text)
        return any(
            marker in normalized
            for marker in ("展开", "相乘", "交叉项", "中间项", "2ab", "乘法分配")
        )


_EVALUATORS: dict[str, MisconceptionSemanticEvaluator] = {
    LINEAR_KB: LinearKbSemanticEvaluator(),
    BINOMIAL_SQUARE: BinomialSquareSemanticEvaluator(),
}


def infer_semantic_type(item: Any) -> str:
    explicit = str(getattr(item, "semantic_type", "") or "").strip()
    if explicit in _EVALUATORS:
        return explicit
    text = " ".join(
        str(getattr(item, field, ""))
        for field in ("name", "concept", "description", "correction_condition")
    )
    if any(marker in text for marker in ("平方", "括号", "中间项", "交叉项", "完全平方")):
        return BINOMIAL_SQUARE
    return LINEAR_KB


def get_semantic_evaluator(semantic_type: str | None) -> MisconceptionSemanticEvaluator:
    return _EVALUATORS.get(semantic_type or LINEAR_KB, _EVALUATORS[LINEAR_KB])


def prompt_guidance(item: Any) -> str:
    return get_semantic_evaluator(infer_semantic_type(item)).prompt_guidance


def knowledge_keywords(item: Any) -> tuple[str, ...]:
    return get_semantic_evaluator(infer_semantic_type(item)).knowledge_keywords


def matches_misconception_text(item: Any, text: str) -> bool:
    return get_semantic_evaluator(infer_semantic_type(item)).matches_text(text)


def has_correction_evidence(item: Any, text: str) -> bool:
    return get_semantic_evaluator(infer_semantic_type(item)).is_correction_evidence(text)


def response_observes_misconception(item: Any, response: str) -> bool:
    return get_semantic_evaluator(infer_semantic_type(item)).analyze(response, "").shows_residual_misconception


def _compact(text: str) -> str:
    return re.sub(r"[\s，。！？、,:：；;]+", "", text.lower())


def _linear_residual(response: str, teacher_text: str) -> bool:
    masked = mask_equations(response)
    normalized = _compact(masked)
    context = teacher_text + "；" + response
    if _has_explicit_linear_self_correction(normalized):
        correction_tail = re.split(r"(?:现在|后来|如今)", masked, maxsplit=1)[-1]
        return _linear_positive_error(_compact(correction_tail)) or any(
            _linear_intercept_reference_error(clause, context)
            for clause in split_linear_clauses(correction_tail)
        )
    # Only the clause raising a hypothetical/quoted error is excluded. A later
    # first-person endorsement still expresses the student's misconception.
    asserted_clauses = [
        clause for clause in _linear_clauses(response)
        if not _is_hypothetical(clause) and not _denies_steepness(clause)
    ]
    if any(_linear_positive_error(clause) for clause in asserted_clauses):
        return True
    return any(
        _linear_intercept_reference_error(clause, context)
        # Numeric assertions keep punctuation and their own denial scope. A
        # denial elsewhere in the clause must not erase a later assertion.
        for clause in split_linear_clauses(masked)
    )


def _linear_intercept_reference_error(response: str, context: str) -> bool:
    """Resolve a spoken number to an intercept before reading its assertion."""
    if _is_hypothetical(response):
        return False
    lines = equations(context)
    if not lines:
        return False
    intercepts = {number(b) for _, b in lines}
    slopes = {abs(number(k)) for k, _ in lines}
    coefficients = {number(k) for k, _ in lines}
    for match in re.finditer(rf"(?<![\d./]){NUMBER}(?![\d./])", response):
        try:
            value = number(match[0])
        except (ValueError, ZeroDivisionError):
            continue
        # A bare value shared by k and b does not identify which role the
        # speaker means, even when the two occurrences are in different lines.
        if value not in intercepts or value in coefficients:
            continue
        tail = re.split(r"k|b|截距|常数项|〈公式〉|\d", response[match.end():], maxsplit=1)[0]
        # Naming a whole line by its intercept is only contradictory here when
        # all compared lines have equal steepness. Unequal slopes need arithmetic.
        line_claim = re.match(r"那条.{0,18}?(?:更陡|越陡|变陡)", tail)
        if line_claim:
            if (
                len(lines) >= 2 and len(slopes) == 1
                and _numeric_relation_is_asserted(response, match, line_claim)
            ):
                return True
            continue
        role_claim = re.match(
            r"(?:(?!k|b|斜率|\d|决定|影响|控制|改变).){0,16}?"
            r"(?:决定|影响|控制|改变)"
            r"(?:(?!k|b|\d|[，,]).){0,10}?(?:斜率|倾斜程度|陡峭程度)",
            tail,
        )
        if role_claim and _numeric_relation_is_asserted(response, match, role_claim):
            return True
        steepness_claim = re.match(
            r"^(?:(?!k|b|斜率|\d).){0,16}?"
            r"(?:越大|变大|增大|增加|影响|决定|控制|会让|让|使)"
            r"(?:(?!k|b|斜率).){0,14}?(?:更陡|越陡|变陡|会陡|倾斜)",
            tail,
        )
        if steepness_claim and _numeric_relation_is_asserted(response, match, steepness_claim):
            return True
    return False


def _numeric_relation_is_asserted(
    response: str, subject: re.Match[str], relation: re.Match[str]
) -> bool:
    """Read polarity/question markers only within this subject's assertion."""
    # Include a denial immediately before the number ("不是 3 决定斜率"),
    # not unrelated denials before an earlier comma or another numeric subject.
    before = re.split(r"[，,]|\d", response[:subject.start()])[-1]
    if re.search(r"(?:不是|并非|不(?:能)?(?:认为|觉得))$", before):
        return False
    span = relation[0]
    if re.search(
        r"(?:并非|而非|没有|没|未|不(?!但|仅|过))"
        r"(?:是|再|会|能|让|使|令|变得|那么|了){0,2}"
        r"(?:决定|影响|控制|改变|让|使|更陡|越陡|变陡|会陡|倾斜|斜率|陡峭程度)",
        span,
    ):
        return False
    if re.search(r"是否|是不是|会不会|能不能|对不对", span):
        return False
    following = response[subject.end() + relation.end():]
    if re.match(r"(?:吗|呢)(?:[?？]|$)", following):
        return False
    if re.match(r"[，,]?(?:对吗|正确吗|对不对|是吗|成立吗)", following):
        return False
    if re.match(r"[，,]?(?:(?:这个|该)(?:说法|结论|观点))?(?:是)?(?:不对|不正确|错误)", following):
        return False
    for quote in re.finditer(r'“[^”]*”|「[^」]*」|"[^"]*"', response):
        if quote.start() < subject.start() < quote.end() and not re.search(
            r"我(?:也)?(?:认为|觉得|同意)$", response[:quote.start()]
        ):
            return False
    # Preserve existing affirmative hedges such as "我觉得……越陡？";
    # a bare question mark without an assertion stance is not an endorsement.
    if re.match(r"[?？]", following) and not re.search(
        r"(?:我|总|还是).{0,6}(?:觉得|认为|感觉)", response[:subject.end()] + span
    ):
        return False
    return True


def _linear_k_role(response: str) -> bool:
    """Require a local relation between k/slope and steepness, not loose vocabulary."""
    patterns = (
        r"k.{0,18}(?:斜率|倾斜|陡|方向)",
        r"(?:斜率|倾斜程度|陡峭程度|陡不陡).{0,18}(?:由|看|取决于|决定于|受)?.{0,8}k",
        r"(?:k|斜率).{0,10}(?:不变|没变|相同|一样|都(?:是)?|保持不变)",
    )
    return any(re.search(pattern, response) for pattern in patterns)


def _linear_b_role(response: str) -> bool:
    """Require b/intercept to be locally tied to position, movement, or y-axis intercept."""
    position = r"(?:截距|纵截距|位置|上下|上移|向上|下移|上面|下面|上方|下方|平移|移动|挪|交点|y轴交点)"
    target = r"(?:b|截距|纵截距|常数项)"
    patterns = (
        rf"{target}.{{0,22}}{position}",
        rf"{position}.{{0,14}}(?:由|看|取决于|决定于|受).{{0,8}}b",
    )
    return any(re.search(pattern, response) for pattern in patterns)


def _linear_clauses(response: str) -> list[str]:
    """Use the same boundaries as claim checking before compacting punctuation."""
    return [_compact(clause) for clause in split_linear_clauses(mask_equations(response))]


# Denial of the b-to-steepness relation, in the forms students actually use.
# Strong negations ("并没有", "没有") deny on their own. Modal negations
# ("不会", "不能") are only denials when they carry a causative marker, so a
# genuine error such as "越大……也会陡一点，不过可能不会太陡吧" still counts as
# the misconception rather than as a correction.
_STEEPNESS_DENIAL = re.compile(
    r"(?:(?:并没有|并没有能|并不能够|并不能|没能|并不|没有)"
    r"|(?:不会|不能)(?:让|使|令))"
    r".{0,4}(?:更陡|越陡|变陡|会陡|更斜|越斜|变斜|影响(?:斜率|倾斜)|改变(?:斜率|倾斜))"
)
_HYPOTHETICAL = re.compile(
    r"(?:有同学|有人|有些同学).{0,6}(?:说|认为|觉得|问)|如果|假如|要是|是不是|对不对"
)


def _denies_steepness(text: str) -> bool:
    """True when the text denies that b changes steepness."""
    return bool(_STEEPNESS_DENIAL.search(text))


def _is_hypothetical(text: str) -> bool:
    """Text that raises the error without asserting it (attribution, question, condition)."""
    return bool(_HYPOTHETICAL.search(text))


def _linear_positive_error(response: str) -> bool:
    rhetorical_positive = re.search(
        r"(?:b|截距).{0,18}不是会.{0,12}(?:更陡|更斜|倾斜|斜率).{0,4}吗",
        response,
    )
    if rhetorical_positive:
        return True
    if _denies_steepness(response):
        return False
    if _linear_negative_claim_match(response):
        return False
    patterns = (
        r"b[^，,]{0,12}(?:越大|变大|增大|更大|增加)[^，,]{0,12}.{0,12}(?:更陡|越陡|变陡|会陡)",
        r"(?:b|截距).{0,20}(?:更陡|越陡|变陡|会陡|更斜|越斜|变斜|有点(?:更)?陡)",
        # The subject must sit next to its own verb, otherwise b is credited with
        # a clause about k ("b 改变上下位置，因为 k 控制陡峭程度").
        r"b.{0,6}(?:影响|决定|控制).{0,10}(?:陡|倾斜|斜率)",
        r"截距.{0,18}(?:越大|变大|更大|增加).{0,18}(?:陡|倾斜|斜率|更斜)",
        r"(?:觉得|感觉|认为|还是|仍然|可能|也许).{0,18}(?:b|往上移).{0,20}(?:陡|倾斜|斜率|影响)",
        r"往上移.{0,12}(?:会|有点|看起来).{0,12}(?:陡|倾斜)",
    )
    return any(re.search(pattern, response) for pattern in patterns)


def _has_explicit_linear_self_correction(response: str) -> bool:
    past_belief = re.search(
        r"(?:以前|之前|刚才|原来|曾经).{0,18}(?:以为|觉得|认为).{0,24}"
        r"(?:b|截距).{0,18}(?:越大|变大|更大|增加).{0,18}(陡|倾斜|斜率|更斜)",
        response,
    )
    if not past_belief or not re.search(r"(?:现在|后来|如今)", response):
        return False
    return bool(
        re.search(
            r"(?:现在|后来|如今).{0,30}(?:知道|明白|想明白|意识到)?.{0,18}"
            r"(?:不是(?:这样)?|不对|想错|不会更陡|不影响(?:倾斜|斜率)|只由k|只看k)",
            response,
        )
    )


def _linear_negative_claim(response: str) -> bool:
    """Detect a negated b-to-steepness claim, not generic uses of “不会”."""
    return _linear_negative_claim_match(response) is not None


def _linear_negative_claim_match(response: str) -> re.Match[str] | None:
    """Return the local negated b/steepness clause when one is present."""
    target = r"(?:b|截距|纵截距|常数项|改变b|b变大|b增大|上下移动|整体上下移动|平移)"
    negation = r"(?:不会|没有|并不|不(?!过))"
    steepness = r"(?:更陡|越陡|变陡|更斜|越斜|变斜|倾斜程度|斜率)"
    for clause in _linear_clauses(response):
        match = re.search(
            rf"{target}.{{0,18}}{negation}.{{0,8}}(?:改变|影响|让|使|变)?.{{0,8}}{steepness}",
            clause,
        ) or re.search(
            rf"{target}(?:(?!b|截距).){{0,22}}{steepness}(?:(?!b|截距).){{0,8}}{negation}.{{0,8}}(?:改变|影响|让|使|变)",
            clause,
        )
        if match:
            return match
    return None


def _binomial_residual(response: str) -> bool:
    correction = (
        any(marker in response for marker in ("以前", "原来", "曾经"))
        and any(marker in response for marker in ("现在", "后来", "知道"))
        and any(marker in response for marker in ("交叉项", "中间项", "2ab"))
    )
    if correction and not any(marker in response for marker in ("但是", "不过", "还是")):
        return False
    omission_correction = (
        any(marker in response for marker in ("以前", "原来", "曾经", "刚才"))
        and _has_positive_omission_claim(response)
        and _has_negative_omission_claim(response)
        and any(marker in response for marker in ("现在", "后来", "知道", "不对"))
    )
    if omission_correction and not any(marker in response for marker in ("但是", "不过", "还是")):
        return False
    shortcut = re.search(
        r"(?:x|a|b)(?:²|\^2)[+＋](?:\d+|(?:x|a|b)(?:²|\^2))(?=$|[^a-z0-9])",
        response,
    )
    return bool(
        (any(marker in response for marker in ("分别平方", "各自平方", "每一项平方"))
         and not any(marker in response for marker in ("不是", "不该", "还会", "交叉项", "中间项")))
        or any(marker in response for marker in ("没有中间项", "不需要中间项", "不需要2ab"))
        or _has_positive_omission_claim(response)
        or shortcut
    )


def _has_positive_omission_claim(response: str) -> bool:
    """Detect omitting cross terms while protecting explicit negation."""
    has_cross_term_reference = bool(
        any(marker in response for marker in ("交叉项", "中间项", "2ab", "ab"))
        or re.search(r"\d+(?:[·*])?[a-z]", response)
    )
    if not has_cross_term_reference or _has_negative_omission_claim(response):
        return False
    return bool(
        re.search(
            r"(?<!不)(?<!没)(?<!未)(?:可以|能够|能|应该能|应该可以|可)"
            r"(?:省略?|省掉|忽略|去掉)",
            response,
        )
        or any(marker in response for marker in ("不用写", "不用管", "不需要写"))
    )


def _has_negative_omission_claim(response: str) -> bool:
    return bool(
        re.search(
            r"(?:不能|不可以|不可|不该|不应|不应该|不必)(?:省略?|省掉|忽略|去掉)",
            response,
        )
        or any(marker in response for marker in ("必须保留", "要保留", "不能去掉", "不应该忽略"))
    )


def _has_middle_term(response: str) -> bool:
    return bool(
        re.search(r"2ab", response)
        or re.search(r"[+-]\d+[a-z](?:[²^]2)?", response)
        or re.search(r"(?:中间项|交叉项).{0,20}(?:有|是|出现|得到)", response)
    )


def _has_cross_term_explanation(response: str) -> bool:
    return bool(
        any(marker in response for marker in ("交叉项", "中间项来自", "两个相同括号相乘"))
        or re.search(r"\([^)]*\)\([^)]*\).{0,40}(展开|相乘|乘法)", response)
        or re.search(r"(?:\d+[a-z]|ab).{0,12}(?:\+|和).{0,12}(?:\d+[a-z]|ab).{0,20}(?:所以|得到|中间)", response)
        or re.search(r"交叉相乘.{0,20}(?:出现|各出现|两次).{0,20}(?:所以|得到|合起来)", response)
    )
