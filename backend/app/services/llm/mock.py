from __future__ import annotations

import re

from .base import LLMClient, LLMContext, LLMServiceError


class MockLLMClient(LLMClient):
    """Deterministic, offline student responses for the current demo case."""

    provider = "mock"

    def respond(self, teacher_text: str, context: LLMContext | None = None) -> str:
        text = teacher_text.strip()
        if not text:
            raise LLMServiceError("教师输入不能为空")

        context = context or LLMContext()
        normalized = text.lower().replace(" ", "")
        branch = len(text) % 3

        if "b越大" in normalized or "b更大" in normalized:
            replies = [
                "我感觉 b 变大以后，直线会变得更陡一些，但我说不太清楚原因。",
                "是不是 b 越大，直线就越倾斜？我把它和 k 的作用有点混在一起了。",
                "我先猜 b 会让直线的斜率变大，因为图像看起来会更‘上扬’。",
            ]
            return replies[branch]

        if "k" in normalized and any(word in normalized for word in ("陡", "倾斜", "斜率")):
            replies = [
                "我觉得 k 应该和直线的倾斜有关，k 越大可能越陡；但 b 到底改变什么，我还不确定。",
                "如果只改变 k，直线的倾斜程度会变化。那 b 变化时，是不是整条直线上下移动？",
                "k 像是在控制直线的方向，b 像是在控制它从哪里开始，但我还需要画图确认。",
            ]
            return replies[branch]

        if "b" in normalized and any(word in normalized for word in ("截距", "平移", "上下", "位置")):
            replies = [
                "这样看起来 b 更像是和 y 轴交点有关，改变 b 会让直线整体上下移动。",
                "如果 k 不变，b 变了以后直线应该还是同样倾斜，只是位置不同，对吗？",
                "我可以先固定 k 画两条线，再比较 b 不同的时候哪里变了。",
            ]
            return replies[branch]

        if any(word in normalized for word in ("图像", "画图", "比较", "例子")):
            return (
                f"我愿意试着画一画。关于{context.topic}，如果先固定一个量再改变另一个量，"
                "应该能看出它们对直线的不同影响。"
            )

        if any(word in normalized for word in ("为什么", "解释", "理由")):
            return [
                "我会先说自己的想法：k 可能影响倾斜程度，b 可能影响位置，但我还需要用具体图像验证。",
                "我能算出结果，但暂时不能只靠公式解释图像为什么这样变化。",
                "这个问题让我发现我只记住了结论，还没有把公式和图像联系起来。",
            ][branch]

        return [
            f"老师，我先按自己的理解回答：{context.topic} 里 k 和 b 的作用不一样，但我还容易混淆。",
            "我可以先做代入计算，不过如果要解释图像变化，我需要一点提示。",
            "我有一个答案，但不确定能不能说明理由。您可以让我比较两条具体的直线吗？",
        ][branch]

    def analyze_behavior(
        self, teacher_text: str, context: LLMContext | None = None
    ) -> dict[str, object]:
        """Return varied, valid structured analysis without network access."""
        text = teacher_text.strip().lower().replace(" ", "")
        if any(marker in text for marker in ("答案是", "结论是", "记住")):
            action_type = "direct_answer"
            accuracy = 0.86
        elif any(marker in text for marker in ("听懂了吗", "明白了吗", "能复述")):
            action_type = "understanding_check"
            accuracy = 0.9
        elif any(marker in text for marker in ("例如", "比如", "画两条")):
            action_type = "example"
            accuracy = 0.92
        elif "?" in text or "？" in text or "吗" in text:
            action_type = "guided_question" if any(
                marker in text for marker in ("如果", "先固定", "比较", "观察")
            ) else "question"
            accuracy = 0.82
        elif any(marker in text for marker in ("不对", "纠正", "b不影响斜率")):
            action_type = "correction"
            accuracy = 0.95
        elif any(marker in text for marker in ("很好", "不错", "再想想")):
            action_type = "feedback"
            accuracy = 0.88
        else:
            action_type = "explanation"
            accuracy = 0.9

        concept = "slope_and_intercept" if "k" in text and "b" in text else "一次函数"
        return {
            "action_type": action_type,
            "concept": concept,
            "knowledge_accuracy": accuracy,
            "clarity": 0.84 if len(text) <= 100 else 0.7,
            "checked_understanding": any(
                marker in text for marker in ("听懂了吗", "明白了吗", "能复述")
            ),
            "gave_answer_directly": action_type == "direct_answer",
        }

    def analyze_evaluation(
        self, evaluation_prompt: str, context: LLMContext | None = None
    ) -> dict[str, object]:
        """Return offline qualitative feedback grounded in the supplied records."""
        rounds = [int(item) for item in re.findall(r"第(\d+)轮", evaluation_prompt)]
        strengths = ["教学记录已形成可复盘的行为和学生回应证据。"]
        problems = ["仍需结合学生的具体回答增加连续追问和理解确认。"]
        suggestions = ["在每次讲解或举例后，让学生复述、比较或说明理由。"]

        if "guided_question" in evaluation_prompt:
            strengths.append("教师使用了引导式提问，给学生保留了推理和表达空间。")
        if "example" in evaluation_prompt:
            strengths.append("教师使用了具体例子或比较，帮助连接公式与图像。")
        if "direct_answer" in evaluation_prompt:
            problems.append("部分轮次在学生回应后直接给出结论，学生自主解释空间不足。")
            suggestions.append("先追问学生的依据，再根据回答提供分层提示，避免立即替学生下结论。")
        if "correction" in evaluation_prompt:
            strengths.append("教师出现了针对性纠错行为，能够回应学生的概念偏差。")

        return {
            "strengths": strengths[:4],
            "problems": problems[:4],
            "suggestions": suggestions[:4],
            "evidence_rounds": sorted(set(rounds))[:4],
        }
