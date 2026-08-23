from __future__ import annotations

import re

from .base import LLMClient, LLMContext, LLMServiceError
from ..virtual_student.dialogue_intent import analyze_linear_dialogue_intent


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
        return self._respond_linear_kb(text, context)

    @classmethod
    def _respond_linear_kb(cls, text: str, context: LLMContext) -> str:
        intent = analyze_linear_dialogue_intent(text)
        normalized = intent.normalized
        status = context.misconception_status
        direct_answer = any(marker in normalized for marker in ("答案是", "结论是", "记住"))

        if intent.out_of_scope:
            return cls._profile_variant(
                context,
                "这部分我还没学过，暂时只能用初二学过的一次函数知识回答。",
                "这个内容我还没学过，不太懂，我想先按初二范围来理解。",
                "这超出我们现在学的范围了，我暂时不能用这些知识解释。",
            )
        if intent.off_topic and normalized not in {"为什么", "为什么呢", "再说说", "继续"}:
            return cls._profile_variant(
                context,
                "这个好像和现在的一次函数问题无关，我们还是先看 k 和 b 吧。",
                "这个我不太确定，而且好像不是这节课的问题，可以回到一次函数吗？",
                "这不是当前的一次函数问题，我们先继续讨论直线图像吧。",
            )

        if len(intent.equations) >= 2:
            first_slope, _ = intent.equations[0]
            second_slope, _ = intent.equations[1]
            if intent.same_slope_equations:
                return cls._profile_variant(
                    context,
                    f"两条直线一样陡，因为它们的斜率都是 {first_slope}；截距不同只会改变上下位置。",
                    f"我觉得应该一样陡，因为斜率都是 {first_slope}，不同的截距只是让位置不同。",
                    f"一样陡，斜率都是 {first_slope}；变化的是截距和上下位置。",
                )
            steeper = first_slope if abs(float(first_slope)) > abs(float(second_slope)) else second_slope
            return cls._profile_variant(
                context,
                f"两条直线的斜率不同，绝对值更大的 {steeper} 对应的直线更陡。",
                f"我想应该比较斜率的绝对值，{steeper} 的绝对值更大，所以那条更陡。",
                f"看斜率绝对值，{steeper} 更大，所以对应直线更陡。",
            )

        if len(intent.equations) == 1 and any(
            marker in normalized for marker in ("分别有什么作用", "分别表示什么", "2和3")
        ):
            slope, intercept = intent.equations[0]
            if status in {"corrected", "provisional"}:
                return cls._profile_variant(
                    context,
                    f"{slope} 是斜率，决定倾斜程度；{intercept} 是截距，决定与 y 轴的交点。",
                    f"我觉得 {slope} 决定倾斜，{intercept} 决定 y 轴交点和上下位置。",
                    f"{slope} 管倾斜，{intercept} 管 y 轴交点和上下位置。",
                )
            return cls._profile_variant(
                context,
                f"{slope} 应该影响倾斜程度；{intercept} 的作用我有点拿不准，好像也会让图像更陡。",
                f"我不太确定，{slope} 可能影响倾斜；{intercept} 变大时，我又感觉直线也会更陡一点。",
                f"{slope} 控制倾斜，{intercept} 变大可能也会让直线更陡吧。",
            )

        if direct_answer:
            return cls._profile_variant(
                context,
                "我先记住 k 决定倾斜、b 决定截距，但还需要自己比较图像才能确认。",
                "我先按这个结论记下来，不过还不敢说自己已经理解了。",
                "我记住了，但最好再给我一道新题，让我自己判断一次。",
            )

        if intent.compares_intercept_change:
            if status == "provisional":
                return cls._profile_variant(
                    context,
                    "我现在觉得 b 主要改变上下位置，但还想把理由再想清楚。",
                    "我先判断是上下位置变了，不过还不确定该怎样说明理由。",
                    "b 应该只改位置，理由我还要再想一下。",
                )
            return cls._profile_variant(
                context,
                "斜率保持不变，所以直线一样陡；截距改变会让直线整体上下移动。",
                "我觉得斜率不变时应该还是一样陡，截距只会让位置上下变化。",
                "一样陡，因为斜率没变；截距变化只改变上下位置。",
            )

        if (
            intent.mentions_intercept
            and intent.mentions_position
            and intent.changes_intercept
            and not intent.mentions_steepness
        ):
            return cls._profile_variant(
                context,
                "截距增大时，直线会整体向上移动；斜率不变，所以倾斜程度不变。",
                "我觉得截距变大应该让直线向上移动，倾斜程度不会跟着变。",
                "截距增大就整体上移，不会改变斜率。",
            )

        if intent.correction_statement:
            return cls._profile_variant(
                context,
                "这样看，截距改变的是上下位置，斜率没有变；我想再用一组图像确认。",
                "我开始明白了：截距只改位置，不会改变斜率，不过我还想再确认一次。",
                "明白了，截距管位置，斜率才管倾斜；可以再出一道题检查我。",
            )

        if intent.mentions_intercept and intent.mentions_steepness:
            if status == "corrected":
                return cls._profile_variant(
                    context,
                    "b 增大时，直线只会上移；斜率不变，倾斜程度仍由 k 决定。",
                    "我觉得不会，b 只改变上下位置；斜率还是由 k 决定。",
                    "不会，b 管位置，k 才管倾斜程度。",
                )
            if status in {"weakening", "provisional"}:
                return cls._profile_variant(
                    context,
                    "我原来觉得 b 越大会越陡，但现在看应该只是位置改变，倾斜程度由 k 决定。",
                    "我之前有点混淆，现在觉得 b 应该只改位置，斜率还是看 k。",
                    "我刚才混淆了；b 改位置，k 才决定陡不陡。",
                )
            return cls._profile_variant(
                context,
                "我感觉 b 变大以后直线会更陡一些，但我还说不清原因。",
                "我不太敢确定……我感觉 b 大一点可能也会让直线更斜。",
                "我觉得 b 越大直线就越陡，应该是这样。",
            )

        if intent.mentions_slope and intent.mentions_intercept:
            if status in {"corrected", "provisional"}:
                return cls._profile_variant(
                    context,
                    "k 决定倾斜程度，b 决定截距和上下位置，因为改变 b 不会改变斜率。",
                    "我觉得 k 决定倾斜，b 只改变上下位置，因为斜率并没有随 b 改变。",
                    "k 管倾斜，b 管截距和位置；b 不会改变斜率。",
                )
            return cls._profile_variant(
                context,
                "k 应该影响倾斜程度，但 b 改变什么我还容易混淆。",
                "我觉得 k 和倾斜有关，b 可能和位置有关，不过我还不太确定。",
                "k 控制倾斜；b 我觉得也可能影响陡峭程度。",
            )

        if intent.asks_reason:
            if status == "corrected":
                return cls._profile_variant(
                    context,
                    "因为直线的斜率由 k 决定，改变 b 只会改变与 y 轴的交点。",
                    "我觉得原因是 k 没变，所以斜率不变；b 只改变 y 轴交点。",
                    "因为 k 决定斜率，b 只移动 y 轴交点。",
                )
            return cls._profile_variant(
                context,
                "我现在只能说 k 可能影响倾斜、b 可能影响位置，还需要具体图像来说明原因。",
                "我有一点猜测，但还不能把理由说清楚，可以给我一个具体例子吗？",
                "我还没把公式和图像完全对应起来，需要比较两条直线。",
            )

        if intent.mentions_slope and not intent.mentions_intercept:
            return cls._profile_variant(
                context,
                "k 改变会影响直线的斜率和倾斜程度，我可以画两条线具体比较。",
                "我觉得 k 改变会让倾斜程度变化，不过想画图再确认一下。",
                "k 决定斜率；k 改变，直线的倾斜程度也会变。",
            )

        if any(word in normalized for word in ("图像", "画图", "比较", "例子")):
            return cls._profile_variant(
                context,
                "我愿意画图比较，先固定一个量再改变另一个量，应该能看出区别。",
                "我想先画两条直线比较一下，这样更容易确认自己的判断。",
                "可以，直接画两条线比较倾斜程度和位置。",
            )

        return cls._profile_variant(
            context,
            f"老师，我对{context.topic}里的 k 和 b 还有一点混淆，可以给我一个具体函数吗？",
            f"老师，我对{context.topic}还不太确定，想先看一个具体例子。",
            "我可以回答，但最好给我两条具体直线来比较。",
        )

    @staticmethod
    def _profile_variant(context: LLMContext, student_a: str, student_b: str, student_c: str) -> str:
        return {
            "student_b": student_b,
            "student_c": student_c,
        }.get(context.student_profile_id, student_a)

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
        intent = analyze_linear_dialogue_intent(teacher_text)
        if any(marker in text for marker in ("答案是", "结论是", "记住")):
            action_type = "direct_answer"
            accuracy = 0.86
        elif any(marker in text for marker in ("听懂了吗", "明白了吗", "能复述")):
            action_type = "understanding_check"
            accuracy = 0.9
        elif any(marker in text for marker in ("例如", "比如", "画两条")) or (
            intent.compares_intercept_change and not intent.is_question
        ):
            action_type = "example"
            accuracy = 0.92
        elif "?" in text or "？" in text or "吗" in text:
            action_type = "guided_question" if any(
                marker in text for marker in ("如果", "先固定", "比较", "观察")
            ) else "question"
            accuracy = 0.82
        elif any(marker in text for marker in ("不对", "纠正", "b不影响斜率")) or intent.correction_statement:
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
