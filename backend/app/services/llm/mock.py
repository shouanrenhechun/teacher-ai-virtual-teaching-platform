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

        if any(marker in context.topic for marker in ("完全平方", "平方公式")):
            return self._respond_binomial_square(normalized, branch)

        if "2和3" in normalized or "2和3".replace("和", "") in normalized:
            return "2应该影响倾斜程度吧，3的话……我总觉得它越大，直线好像也会越陡？"

        if "先不看我刚才" in normalized or "y=kx+b" in normalized:
            return "k 决定直线的倾斜程度，b 决定上下位置；因为 k 改变方向，b 改变截距。"

        if "y=4x-2" in normalized or "y=4x+7" in normalized:
            return "两条直线一样陡，因为它们的 k 都是 4；b 不同只会让位置上下移动。"

        if "y=-3x+1" in normalized or "只改变b" in normalized:
            return "两条直线一样陡，因为 k 都是 -3；b 只会让它们上下移动，位置不同。"

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

    @staticmethod
    def _respond_binomial_square(normalized: str, branch: int) -> str:
        """Small offline responses for the second misconception only."""
        if "x+4" in normalized:
            return "(x+4)^2=x²+8x+16，因为展开会有 4x+4x 两个交叉项。"
        if "2x+3" in normalized:
            return "(2x+3)^2=4x²+12x+9，中间的 12x 来自两个 6x。"
        if "x-5" in normalized or "负号" in normalized:
            return "(x-5)^2=x²-10x+25，两个交叉项是 -5x 和 -5x。"
        if "答案是" in normalized or "a²+2ab+b²" in normalized or "a^2+2ab+b^2" in normalized:
            return "对，(a+b)^2=a²+2ab+b²，我先记住这个公式。"
        if "平方就是分别平方" in normalized or "没有中间项" in normalized:
            return "对，我原来也觉得括号里的两项分别平方就行，好像没有中间项。"
        if "ab" in normalized and any(marker in normalized for marker in ("几次", "出现", "为什么")):
            return "ab 会从两个交叉相乘中各出现一次，所以合起来是 2ab。"
        if any(marker in normalized for marker in ("两个相同", "相乘", "展开")):
            return "写成两个相同括号相乘后，我好像看到了两个交叉项，但还要再确认一下。"
        if "2x+1" in normalized:
            return "我先算成 4x²+1，括号里的两项分别平方就可以了吧？"
        if "x+3" in normalized:
            return "我觉得 (x+3)^2=x²+9，先把 x 和 3 分别平方。"
        if "x+2" in normalized:
            return "我先猜是 x²+4，不过写成两个括号相乘后好像还有别的项。"
        return (
            "括号平方我有点容易漏掉中间项，可能需要把两个括号真正乘开。"
            if branch == 0
            else "我记得每一项平方，但还不太确定交叉相乘要不要算进去。"
        )

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
