import {
actionLabel,
CognitiveTrace,
CognitiveTraceRound,
hasStateChange,
masteryReasons,
missingEvidence,
statusDescription,
statusLabel,
strengthChangeLabel,
strengthDelta,
strengthInterpretation,
teachingAdvice,
timelineNodeLabel,
} from "./cognitiveVisualization";

import { formatPercent } from './api';
import { CognitiveStrengthChart } from './Charts';
export function CognitiveStatePanel({ trace }: { trace?: CognitiveTrace }) {
  if (!trace) {
    return <div className="session-panel cognitive-panel"><span className="detail-label">认知状态</span><p className="fallback-copy">暂无该项分析</p></div>;
  }
  const current = trace.current_misconception;
  const latest = trace.rounds.at(-1);
  return (
    <div className="session-panel cognitive-panel">
      <div className="cognitive-panel-heading">
        <div><span className="detail-label">认知状态</span><h3>{current ? statusLabel(current.status) : "暂无状态记录"}</h3></div>
        {current && <span className={`cognitive-status-dot status-${current.status}`} />}
      </div>
      {current ? (
        <>
          <p className="cognitive-description">{statusDescription(current.status)}</p>
          <div className="misconception-copy"><span>当前错误认知</span><strong>{current.name}</strong></div>
          <StrengthBar value={current.strength} latest={latest} />
          {latest && hasStateChange(latest) && (
            <div className="state-change-note"><strong>认知状态发生变化</strong><span>{statusLabel(latest.misconception_before?.status)} → {statusLabel(latest.misconception_after?.status)}</span></div>
          )}
          <EvidenceCard round={latest} />
          <div className={`next-evidence next-evidence-${current.status}`}>
            <span className="detail-label">{current.status === "corrected" ? "为什么认为已经掌握？" : "当前还缺什么？"}</span>
            <ul>
              {(current.status === "corrected" ? masteryReasons(latest) : missingEvidence(trace)).map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
          <CognitiveTimeline trace={trace} compact />
          <details className="technical-details">
            <summary>查看技术详情</summary>
            <div className="technical-grid">
              <span>status <b>{current.status}</b></span>
              <span>strength <b>{current.strength.toFixed(2)}</b></span>
              <span>stable evidence <b>{current.stable_correct_evidence_count}</b></span>
              <span>transfer evidence <b>{current.transfer_evidence}</b></span>
              <span>semantic type <b>{current.semantic_type}</b></span>
              <span>surface recall <b>{trace.current_state.surface_recall.toFixed(2)}</b></span>
            </div>
          </details>
        </>
      ) : <p className="fallback-copy">暂无该项分析</p>}
    </div>
  );
}

export function StrengthBar({ value, latest }: { value: number; latest?: CognitiveTraceRound }) {
  const before = latest?.misconception_before?.strength;
  const change = before === undefined ? null : strengthChangeLabel(before, value);
  return (
    <div className="strength-meter">
      <div><span>错误认知强度</span><strong>{value.toFixed(2)}</strong></div>
      <div className="strength-track"><i style={{ width: `${value * 100}%` }} /></div>
      <div className="strength-scale"><span>0 · 错误较弱</span><span>1 · 错误较强</span></div>
      <small>数值越高，表示该错误认知越牢固。{change ? ` ${before?.toFixed(2)} → ${value.toFixed(2)} · ${change}。` : ` 当前：${strengthInterpretation(value)}。`}</small>
    </div>
  );
}

export function EvidenceCard({ round }: { round?: CognitiveTraceRound }) {
  if (!round?.evidence) return <div className="evidence-card"><span className="detail-label">本轮学习证据</span><p className="fallback-copy">暂无该项分析</p></div>;
  const evidence = round.evidence;
  const surfaceRecall = evidence.parrots_teacher || round.state_after.surface_recall >= 0.1;
  const primaryEvidence: Array<{ text: string; className: string }> = [];
  if (evidence.shows_residual_misconception) primaryEvidence.push({ text: "⚠ 仍存在原有错误认知", className: "evidence-warn" });
  if (evidence.states_correct_conclusion) primaryEvidence.push({ text: "✓ 得出了正确结论", className: "evidence-good" });
  if (evidence.explains_reason_correctly) primaryEvidence.push({ text: "✓ 能解释原因", className: "evidence-good" });
  if (evidence.transfer_success) primaryEvidence.push({ text: "✓ 能迁移到新的题目", className: "evidence-good" });
  const secondaryEvidence: string[] = [];
  if (surfaceRecall) secondaryEvidence.push("可能只是复述教师结论");
  if (evidence.conceptual_uncertainty) secondaryEvidence.push("对概念仍存在真实犹豫");
  if (evidence.linguistic_hedging) secondaryEvidence.push("表达较谨慎（不等于错误）");
  return (
    <div className="evidence-card">
      <div className="evidence-heading"><span className="detail-label">本轮学习证据</span><span>第 {round.round} 轮</span></div>
      <div className="evidence-list">
        {primaryEvidence.slice(0, 3).map((item) => <span className={`evidence-item ${item.className}`} key={item.text}>{item.text}</span>)}
        {primaryEvidence.length === 0 && <span className="evidence-item evidence-neutral">○ 当前证据仍不足以判断稳定掌握</span>}
      </div>
      {secondaryEvidence.length > 0 && <div className="evidence-secondary">{secondaryEvidence.join(" · ")}</div>}
    </div>
  );
}

export function CognitiveTimeline({ trace, compact = false }: { trace: CognitiveTrace; compact?: boolean }) {
  if (trace.rounds.length === 0) return <div className="timeline-empty">完成一轮教学后，这里会显示认知变化轨迹。</div>;
  const rounds = compact ? trace.rounds.slice(-4) : trace.rounds;
  return (
    <div className={`cognitive-timeline ${compact ? "timeline-compact" : ""}`}>
      <div className="timeline-heading"><span className="detail-label">认知变化轨迹</span><span>{trace.rounds.length} 轮</span></div>
      <div className="timeline-list">
        {rounds.map((round) => {
          const delta = strengthDelta(round);
          const keyLabel = timelineNodeLabel(round);
          const isKey = Boolean(keyLabel);
          const responsePreview = round.student_text.length > 76 ? `${round.student_text.slice(0, 76)}…` : round.student_text;
          return <div className={`timeline-node ${isKey ? "timeline-node-key" : "timeline-node-ordinary"}`} key={round.round}>
            <div className="timeline-marker"><b>R{round.round}</b><i /></div>
            <div className="timeline-content">
              <strong>{statusLabel(round.misconception_after?.status)}</strong>
              {keyLabel && <em>{keyLabel}</em>}
              <span>教师行为：{actionLabel(round.action_type)}</span>
              {(!compact || isKey) && <span>学生反应：{responsePreview}</span>}
              <span className={delta < 0 ? "delta-down" : ""}>强度 {round.misconception_after?.strength.toFixed(2) ?? "—"}{delta !== 0 ? `（${delta > 0 ? "+" : ""}${delta.toFixed(2)}）` : ""}</span>
            </div>
          </div>;
        })}
      </div>
    </div>
  );
}

export function CognitiveReport({ trace }: { trace?: CognitiveTrace }) {
  if (!trace) return <section className="cognitive-report"><span className="detail-label">本次教学中的认知变化</span><p className="fallback-copy">暂无该项分析</p></section>;
  const initial = trace.initial_misconception;
  const current = trace.current_misconception;
  return (
    <section className="cognitive-report">
      <div className="evaluation-header cognitive-report-header">
        <div><span className="section-kicker">过程证据</span><h3>本次教学中的认知变化</h3></div>
        <span className={`status-pill status-${current?.status ?? "unknown"}`}>{statusLabel(current?.status)}</span>
      </div>
      <div className="cognitive-summary-grid">
        <div><span>初始</span><strong>{statusLabel(initial?.status)}</strong><b>{initial?.strength.toFixed(2) ?? "—"}</b></div>
        <div><span>最终</span><strong>{statusLabel(current?.status)}</strong><b>{current?.strength.toFixed(2) ?? "—"}</b></div>
        <div><span>{current?.status === "corrected" ? "为什么认为已经掌握？" : "当前还缺什么？"}</span><ul className="cognitive-reason-list">{(current?.status === "corrected" ? masteryReasons(trace.rounds.at(-1)) : missingEvidence(trace)).map((item) => <li key={item}>{item}</li>)}</ul></div>
      </div>
      <div className="cognitive-next-advice"><span className="detail-label">下一步教学建议</span><p>{teachingAdvice(current?.status)}</p></div>
      <CognitiveStrengthChart trace={trace} />
      <CognitiveTimeline trace={trace} />
      <p className="cognitive-disclaimer">系统不会因为学生说出一次正确答案就认定已经掌握；以上结论来自多轮结构化证据。</p>
    </section>
  );
}

export function StateBar({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="state-bar">
      <div><span>{label}</span><strong>{formatPercent(value)}</strong></div>
      <div className="state-track"><i className={`state-fill state-${tone}`} style={{ width: `${value * 100}%` }} /></div>
    </div>
  );
}
