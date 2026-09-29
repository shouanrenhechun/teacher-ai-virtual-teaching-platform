from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from .evidence_scoring import score_session, WEIGHTS as EVALUATION_WEIGHTS
from .llm import LLMClient, LLMContext
from .llm.base import LLMError
from ..models import Evaluation, EvaluationNarrative, TeachingSession
from ..schemas.evaluation import (
    EvaluationQualitativeAnalysis,
    EvaluationReportRead,
    KeyTeachingSnippet,
)


logger = logging.getLogger(__name__)

EVALUATION_DISCLAIMER = "本评价仅用于教学训练辅助，不替代专业教师的正式评价。"


class EvaluationEngine:
    """Calculate observable scores, then optionally add validated qualitative analysis."""

    def evaluate_and_save(
        self,
        db: Session,
        session: TeachingSession,
        llm_client: LLMClient | None = None,
    ) -> EvaluationReportRead:
        if session.evaluation is not None and session.evaluation.narrative is not None:
            return self.to_read(session.evaluation, session.evaluation.narrative)
        if session.evaluation is not None and session.evaluation.rubric_version == 1:
            narrative = EvaluationNarrative(session_id=session.id, strengths_json='[]',
                problems_json=json.dumps(['历史报告缺少质性记录，原分数已保留。'], ensure_ascii=False),
                suggestions_json=json.dumps(['可结合原始对话复盘。'], ensure_ascii=False), snippets_json='[]',
                disclaimer=EVALUATION_DISCLAIMER, generated_at=datetime.now(UTC).replace(tzinfo=None), analysis_source='legacy')
            db.add(narrative)
            db.commit()
            return self.to_read(session.evaluation, narrative)
        scores, evidence = score_session(session)
        snippets_by_round = self._candidate_snippets(session)
        session_id = session.id
        db.expunge_all()
        db.rollback()
        qualitative, analysis_source, analysis_error = self._qualitative_analysis(
            session, scores, snippets_by_round, llm_client, evidence
        )
        unassessed = sum(record.concept == '未判定知识' for record in session.behavior_records)
        if unassessed:
            qualitative = qualitative.model_copy(update={
                'problems': [*qualitative.problems, f'有 {unassessed} 轮知识内容未判定（包括待辨析命题），未计入知识准确性；该分数不代表全部教学内容。']
            })
        selected_snippets = self._select_snippets(
            snippets_by_round, qualitative.evidence_rounds
        )
        summary = self._build_summary(scores, qualitative)
        generated_at = datetime.now(UTC).replace(tzinfo=None)

        db.execute(text('BEGIN IMMEDIATE'))
        evaluation = db.get(Evaluation, session_id)
        if evaluation is not None and evaluation.narrative is not None:
            report = self.to_read(evaluation, evaluation.narrative)
            db.commit()
            return report
        if evaluation is None:
            evaluation = Evaluation(session_id=session.id, **scores, summary=summary)
            db.add(evaluation)
        else:
            for key, value in scores.items():
                setattr(evaluation, key, value)
            evaluation.summary = summary
        evaluation.rubric_version = 2
        evaluation.evidence_json = json.dumps(evidence, ensure_ascii=False)
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

    def calculate_scores(self, session: TeachingSession) -> dict[str, float | None]:
        return score_session(session)[0]

    def _qualitative_analysis(
        self,
        session: TeachingSession,
        scores: dict[str, float | None],
        snippets_by_round: dict[int, KeyTeachingSnippet],
        llm_client: LLMClient | None,
        evidence: dict | None = None,
    ) -> tuple[EvaluationQualitativeAnalysis, str, str | None]:
        evidence = evidence or score_session(session)[1]
        fallback = self._fallback_qualitative(session, scores, snippets_by_round, evidence)
        if llm_client is None or llm_client.provider == 'mock':
            return fallback, "rules", None

        prompt = self._build_qualitative_prompt(session, scores, snippets_by_round, evidence)
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
            if any(n not in snippets_by_round for n in result.evidence_rounds):
                raise ValueError("评价引用了不存在的轮次")
            evidence_rounds = {n for entries in evidence.get('dimensions', {}).values() for entry in entries
                for n in [*entry.get('rounds', []), *(r for check in entry.get('checks', []) if isinstance(check, dict) for r in check['rounds'])]}
            if evidence_rounds and any(n not in evidence_rounds for n in result.evidence_rounds):
                raise ValueError('评价建议必须引用逐项评分使用的证据轮次')
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
        scores: dict[str, float | None],
        snippets_by_round: dict[int, KeyTeachingSnippet],
        evidence: dict,
    ) -> EvaluationQualitativeAnalysis:
        labels = {'knowledge_accuracy': '知识准确性', 'questioning': '提问', 'feedback': '反馈', 'misconception_diagnosis': '错误诊断', 'scaffolding': '支架支持'}
        strengths, problems, suggestions, cited_rounds = [], [], [], []
        for key, label in labels.items():
            entries = evidence.get('dimensions', {}).get(key, [])
            checks = [check for entry in entries for check in entry.get('checks', []) if isinstance(check, dict)]
            candidate = next((check for check in checks if check['value'] < 1), checks[0] if checks else None)
            refs = candidate['rounds'] if candidate else sorted({n for entry in entries for n in entry.get('rounds', [])})
            cited_rounds.extend(refs)
            citation = '（第 ' + '、'.join(map(str, refs)) + ' 轮）' if refs else ''
            if scores.get(key) is None:
                problems.append(f'{label}尚未观察到足够证据，不能据此判断能力高低。')
            elif scores[key] >= 75:
                strengths.append(f'{label}观察到较充分的教学证据{citation}。')
            else:
                criterion = candidate['criterion'] if candidate else '核验明确主张'
                problems.append(f'{label}中的“{criterion}”仍需补充证据{citation}。')
                suggestions.append(f'结合{citation or "原始对话"}复盘“{criterion}”，提供下一步提示并让学生独立作答。')
        return EvaluationQualitativeAnalysis(strengths=strengths or ['已保留可供复盘的课堂对话。'],
            problems=problems or ['可继续通过不同题目检验教学策略。'],
            suggestions=suggestions or ['让学生在新题中独立解释，并对照逐项证据复盘。'],
            evidence_rounds=list(dict.fromkeys(cited_rounds))[:8])

    @staticmethod
    def _build_qualitative_prompt(
        session: TeachingSession,
        scores: dict[str, float | None],
        snippets_by_round: dict[int, KeyTeachingSnippet],
        evidence: dict,
    ) -> str:
        records = "\n".join(
            f"[第{round_number}轮][行为={snippet.action_type}]教师：{snippet.teacher_text}；"
            f"学生：{snippet.student_text}"
            for round_number, snippet in snippets_by_round.items()
        ) or "（暂无教师教学记录）"
        score_text = "，".join(f"{key}={value if value is not None else '未评估'}" for key, value in scores.items())
        return (
            "请基于以下真实教学记录进行训练辅助评价。只输出 JSON，不要修改或生成分数。"
            "JSON 字段必须为 strengths、problems、suggestions、evidence_rounds；"
            "每个前三项至少给出一条具体内容，evidence_rounds 只能引用记录中的轮次。"
            f"评分（由规则计算，仅供参考）：{score_text}\n逐项评分证据（建议必须引用相同证据）：{json.dumps(evidence, ensure_ascii=False)}\n记录：\n{records}"
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
                    f"第 {round_number} 轮教师直接给出结论：“{_clip(teacher_text)}”，"
                    f"随后学生回答：“{_clip(student_text)}”。"
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
        score = scores['overall_score']
        prefix = f"训练参考分 {score:.1f} 分" if score is not None else "证据不足，暂不生成总分"
        return f"{prefix}。主要复盘点：{issue}"

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
            rubric_version=evaluation.rubric_version,
            evidence=json.loads(evaluation.evidence_json or '{}'),
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
