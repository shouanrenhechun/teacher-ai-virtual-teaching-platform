from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .dialogue_intent import analyze_linear_dialogue_intent


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
        response_intent = analyze_linear_dialogue_intent(response)
        has_k = (
            "k" in normalized
            and response_intent.mentions_slope
            and any(marker in normalized for marker in ("斜率", "倾斜", "陡", "方向"))
        ) or any(
            marker in normalized
            for marker in (
                "斜率不变", "斜率保持不变", "斜率相同", "斜率都是",
                "斜率由k", "斜率看k",
            )
        )
        has_b = response_intent.mentions_intercept and any(
            marker in normalized
            for marker in (
                "截距", "位置", "上下", "上移", "向上", "下移", "平移",
                "上面", "下面", "上方", "下方", "移动", "挪", "交点", "常数项",
                "陡", "倾斜", "斜率",
            )
        )
        residual = _linear_residual(normalized, teacher_normalized)
        negative_claim = _linear_negative_claim(normalized)
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
            )
        )
        # A mixed answer can contain a correct conclusion and a residual error;
        # pure error vocabulary alone must not count as a correct conclusion.
        states_correct = (has_k and (has_b or residual)) or (negative_claim and has_b)
        if states_correct and not residual:
            conclusion_level = "correct"
        elif states_correct:
            conclusion_level = "partial"
        elif has_k or has_b:
            conclusion_level = "partial"
        else:
            conclusion_level = "wrong"
        slopes = re.findall(r"y=([+-]?\d+)x", teacher_normalized)
        is_transfer = len(slopes) >= 2 and len(set(slopes[:2])) == 1
        transfer = (
            is_transfer
            and states_correct
            and explains
            and any(marker in normalized for marker in ("一样", "相同", "同样"))
            and not residual
        )
        if residual and not (has_k and has_b):
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
    if _has_explicit_linear_self_correction(response):
        correction_tail = re.split(r"(?:现在|后来|如今)", response, maxsplit=1)[-1]
        return _linear_positive_error(correction_tail)
    if any(_linear_positive_error(clause) for clause in _linear_clauses(response)):
        return True
    if "2和3" in teacher_text or "y=2x+3" in teacher_text:
        return bool(re.search(r"(?:3|它).{0,16}(越陡|更陡|变陡|会陡)", response))
    return False


def _linear_clauses(response: str) -> list[str]:
    """Keep contrastive clauses separate so negation cannot cross a turn."""
    return [clause for clause in re.split(r"(?:不过|但是|然而|可是|但)", response) if clause]


def _linear_positive_error(response: str) -> bool:
    rhetorical_positive = re.search(
        r"(?:b|截距).{0,18}不是会.{0,12}(?:更陡|更斜|倾斜|斜率).{0,4}吗",
        response,
    )
    if rhetorical_positive:
        return True
    if _linear_negative_claim_match(response):
        return False
    patterns = (
        r"b.{0,18}(越大|变大|更大|增加).{0,18}(陡|倾斜|斜率)",
        r"(?:b|截距|[+＋]\d+).{0,20}(?:更陡|越陡|变陡|会陡|更斜|越斜|变斜|有点(?:更)?陡)",
        r"(?:b|[+＋]\d+).{0,20}影响.{0,12}(?:陡|倾斜|斜率)",
        r"截距.{0,18}(越大|变大|更大|增加).{0,18}(陡|倾斜|斜率|更斜)",
        r"(觉得|感觉|认为|还是|仍然|可能|也许).{0,18}(?:b|往上移|[+＋]\d+).{0,20}(?:陡|倾斜|斜率|影响)",
        r"往上移.{0,12}(会|有点|看起来).{0,12}(陡|倾斜)",
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
