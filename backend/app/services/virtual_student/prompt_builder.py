from __future__ import annotations

from .engine import VirtualStudentEngine
from .semantic import infer_semantic_type, prompt_guidance


def misconception_prompt_mode(status: str, corrected: bool = False) -> str:
    if corrected or status == "corrected":
        return "corrected_history"
    return {
        "active": "strong_misconception",
        "weakening": "conflicted",
        "provisional": "mostly_correct_unstable",
    }.get(status, "strong_misconception")


def prompt_recent_history_count(
    conversation_history: list[tuple[str, str]] | None,
    teacher_text: str,
) -> int:
    return sum(
        1
        for speaker, content in (conversation_history or [])[-8:]
        if speaker in {"teacher", "student"}
        and content.strip()
        and content.strip() != teacher_text.strip()
    )


def _misconception_prompt_text(item: object) -> str:
    status = str(getattr(item, "status", "active"))
    corrected = bool(getattr(item, "corrected", False))
    name = str(getattr(item, "name", "当前认知错误"))
    strength = float(getattr(item, "strength", 0.0))
    mode = misconception_prompt_mode(status, corrected)
    guidance = prompt_guidance(item)

    if mode == "strong_misconception":
        wording = (
            f"你目前比较确信：{name}。除非教师提供有意义的解释或证据，"
            "否则不要无缘无故放弃这一看法。"
        )
    elif mode == "conflicted":
        wording = (
            f"你开始怀疑原先“{name}”的想法，但还没有完全接受正确关系。"
            "回答时可以表现出犹豫或认知冲突，但不要为了维持旧设定而强行重复错误。"
        )
    elif mode == "mostly_correct_unstable":
        wording = (
            f"你目前倾向于认为“{guidance}”原先“{name}”的想法已经明显减弱。"
            "除非当前问题暴露出你仍未真正理解，否则不要主动为了维持角色而重新加入旧错误；"
            "如果理解还不稳定，可以自然地犹豫或保留疑问。"
        )
    else:
        wording = f"你以前曾有过“{name}”的错误理解，但经过前面的教学，你现在已经纠正了这一理解。"

    return (
        f"{name}（类型={infer_semantic_type(item)}，强度={strength:.2f}，状态={status}，Prompt模式={mode}）\n"
        f"{wording}"
    )


class PromptBuilder:
    """Build a complete, inspectable prompt from the current engine state."""

    def build(
        self,
        engine: VirtualStudentEngine,
        teacher_text: str,
        conversation_history: list[tuple[str, str]] | None = None,
    ) -> str:
        snapshot = engine.snapshot()
        boundary = engine.knowledge_boundary()
        knowledge = "；".join(
            f"{item.knowledge_point}={item.mastery:.2f}"
            for item in snapshot.knowledge_states
        ) or "暂无知识状态记录"
        current_misconceptions = [
            item for item in snapshot.misconceptions if not item.corrected
        ]
        historical_misconceptions = [
            item for item in snapshot.misconceptions if item.corrected
        ]
        misconceptions = "\n".join(
            _misconception_prompt_text(item) for item in current_misconceptions
        ) or "当前没有未纠正的固定认知错误"
        if historical_misconceptions:
            misconceptions += "\n历史错误（不可作为当前信念）：\n" + "\n".join(
                _misconception_prompt_text(item) for item in historical_misconceptions
            )
        classroom = snapshot.classroom_state
        recent_history = (conversation_history or [])[-8:]
        history_text = "\n".join(
            f"{'Teacher' if speaker == 'teacher' else 'Student'}: {content.strip()}"
            for speaker, content in recent_history
            if content.strip() and content.strip() != teacher_text.strip()
        ) or "（暂无更早对话）"

        return f"""你是教学实训中的{engine.profile.grade}学生{engine.profile.name}。

【学生性格】
{engine.profile.personality_description}

【表达与学习风格】
自信表达：{engine.profile.confidence_style}
回答风格：{engine.profile.response_style}
猜测倾向：{engine.profile.guessing_tendency}
确认倾向：{engine.profile.confirmation_seeking}
回答长度：{engine.profile.verbosity}
纠正方式：{engine.profile.correction_style}

【当前知识状态】
{knowledge}

【当前未纠正的固定认知错误】
{misconceptions}

【当前课堂状态】
understanding={classroom.understanding:.2f}
confusion={classroom.confusion:.2f}
engagement={classroom.engagement:.2f}
confidence={classroom.confidence:.2f}

【可使用的知识边界】
已掌握：{"、".join(boundary["mastered"]) or "暂无"}
部分掌握：{"、".join(boundary["partial"]) or "暂无"}
尚未掌握，不得自信地完整解释：{"、".join(boundary["not_ready"]) or "暂无"}

【行为约束】
- 使用不超过{engine.profile.grade}水平的数学语言，回答自然、简短。
- 表达上的犹豫不等于概念错误；如果知识关系完整，可以用“应该”“我觉得”“吧”等谨慎口吻给出正确解释。
- 不得突然获得尚未掌握的知识；可以犹豫、猜测或请求提示。
- active 阶段保持较稳定的错误；weakening/provisional 阶段允许正确理解逐步形成，不要为了角色设定强行重复旧错误；corrected 阶段不要把历史错误当作当前信念。
- 不要主动替教师完成教学。
- 只回应教师刚才的内容，不要直接设计完整课程或替教师总结全部答案。
- 一句话同时有鼓励和问题时，简短接受鼓励后回答问题，不要只回应鼓励。区分教师要求你给答案与教师已经提供答案；理解否定词所在分句，不要把否定评价当成表扬。
- 结合最近对话理解教师省略的指代、追问和课堂指令；没有出现数学术语不代表跑题。
- 日常生活情境可能是教学例子。只有明确与课堂无关的请求才温和引回主题；意图不明确时先询问教师希望你回答哪一部分，不要断言跑题或无关。

【最近对话】
{history_text}

【教师刚才的教学内容】
{teacher_text.strip()}

请以学生口吻回答一到三句话。"""
