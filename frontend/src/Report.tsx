import {
actionLabel,
CognitiveTrace
} from "./cognitiveVisualization";
import type { BehaviorSummary,EvaluationReport } from './types';

import { formatScore } from './api';
import { RadarChart } from './Charts';
import { CognitiveReport } from './CognitivePanels';
export function EvaluationPanel({ report, behaviorSummary, trace }: { report: EvaluationReport; behaviorSummary: BehaviorSummary; trace?: CognitiveTrace }) {
  const dimensions = [
    ["知识准确性", report.knowledge_accuracy],
    ["提问与引导", report.questioning],
    ["教学反馈", report.feedback],
    ["错误诊断能力", report.misconception_diagnosis],
    ["支架式教学", report.scaffolding],
  ] as const;

  return (
    <section className="evaluation-panel">
      <div className="evaluation-header">
        <div>
          <span className="section-kicker">训练辅助评价</span>
          <h2>本次教学复盘</h2>
        </div>
        <div className="evaluation-total"><span>参考分</span><strong>{formatScore(report.overall_score)}</strong>{report.overall_score !== null && <span>/ 100</span>}</div>
      </div>
      <p className="runtime-status">{report.rubric_version === 1 ? '第一版历史报告 · 分数按原标准保留' : `评分第 2 版 · 证据覆盖 ${Math.round((report.evidence.coverage ?? 0)*100)}% · 独立任务 ${report.evidence.independent_tasks ?? '—'} 个`}</p><p className="evaluation-order-note">先看学生的认知变化，再结合行为指标复盘教学过程。</p>
      <CognitiveReport trace={trace} />
      <p className="evaluation-summary">{report.summary}</p>
      <div className="evaluation-scores">
        {dimensions.map(([label, score]) => (
          <div className="evaluation-score" key={label}>
            <div><span>{label}</span><strong>{formatScore(score)}</strong></div>
            {score === null ? <small>暂无足够证据</small> : <div className="state-track"><i className="state-fill state-green" style={{ width: `${score}%` }} /></div>}
          </div>
        ))}
      </div>
      <RadarChart report={report} />{report.rubric_version === 2 && <ScoringEvidence report={report} />}
      {report.rubric_version === 1 && <TeachingBehaviorFeedback summary={behaviorSummary} />}
      <div className="evaluation-columns">
        <EvaluationList title="做得较好的地方" items={report.strengths} className="evaluation-good" />
        <EvaluationList title="主要问题" items={report.problems} className="evaluation-problem" />
        <EvaluationList title="改进建议" items={report.suggestions} className="evaluation-advice" />
      </div>
      {report.key_teaching_snippets.length > 0 && (
        <div className="evaluation-evidence">
          <span className="detail-label">关键教学片段</span>
          {report.key_teaching_snippets.map((snippet) => (
            <blockquote key={`${snippet.round}-${snippet.action_type}`}>
              <strong>第 {snippet.round} 轮 · {actionLabel(snippet.action_type)}</strong>
              <p>{snippet.evidence}</p>
            </blockquote>
          ))}
        </div>
      )}
      <BehaviorStats summary={behaviorSummary} />
      <p className="evaluation-disclaimer">◇ {report.disclaimer}</p>
    </section>
  );
}
function TeachingBehaviorFeedback({ summary }: { summary: BehaviorSummary }) {
  const items: string[] = [];
  if (summary.direct_answer_count === 0) items.push("没有立即直接公布答案，给学生留下了思考空间。");
  if (summary.guided_question_count > 0) items.push(`使用了 ${summary.guided_question_count} 次引导式提问，帮助学生逐步表达理解。`);
  if (summary.example_count > 0) items.push(`使用了 ${summary.example_count} 次具体例子或对比。`);
  if (summary.understanding_check_count > 0) items.push(`进行了 ${summary.understanding_check_count} 次理解确认。`);
  if (summary.correction_count > 0) items.push(`进行了 ${summary.correction_count} 次针对性纠错。`);
  if (items.length === 0) items.push("本次还没有足够的结构化教学行为记录。可以尝试加入提问、举例或理解确认。");
  return (
    <div className="behavior-feedback">
      <span className="detail-label">教师做对了什么</span>
      <ul>{items.slice(0, 4).map((item) => <li key={item}>✓ {item}</li>)}</ul>
    </div>
  );
}
function BehaviorStats({ summary }: { summary: BehaviorSummary }) {
  const items = [
    ["提问", summary.question_count],
    ["引导式提问", summary.guided_question_count],
    ["举例", summary.example_count],
    ["理解确认", summary.understanding_check_count],
    ["直接给答案", summary.direct_answer_count],
    ["纠错", summary.correction_count],
    ["反馈", summary.feedback_count],
    ["讲解", summary.explanation_count],
    ["课堂互动", summary.classroom_interaction_count],
    ["非教学话题", summary.off_topic_count],
  ] as const;
  return (
    <div className="behavior-stats">
      <span className="detail-label">教学行为统计</span>
      <div className="behavior-stat-grid">
        {items.map(([label, value]) => (
          <div className="behavior-stat" key={label}><span>{label}</span><strong>{value}</strong></div>
        ))}
      </div>
    </div>
  );
}
function EvaluationList({ title, items, className }: { title: string; items: string[]; className: string }) {
  return (
    <div className={`evaluation-list ${className}`}>
      <span className="detail-label">{title}</span>
      <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function ScoringEvidence({report}: {report: EvaluationReport}) {
 const labels: Record<string,string> = {knowledge_accuracy:'知识准确性', questioning:'提问', feedback:'反馈', misconception_diagnosis:'错误诊断', scaffolding:'支架支持'};
 return <details className="scoring-evidence"><summary>查看评分依据与引用轮次</summary><p>每项 0 / 0.5 / 1 表示未满足、部分满足、充分满足；此规则尚待教师人工校准。</p>{Object.entries(report.evidence.dimensions ?? {}).map(([name, tasks]) => <section key={name}><h4>{labels[name] ?? name}</h4>{tasks.map((task,index) => <div key={index}>{task.rounds && <p>第 {task.rounds.join('、')} 轮：{task.reason}</p>}{task.checks.map((check,i) => typeof check === 'boolean' ? <span key={i}>{check ? '已核验正确' : '观察到错误主张'} </span> : <p key={i}>{check.criterion}：{check.value} · {check.reason}（第 {check.rounds.join('、') || '—'} 轮）</p>)}</div>)}</section>)}</details>;
}
