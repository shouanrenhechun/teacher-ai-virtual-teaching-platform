from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re


class ClassroomAct(StrEnum):
    SUBJECT_CONTENT = "subject_content"
    DIRECT_ANSWER = "direct_answer"
    EXAMPLE = "example"
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


_ACT_PRIORITY = (
    ClassroomAct.DIRECT_ANSWER,
    ClassroomAct.CORRECTIVE_FEEDBACK,
    ClassroomAct.ELABORATION_REQUEST,
    ClassroomAct.EXAMPLE,
    ClassroomAct.CONTEXTUAL_REFERENCE,
    ClassroomAct.UNDERSTANDING_CHECK,
    ClassroomAct.FEEDBACK,
    ClassroomAct.ENCOURAGEMENT,
    ClassroomAct.ORGANIZATION,
    ClassroomAct.CLOSURE,
    ClassroomAct.TRANSITION,
    ClassroomAct.GREETING,
    ClassroomAct.CONTINUATION,
    ClassroomAct.ACKNOWLEDGEMENT,
    ClassroomAct.SUBJECT_CONTENT,
    ClassroomAct.OFF_TOPIC,
)


@dataclass(frozen=True)
class ClassroomDialogueIntent:
    normalized: str
    primary_act: ClassroomAct
    secondary_acts: tuple[ClassroomAct, ...]
    has_subject_content: bool
    confidence: float = 1.0
    classification_source: str = "rules"

    @property
    def act(self) -> ClassroomAct:
        """Backward-compatible alias for callers that only need the primary act."""
        return self.primary_act

    @property
    def acts(self) -> tuple[ClassroomAct, ...]:
        return (self.primary_act, *self.secondary_acts)

    def has(self, act: ClassroomAct) -> bool:
        return act in self.acts

    @property
    def is_classroom_interaction(self) -> bool:
        return self.primary_act not in {ClassroomAct.SUBJECT_CONTENT, ClassroomAct.OFF_TOPIC}

    @property
    def off_topic(self) -> bool:
        return self.primary_act is ClassroomAct.OFF_TOPIC


_SUBJECT_MARKERS = (
    "一次函数", "函数", "直线", "图像", "斜率", "倾斜", "陡", "截距",
    "交点", "平移", "常数项", "公式", "平方", "括号", "展开", "中间项",
    "交叉项", "计算", "线性代数", "仿射变换", "矩阵", "特征值", "微积分",
    "导数", "微分方程", "等于", "y=", "x", "k", "b",
)

# These are compositional semantic features, not sentence templates.  A new
# utterance is scored from combinations such as action + object or evaluation
# + student work, so unseen wording does not need a new full-sentence rule.
_OFF_TOPIC_DOMAINS = (
    "天气", "下雨", "温度", "篮球", "足球", "球队", "比赛", "游戏", "电影",
    "歌曲", "唱歌", "笑话", "故事", "旅游", "景点", "奶茶", "吃饭", "午饭",
    "晚饭", "做饭", "购物", "多少钱", "新闻", "宠物", "小猫", "小狗", "暑假",
    "周末去哪", "住在哪里", "几号", "生日", "睡得", "睡觉", "中午",
    "吃什么", "这首歌", "音乐",
)


def _has_any(text: str, roots: tuple[str, ...]) -> bool:
    return any(root in text for root in roots)


def _semantic_act_scores(text: str) -> dict[ClassroomAct, float]:
    """Score unseen classroom wording from reusable semantic feature groups."""
    scores: dict[ClassroomAct, float] = {}

    def add(act: ClassroomAct, score: float) -> None:
        scores[act] = max(scores.get(act, 0.0), score)

    question_shape = _has_any(text, ("吗", "没有", "是否", "哪里", "怎么", "呢"))

    if _has_any(text, ("同学", "上课")) or (
        _has_any(text, ("开始", "准备")) and len(text) <= 12
    ):
        add(ClassroomAct.GREETING, 0.86)

    positive = _has_any(
        text, ("漂亮", "到位", "正确", "清楚", "没问题", "正是", "可以", "进步")
    )
    student_work = _has_any(
        text,
        ("回答", "解答", "作答", "答得", "讲", "说", "结论", "思路", "方法", "步骤", "这次", "干得"),
    )
    if positive and student_work:
        add(ClassroomAct.FEEDBACK, 0.84)
    elif student_work and _has_any(text, ("得", "很", "真", "相当", "挺")):
        add(ClassroomAct.FEEDBACK, 0.68)

    support = _has_any(
        text, ("慌", "怕", "紧张", "琢磨", "尝试", "试试", "稳", "想好", "灰心")
    )
    supportive_shape = _has_any(text, ("不用", "不要", "别", "再", "先", "慢慢"))
    if support and supportive_shape:
        add(ClassroomAct.ENCOURAGEMENT, 0.82)

    classroom_object = _has_any(
        text, ("书", "屏幕", "黑板", "笔", "本子", "练习册", "草稿", "座位", "声音")
    )
    classroom_command = _has_any(
        text, ("翻", "看", "拿", "记", "写", "画", "打开", "关", "坐", "安静")
    )
    generic_classroom_command = bool(
        re.search(r"^(?:请)?把.{1,12}(?:打开|拿出|放|写|记|画|翻)", text)
        or re.search(r"^请(?:打开|拿出|写|记|画|翻|看)", text)
    )
    if (
        (classroom_object and classroom_command)
        or generic_classroom_command
        or _has_any(text, ("保持安静", "声音大"))
    ):
        add(ClassroomAct.ORGANIZATION, 0.88)

    if _has_any(
        text, ("接着", "后面", "刚才", "下一个", "下一道", "往后", "跳过", "转到", "继续")
    ):
        add(ClassroomAct.TRANSITION, 0.8)

    if _has_any(text, ("讲到这", "课结束", "下次", "休息", "先这样", "到这儿", "到这里")):
        add(ClassroomAct.CLOSURE, 0.86)

    elaboration_content = _has_any(text, ("详细", "多说", "过程", "理由", "依据", "具体", "展开"))
    elaboration_request = question_shape or text.startswith(("请", "能")) or _has_any(
        text, ("讲一下", "说一点", "说说", "补充")
    ) or (text.startswith("再") and elaboration_content)
    if elaboration_content and elaboration_request:
        add(ClassroomAct.ELABORATION_REQUEST, 0.88)

    understanding_content = _has_any(
        text, ("明白", "理解", "会做", "跟得上", "清楚", "学会", "做一个", "掌握")
    )
    clarity_describes_expression = _has_any(text, ("说清楚", "讲清楚", "写清楚"))
    if understanding_content and question_shape and not clarity_describes_expression:
        add(ClassroomAct.UNDERSTANDING_CHECK, 0.9)

    if _has_any(text, ("不对", "有错", "错了", "核对", "需要改", "得改", "有点偏", "偏了")):
        add(ClassroomAct.CORRECTIVE_FEEDBACK, 0.9)

    if len(text) <= 5 and _has_any(text, ("嗯", "好", "行", "明白", "收到", "知道")):
        add(ClassroomAct.ACKNOWLEDGEMENT, 0.78)

    contextual_subject = _has_any(
        text, ("那个", "这个", "前一个", "上一个", "刚刚", "刚才", "接下来", "那又")
    )
    contextual_request = _has_any(text, ("呢", "怎么样", "怎么理解", "怎么说", "怎么办"))
    if contextual_subject and contextual_request:
        add(ClassroomAct.CONTEXTUAL_REFERENCE, 0.84)

    if _has_any(
        text,
        ("这道题", "题目", "解法", "知识点", "概念", "作业", "练习", "步骤", "答案"),
    ):
        add(ClassroomAct.SUBJECT_CONTENT, 0.72)

    return scores


def _matches(text: str, *patterns: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def analyze_classroom_dialogue(
    text: str,
    *,
    conversation_history: tuple[tuple[str, str], ...] = (),
    assume_classroom_context: bool = True,
) -> ClassroomDialogueIntent:
    # Keep operators but remove punctuation so both spoken and typed variants align.
    normalized = re.sub(r"[\s，。！？、,.!?,:：；;‘’“”\"']+", "", text.lower())
    found: set[ClassroomAct] = set()
    semantic_scores = _semantic_act_scores(normalized)
    if conversation_history and len(normalized) <= 10 and _has_any(
        normalized, ("呢", "怎么样", "怎么说", "怎么办", "为什么")
    ):
        semantic_scores[ClassroomAct.CONTEXTUAL_REFERENCE] = max(
            semantic_scores.get(ClassroomAct.CONTEXTUAL_REFERENCE, 0.0), 0.7
        )

    direct_answer = _matches(
        normalized,
        r"(?:答案|结论|结果|正确答案|正确结果)(?:是|为)",
        r"(?:直接|就)(?:写|填|告诉)",
        r"记住(?:是|这个|这个结果)?",
        r"这里应该是[+\-]?\d",
    )
    if direct_answer:
        found.add(ClassroomAct.DIRECT_ANSWER)

    if _matches(
        normalized,
        r"(?:听|看|弄|搞)?明白了吗", r"听懂了吗", r"有没有听懂", r"理解了吗",
        r"学会了吗", r"会了吗", r"清楚了吗", r"跟上了吗", r"现在知道了吗",
        r"能不能复述", r"能不能再做一题", r"能说一遍吗", r"懂了吗",
    ):
        found.add(ClassroomAct.UNDERSTANDING_CHECK)

    if _matches(
        normalized,
        r"(?<!好了)(?:再|重新)(?:讲|说|解释)", r"(?:展开|具体)(?:讲|说)",
        r"为什么这么想", r"依据是什么", r"补充", r"还有吗", r"请接着说",
        r"刚才.{0,12}是什么意思", r"说(?:得)?(?:完整|清楚)一点", r"用自己的话",
        r"继续说理由", r"解释(?:一下)?为什么", r"说说理由", r"说明一下",
    ):
        found.add(ClassroomAct.ELABORATION_REQUEST)

    if _matches(
        normalized,
        r"不太对", r"(?:这|哪|后面)?一步错", r"错了", r"再检查", r"重新检查",
        r"你再看看", r"有问题", r"有偏差", r"不是这样", r"你确定吗",
        r"差一点", r"后面再检查", r"不影响斜率", r"不改变斜率",
        r"只改变截距", r"改变的是(?:位置|截距)",
    ):
        found.add(ClassroomAct.CORRECTIVE_FEEDBACK)

    if _matches(normalized, r"举(?:个|一个)?例", r"换个例子", r"(?:比较|对比)", r"画两条"):
        found.add(ClassroomAct.EXAMPLE)

    if not direct_answer and _matches(
        normalized,
        r"(?:很好|非常好|真好)", r"真棒", r"不错", r"答得不错", r"说得很好",
        r"没错", r"完全正确", r"回答(?:得)?正确", r"答对", r"说得对", r"思路对",
        r"方法正确", r"这一步没问题", r"第一步是对", r"说对了", r"就是这样",
        r"就是这个意思", r"有进步", r"前面正确", r"对就是这样",
    ):
        found.add(ClassroomAct.FEEDBACK)

    if _matches(
        normalized,
        r"别(?:紧张|着急)", r"不要怕错", r"没关系", r"慢慢(?:想|来)", r"大胆",
        r"再试", r"试试看", r"你可以的", r"再努力", r"接近答案", r"继续思考",
        r"加油", r"再想",
    ):
        found.add(ClassroomAct.ENCOURAGEMENT)

    if _matches(
        normalized,
        r"(?:请)?看(?:黑板|这里)", r"翻到", r"草稿纸", r"(?:课|练习|作业)本",
        r"给你.{0,4}分钟", r"先别急", r"请坐", r"注意听", r"举手",
        r"(?:写|画|记)下来", r"拿出", r"声音大一点", r"认真观察", r"安静",
        r"停一下", r"打开课本", r"打开窗户", r"关门", r"擦黑板", r"去办公室",
    ):
        found.add(ClassroomAct.ORGANIZATION)

    if _matches(
        normalized,
        r"我们继续", r"请继续", r"继续学习", r"继续刚才", r"下一(?:题|问|步)",
        r"往下看", r"换(?:一?道?题|个例子)", r"回到刚才", r"上一个", r"先回顾",
        r"接着看", r"下面来看", r"进入下一步", r"放一放", r"后面讨论",
    ) or normalized in {"继续", "继续吧"}:
        found.add(ClassroomAct.TRANSITION)

    if _matches(
        normalized,
        r"(?:今天|这节课).{0,8}(?:到这里|结束)", r"下课", r"下次再讲",
        r"课后", r"休息", r"再见",
    ):
        found.add(ClassroomAct.CLOSURE)

    if _matches(
        normalized,
        r"早上好", r"大家好", r"同学们好", r"同学你好", r"你好", r"上课吧", r"开始上课",
        r"可以开始了吗", r"准备(?:好|开始)",
    ):
        found.add(ClassroomAct.GREETING)

    if normalized in {"然后呢", "接着呢", "接下来呢", "还有呢", "怎么办"}:
        found.add(ClassroomAct.CONTINUATION)

    if _matches(
        normalized,
        r"(?:那|这个|它|上一个|第二个|刚才那个).{0,12}呢$",
        r"这个为什么$",
    ):
        found.add(ClassroomAct.CONTEXTUAL_REFERENCE)

    if normalized in {"嗯", "好的", "好", "可以", "知道了", "行"}:
        found.add(ClassroomAct.ACKNOWLEDGEMENT)

    lexical_subject = any(marker in normalized for marker in _SUBJECT_MARKERS)
    symbolic_math = bool(
        re.search(r"(?:[a-z]\d*|\d+)[=+\-×÷*/^²](?:[a-z]|\d)", normalized)
        or re.search(r"[=+\-×÷*/^²](?:[a-z]|\d)", normalized)
    )
    numeric_instruction = direct_answer and bool(re.search(r"[+\-]?\d+(?:\.\d+)?", normalized))
    has_subject_content = lexical_subject or symbolic_math or numeric_instruction
    if has_subject_content:
        found.add(ClassroomAct.SUBJECT_CONTENT)

    rule_found = set(found)
    semantic_found = {act for act, score in semantic_scores.items() if score >= 0.58}
    strong_off_topic_signal = _has_any(normalized, _OFF_TOPIC_DOMAINS)
    has_semantic_classroom_anchor = (
        semantic_scores.get(ClassroomAct.SUBJECT_CONTENT, 0.0) >= 0.65
    )

    if strong_off_topic_signal and not rule_found and not has_semantic_classroom_anchor:
        found = {ClassroomAct.OFF_TOPIC}
        classification_source = "off_topic_signal"
        confidence = 0.92
    else:
        found.update(semantic_found)
        if not found:
            ambiguous_short_turn = (
                assume_classroom_context and len(normalized) <= 4
            ) or (
                bool(conversation_history) and len(normalized) <= 8
            )
            if ambiguous_short_turn:
                # Topic drift needs positive evidence. An unmatched turn inside a
                # lesson stays neutral instead of triggering a disruptive redirect.
                found.add(ClassroomAct.ACKNOWLEDGEMENT)
                classification_source = "classroom_context_fallback"
                confidence = 0.4 if conversation_history else 0.32
            else:
                found.add(ClassroomAct.OFF_TOPIC)
                classification_source = "open_set_rejection"
                confidence = 0.68
        elif semantic_found and rule_found:
            classification_source = "rules+semantic"
            confidence = max(semantic_scores[act] for act in semantic_found)
        elif semantic_found:
            classification_source = "semantic"
            confidence = max(semantic_scores[act] for act in semantic_found)
        else:
            classification_source = "rules"
            confidence = 1.0

    ordered = tuple(act for act in _ACT_PRIORITY if act in found)
    return ClassroomDialogueIntent(
        normalized=normalized,
        primary_act=ordered[0],
        secondary_acts=ordered[1:],
        has_subject_content=has_subject_content,
        confidence=round(confidence, 2),
        classification_source=classification_source,
    )
