from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re


class ClassroomAct(StrEnum):
    SUBJECT_CONTENT = "subject_content"
    GREETING = "greeting"
    FEEDBACK = "feedback"
    ENCOURAGEMENT = "encouragement"
    ORGANIZATION = "organization"
    TRANSITION = "transition"
    CLOSURE = "closure"
    ELABORATION_REQUEST = "elaboration_request"
    UNDERSTANDING_CHECK = "understanding_check"
    CORRECTIVE_FEEDBACK = "corrective_feedback"
    ACKNOWLEDGEMENT = "acknowledgement"
    CONTINUATION = "continuation"
    CONTEXTUAL_REFERENCE = "contextual_reference"
    OFF_TOPIC = "off_topic"


@dataclass(frozen=True)
class ClassroomDialogueIntent:
    normalized: str
    act: ClassroomAct
    has_subject_content: bool

    @property
    def is_classroom_interaction(self) -> bool:
        return self.act not in {ClassroomAct.SUBJECT_CONTENT, ClassroomAct.OFF_TOPIC}

    @property
    def off_topic(self) -> bool:
        return self.act is ClassroomAct.OFF_TOPIC


_SUBJECT_MARKERS = (
    "一次函数", "函数", "直线", "图像", "斜率", "倾斜", "陡", "截距",
    "交点", "平移", "常数项", "公式", "平方", "括号", "展开", "中间项",
    "交叉项", "计算", "线性代数", "仿射变换", "矩阵", "特征值", "微积分",
    "导数", "微分方程", "y=", "x", "k", "b",
)


def analyze_classroom_dialogue(text: str) -> ClassroomDialogueIntent:
    normalized = re.sub(r"[\s，。！？、,:：；;]+", "", text.lower())
    has_subject_content = any(marker in normalized for marker in _SUBJECT_MARKERS)

    direct_answer_cue = any(
        marker in normalized for marker in ("答案是", "结论是", "直接告诉你", "正确结果是")
    )
    if any(marker in normalized for marker in ("下课", "今天先到这里", "这节课先到这里", "老师再见", "课后再练习")):
        act = ClassroomAct.CLOSURE
    elif any(marker in normalized for marker in ("同学你好", "你好", "开始上课", "准备好了吗", "准备好没有")):
        act = ClassroomAct.GREETING
    elif not direct_answer_cue and any(
        marker in normalized
        for marker in (
            "很好", "不错", "回答得", "回答的很好", "回答正确", "答对了",
            "说得对", "第一步是对的", "就是这个意思", "对就是这样", "有进步",
            "前面正确",
        )
    ):
        act = ClassroomAct.FEEDBACK
    elif any(
        marker in normalized
        for marker in ("这里不太对", "不太对", "差一点", "再检查一下", "重新检查", "后面再检查")
    ):
        act = ClassroomAct.CORRECTIVE_FEEDBACK
    elif any(
        marker in normalized
        for marker in (
            "别紧张", "不要紧张", "没关系", "慢慢想", "大胆说", "再试一次",
            "再想一想", "再想想", "接近答案", "加油",
        )
    ):
        act = ClassroomAct.ENCOURAGEMENT
    elif any(
        marker in normalized
        for marker in (
            "请看黑板", "看黑板", "草稿纸", "给你一分钟", "先别急", "请坐",
            "注意听", "举手", "先写下来", "先画下来",
        )
    ):
        act = ClassroomAct.ORGANIZATION
    elif any(
        marker in normalized
        for marker in (
            "我们继续", "请继续", "继续学习", "下一题", "换一道题", "换一题",
            "回到刚才", "先回顾", "接着看", "下面来看",
        )
    ) or normalized in {"继续", "继续吧"}:
        act = ClassroomAct.TRANSITION
    elif any(
        marker in normalized
        for marker in (
            "听懂了吗", "听明白了吗", "明白了吗", "懂了吗", "理解了吗",
            "能复述吗", "能说一遍吗",
        )
    ):
        act = ClassroomAct.UNDERSTANDING_CHECK
    elif any(
        marker in normalized
        for marker in (
            "再说一遍", "说完整一点", "说清楚一点", "补充完整", "再解释",
            "再说说", "说具体", "说明一下", "用自己的话", "理由",
        )
    ):
        act = ClassroomAct.ELABORATION_REQUEST
    elif normalized in {"然后呢", "接着呢"}:
        act = ClassroomAct.CONTINUATION
    elif re.fullmatch(r"(?:那|这个|它).{0,12}呢\??", normalized):
        act = ClassroomAct.CONTEXTUAL_REFERENCE
    elif normalized in {"嗯", "好的", "好", "可以", "知道了", "行"}:
        act = ClassroomAct.ACKNOWLEDGEMENT
    elif has_subject_content:
        act = ClassroomAct.SUBJECT_CONTENT
    else:
        act = ClassroomAct.OFF_TOPIC

    return ClassroomDialogueIntent(
        normalized=normalized,
        act=act,
        has_subject_content=has_subject_content,
    )
