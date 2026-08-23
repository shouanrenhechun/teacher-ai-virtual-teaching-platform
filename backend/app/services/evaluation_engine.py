from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from .llm import LLMClient, LLMContext
from .llm.base import LLMError
from ..models import Evaluation, EvaluationNarrative, TeachingSession
from ..schemas.evaluation import (
    EvaluationQualitativeAnalysis,
    EvaluationReportRead,
    KeyTeachingSnippet,
)


logger = logging.getLogger(__name__)

EVALUATION_WEIGHTS: dict[str, float] = {
    "knowledge_accuracy": 0.30,
    "questioning": 0.20,
    "feedback": 0.15,
    "misconception_diagnosis": 0.20,
    "scaffolding": 0.15,
}
EVALUATION_DISCLAIMER = "本评价仅用于教学训练辅助，不替代专业教师的正式评价。"


class EvaluationEngine:
    """Calculate observable scores, then optionally add validated qualitative analysis."""

    def evaluate_and_save(
        self,
        db: Session,
        session: TeachingSession,
        llm_client: LLMClient | None = None,
    ) -> EvaluationReportRead:
        scores = self.calculate_scores(session)
        snippets_by_round = self._candidate_snippets(session)
        qualitative, analysis_source, analysis_error = self._qualitative_analysis(
            session, scores, snippets_by_round, llm_client
        )
        selected_snippets = self._select_snippets(
            snippets_by_round, qualitative.evidence_rounds
        )
        summary = self._build_summary(scores, qualitative)
        generated_at = datetime.now(UTC).replace(tzinfo=None)

        evaluation = db.get(Evaluation, session.id)
        if evaluation is None:
            evaluation = Evaluation(session_id=session.id, **scores, summary=summary)
            db.add(evaluation)
        else:
            for key, value in scores.items():
                setattr(evaluation, key, value)
            evaluation.summary = summary
        db.flush()

        narrative = db.get(EvaluationNarrative, session.id)
        if narrative is None:
            narrative = EvaluationNarrative(
                session_id=session.id,
                strengths_json="[]",
                problems_json="[]",
                suggestions_json="[]",
                snippets_json="[]",
                disclaimer=EVALUATION_DISCLAIMER,
                generated_at=generated_at,
                analysis_source=analysis_source,
                analysis_error=analysis_error,
            )
            db.add(narrative)

        narrative.strengths_json = json.dumps(qualitative.strengths, ensure_ascii=False)
        narrative.problems_json = json.dumps(qualitative.problems, ensure_ascii=False)
        narrative.suggestions_json = json.dumps(qualitative.suggestions, ensure_ascii=False)
        narrative.snippets_json = json.dumps(
            [snippet.model_dump(mode="json") for snippet in selected_snippets],
            ensure_ascii=False,
        )
        narrative.disclaimer = EVALUATION_DISCLAIMER
        narrative.generated_at = generated_at
        narrative.analysis_source = analysis_source
        narrative.analysis_error = analysis_error
        db.commit()
        return self.to_read(evaluation, narrative)

    def calculate_scores(self, session: TeachingSession) -> dict[str, float]:
        records = list(session.behavior_records)
        if not records:
            scores = {dimension: 0.0 for dimension in EVALUATION_WEIGHTS}
            scores["overall_score"] = 0.0
            return scores

        counts = self._counts(records)
        knowledge_records = [
            record
            for record in records
            if record.action_type != "classroom_interaction"
            and getattr(record, "concept", None) != "课堂互动"
        ]
        knowledge_accuracy = (
            self._round_score(
                sum(record.knowledge_accuracy for record in knowledge_records)
                / len(knowledge_records)
                * 100
            )
            if knowledge_records
            else 0.0
        )
        questioning = self._target_score(
            counts["question"] + counts["guided_question"] * 1.25,
            target=3,
        )
        feedback = self._target_score(counts["feedback"], target=2)
        misconception_diagnosis = self._round_score(
            min(100.0, counts["correction"] / 2 * 70 + counts["understanding_check"] / 2 * 30)
        )
        scaffolding = self._round_score(
            max(
                0.0,
                min(
                    100.0,
                    (
                        counts["example"] * 0.4
                        + counts["guided_question"] * 0.4
                        + counts["understanding_check"] * 0.2
                    )
                    / 3
                    * 100
                    - counts["direct_answer"] * 8,
                ),
            )
        )
        scores = {
            "knowledge_accuracy": knowledge_accuracy,
            "questioning": questioning,
            "feedback": feedback,
            "misconception_diagnosis": misconception_diagnosis,
            "scaffolding": scaffolding,
        }
        scores["overall_score"] = self._round_score(
            sum(scores[dimension] * weight for dimension, weight in EVALUATION_WEIGHTS.items())
        )
        return scores

    def _qualitative_analysis(
        self,
        session: TeachingSession,
        scores: dict[str, float],
        snippets_by_round: dict[int, KeyTeachingSnippet],
        llm_client: LLMClient | None,
    ) -> tuple[EvaluationQualitativeAnalysis, str, str | None]:
        fallback = self._fallback_qualitative(session, scores, snippets_by_round)
        if llm_client is None:
            return fallback, "rules", None

        prompt = self._build_qualitative_prompt(session, scores, snippets_by_round)
        try:
            raw_result = llm_client.analyze_evaluation(
                prompt,
                LLMContext(
                    student_name=session.virtual_student.name,
                    student_grade=session.virtual_student.grade,
                    topic=session.scenario.topic,
                ),
            )
            result = EvaluationQualitativeAnalysis.model_validate(raw_result)
            return result, "rules+llm", None
        except (LLMError, ValidationError, TypeError, ValueError) as exc:
            logger.warning("教学评价质性分析失败，使用规则报告: %s", exc)
            return fallback, "fallback", str(exc)[:500]
        except Exception as exc:  # Defensive boundary for third-party providers.
            logger.exception("教学评价出现未预期错误，使用规则报告")
            return fallback, "fallback", str(exc)[:500]

    def _fallback_qualitative(
        self,
        session: TeachingSession,
        scores: dict[str, float],
        snippets_by_round: dict[int, KeyTeachingSnippet],
    ) -> EvaluationQualitativeAnalysis:
        records = list(session.behavior_records)
        counts = self._counts(records)
        strengths: list[str] = []
        problems: list[str] = []
        suggestions: list[str] = []

        if scores["knowledge_accuracy"] >= 80:
            strengths.append("教师对当前教学主题的知识表述整体准确。")
        if counts["guided_question"]:
            strengths.append(f"教师使用了 {counts['guided_question']} 次引导式提问，给学生保留了思考空间。")
        if counts["example"]:
            strengths.append(f"教师提供了 {counts['example']} 次例子或对比，有助于把概念落到图像或具体情境。")
        if not strengths:
            strengths.append("本次记录中已形成可供复盘的教学行为证据。")

        if counts["direct_answer"]:
            round_number = self._first_round(counts, session, "direct_answer")
            problems.append(f"第 {round_number} 轮出现直接给出结论的行为，可能压缩学生自行解释的机会。")
            suggestions.append("在给出结论前先追问学生的依据，并安排一次简短的理解确认。")
        if not counts["understanding_check"]:
            problems.append("教学记录中没有观察到明确的理解确认行为。")
            suggestions.append("在讲解或举例后增加‘请你复述/比较一下’等理解确认。")
        if not counts["correction"]:
            problems.append("教学记录中没有观察到针对学生认知错误的明确纠正。")
            suggestions.append("结合学生的具体回答指出错误所在，再用对比例子帮助其修正。")
        if scores["questioning"] < 60:
            problems.append("提问与引导次数偏少，课堂中的学生思考节点还不够明显。")
            suggestions.append("把完整讲解拆成连续的小问题，优先使用带条件或比较关系的引导式提问。")
        if not problems:
            problems.append("当前记录未显示明显薄弱项，可继续积累学生回答后的追问证据进行复盘。")
        if not suggestions:
            suggestions.append("继续保留真实教学片段，围绕学生回答进行针对性追问和反馈。")

        return EvaluationQualitativeAnalysis(
            strengths=strengths,
            problems=problems,
            suggestions=suggestions,
            evidence_rounds=list(snippets_by_round)[:4],
        )

    @staticmethod
    def _build_qualitative_prompt(
        session: TeachingSession,
        scores: dict[str, float],
        snippets_by_round: dict[int, KeyTeachingSnippet],
    ) -> str:
        records = "\n".join(
            f"[第{round_number}轮][行为={snippet.action_type}]教师：{snippet.teacher_text}；"
            f"学生：{snippet.student_text}"
            for round_number, snippet in snippets_by_round.items()
        ) or "（暂无教师教学记录）"
        score_text = "，".join(f"{key}={value:.1f}" for key, value in scores.items())
        return (
            "请基于以下真实教学记录进行训练辅助评价。只输出 JSON，不要修改或生成分数。"
            "JSON 字段必须为 strengths、problems、suggestions、evidence_rounds；"
            "每个前三项至少给出一条具体内容，evidence_rounds 只能引用记录中的轮次。"
            f"评分（由规则计算，仅供参考）：{score_text}\n记录：\n{records}"
        )

    @staticmethod
    def _candidate_snippets(session: TeachingSession) -> dict[int, KeyTeachingSnippet]:
        behavior_by_dialogue = {
            record.dialogue_record_id: record for record in session.behavior_records
        }
        dialogue_by_sequence = {record.sequence: record for record in session.dialogue_records}
        snippets: dict[int, KeyTeachingSnippet] = {}
        round_number = 0
        for teacher in sorted(
            (record for record in session.dialogue_records if record.speaker == "teacher"),
            key=lambda record: record.sequence,
        ):
            round_number += 1
            behavior = behavior_by_dialogue.get(teacher.id)
            action_type = behavior.action_type if behavior else "unclassified"
            student = dialogue_by_sequence.get(teacher.sequence + 1)
            student_text = student.content if student else "（暂无学生回答）"
            teacher_text = teacher.content
            if action_type == "direct_answer" and student:
                evidence = (
                    f"第 {round_number} 轮学生表示“{_clip(student_text)}”后，"
                    f"教师直接给出了结论：“{_clip(teacher_text)}”。"
                )
            elif action_type in {"guided_question", "question"}:
                evidence = f"第 {round_number} 轮教师通过提问引导学生：“{_clip(teacher_text)}”。"
            else:
                evidence = f"第 {round_number} 轮教师的{action_type}行为：“{_clip(teacher_text)}”。"
            snippets[round_number] = KeyTeachingSnippet(
                round=round_number,
                action_type=action_type,
                teacher_text=teacher_text,
                student_text=student_text,
                evidence=evidence,
            )
        return snippets

    @staticmethod
    def _select_snippets(
        snippets_by_round: dict[int, KeyTeachingSnippet], evidence_rounds: list[int]
    ) -> list[KeyTeachingSnippet]:
        selected = [snippets_by_round[item] for item in evidence_rounds if item in snippets_by_round]
        if not selected:
            selected = list(snippets_by_round.values())[:4]
        return selected[:4]

    @staticmethod
    def _build_summary(
        scores: dict[str, float], qualitative: EvaluationQualitativeAnalysis
    ) -> str:
        issue = qualitative.problems[0] if qualitative.problems else "暂无主要问题"
        return f"综合得分 {scores['overall_score']:.1f} 分。主要复盘点：{issue}"

    @staticmethod
    def _counts(records: list[Any]) -> dict[str, int]:
        counts = {
            "question": 0,
            "guided_question": 0,
            "example": 0,
            "feedback": 0,
            "correction": 0,
            "understanding_check": 0,
            "direct_answer": 0,
        }
        for record in records:
            if record.action_type in counts:
                counts[record.action_type] += 1
        return counts

    @staticmethod
    def _target_score(value: float, *, target: float) -> float:
        return round(min(100.0, value / target * 100), 2)

    @staticmethod
    def _round_score(value: float) -> float:
        return round(max(0.0, min(100.0, value)), 2)

    @staticmethod
    def _first_round(counts: dict[str, int], session: TeachingSession, action_type: str) -> int:
        behavior_by_dialogue = {
            record.dialogue_record_id: record for record in session.behavior_records
        }
        teacher_records = sorted(
            (record for record in session.dialogue_records if record.speaker == "teacher"),
            key=lambda record: record.sequence,
        )
        for index, teacher in enumerate(teacher_records, start=1):
            behavior = behavior_by_dialogue.get(teacher.id)
            if behavior and behavior.action_type == action_type:
                return index
        return 1

    @staticmethod
    def to_read(evaluation: Evaluation, narrative: EvaluationNarrative) -> EvaluationReportRead:
        return EvaluationReportRead(
            session_id=evaluation.session_id,
            knowledge_accuracy=evaluation.knowledge_accuracy,
            questioning=evaluation.questioning,
            feedback=evaluation.feedback,
            misconception_diagnosis=evaluation.misconception_diagnosis,
            scaffolding=evaluation.scaffolding,
            overall_score=evaluation.overall_score,
            summary=evaluation.summary,
            strengths=json.loads(narrative.strengths_json),
            problems=json.loads(narrative.problems_json),
            suggestions=json.loads(narrative.suggestions_json),
            key_teaching_snippets=json.loads(narrative.snippets_json),
            disclaimer=narrative.disclaimer,
            generated_at=narrative.generated_at,
            analysis_source=narrative.analysis_source,
            analysis_error=narrative.analysis_error,
        )


def _clip(text: str, limit: int = 120) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else f"{clean[:limit - 1]}…"
