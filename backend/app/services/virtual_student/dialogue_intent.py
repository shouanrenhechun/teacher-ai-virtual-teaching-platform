from __future__ import annotations

from dataclasses import dataclass
import re

from .classroom_intent import ClassroomAct, analyze_classroom_dialogue


_OUT_OF_SCOPE_MARKERS = (
    "线性代数",
    "仿射变换",
    "矩阵",
    "特征值",
    "微积分",
    "导数",
    "微分方程",
)
def compact_dialogue_text(text: str) -> str:
    return re.sub(r"[\s，。！？、,:：；;]+", "", text.lower())


@dataclass(frozen=True)
class LinearDialogueIntent:
    normalized: str
    classroom_act: ClassroomAct
    mentions_slope: bool
    mentions_intercept: bool
    mentions_position: bool
    mentions_steepness: bool
    fixed_slope: bool
    changes_intercept: bool
    denies_slope_change: bool
    asks_reason: bool
    asks_understanding: bool
    contextual_follow_up: bool
    is_question: bool
    equations: tuple[tuple[str, str], ...]
    same_slope_equations: bool
    out_of_scope: bool
    off_topic: bool

    @property
    def correction_statement(self) -> bool:
        return (
            self.mentions_intercept
            and self.mentions_position
            and self.denies_slope_change
            and not self.is_question
        )

    @property
    def compares_intercept_change(self) -> bool:
        return (
            self.same_slope_equations
            or (self.fixed_slope and self.changes_intercept)
            or (
                self.mentions_slope
                and self.mentions_intercept
                and any(marker in self.normalized for marker in ("比较", "不同", "关系"))
            )
        )


def analyze_linear_dialogue_intent(text: str) -> LinearDialogueIntent:
    normalized = compact_dialogue_text(text)
    classroom = analyze_classroom_dialogue(text)
    asks_understanding = classroom.act is ClassroomAct.UNDERSTANDING_CHECK
    asks_reason = classroom.act is ClassroomAct.ELABORATION_REQUEST or any(
        marker in normalized for marker in ("为什么", "理由", "解释", "再说说", "说具体", "说明一下")
    )
    contextual_follow_up = classroom.act is ClassroomAct.CONTEXTUAL_REFERENCE
    mentions_slope = any(
        marker in normalized for marker in ("k", "斜率", "倾斜", "陡")
    )
    mentions_intercept = any(
        marker in normalized for marker in ("b", "截距", "纵截距", "常数项")
    )
    mentions_position = any(
        marker in normalized
        for marker in ("位置", "上下", "上移", "下移", "平移", "交点", "截距", "常数项")
    )
    mentions_steepness = any(
        marker in normalized for marker in ("斜率", "倾斜", "陡", "斜")
    )
    fixed_slope = any(
        marker in normalized
        for marker in (
            "固定k",
            "k不变",
            "k相同",
            "k都",
            "斜率不变",
            "斜率相同",
            "斜率保持",
            "倾斜程度不变",
            "一样陡",
            "同样陡",
        )
    )
    changes_intercept = mentions_intercept and any(
        marker in normalized
        for marker in (
            "改变", "变化", "变大", "越大", "增大", "增加", "改成", "变成",
            "不同", "从", "只改变",
        )
    )
    denies_slope_change = any(
        marker in normalized
        for marker in (
            "不影响斜率",
            "不改变斜率",
            "斜率不变",
            "倾斜程度不变",
            "不会更陡",
            "不会变陡",
            "一样陡",
            "同样陡",
            "斜率相同",
        )
    )
    equations = tuple(
        (match.group(1), match.group(2) or "0")
        for match in re.finditer(
            r"y=([+-]?\d+(?:\.\d+)?)x(?:([+-]\d+(?:\.\d+)?))?",
            normalized,
        )
    )
    same_slope_equations = len(equations) >= 2 and len({item[0] for item in equations}) == 1
    if same_slope_equations:
        fixed_slope = True
        changes_intercept = len({item[1] for item in equations}) > 1
    out_of_scope = any(marker in normalized for marker in _OUT_OF_SCOPE_MARKERS)
    off_topic = classroom.off_topic and not out_of_scope
    is_question = "?" in text or "？" in text or any(
        marker in normalized for marker in ("吗", "什么", "为什么", "如何", "怎么", "哪个", "能否")
    )
    return LinearDialogueIntent(
        normalized=normalized,
        classroom_act=classroom.act,
        mentions_slope=mentions_slope,
        mentions_intercept=mentions_intercept,
        mentions_position=mentions_position,
        mentions_steepness=mentions_steepness,
        fixed_slope=fixed_slope,
        changes_intercept=changes_intercept,
        denies_slope_change=denies_slope_change,
        asks_reason=asks_reason,
        asks_understanding=asks_understanding,
        contextual_follow_up=contextual_follow_up,
        is_question=is_question,
        equations=equations,
        same_slope_equations=same_slope_equations,
        out_of_scope=out_of_scope,
        off_topic=off_topic,
    )
