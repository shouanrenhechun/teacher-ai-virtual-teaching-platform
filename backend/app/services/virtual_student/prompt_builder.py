from __future__ import annotations

from .engine import VirtualStudentEngine


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
        misconceptions = "；".join(
            f"{item.name}（强度={item.strength:.2f}，已触发={item.triggered}，"
            f"已开始修正={item.correction_started}，状态={item.status}，已纠正={item.corrected}）"
            for item in snapshot.misconceptions
            if not item.corrected
        ) or "当前没有未纠正的固定认知错误"
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
- 不得突然获得尚未掌握的知识；可以犹豫、猜测或请求提示。
- 未被有效纠正前，保持未纠正的固定认知错误，不要主动替教师完成教学。
- 只回应教师刚才的内容，不要直接设计完整课程或替教师总结全部答案。

【最近对话】
{history_text}

【教师刚才的教学内容】
{teacher_text.strip()}

请以学生口吻回答一到三句话。"""
