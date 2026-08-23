export type CognitiveStatus = "active" | "weakening" | "provisional" | "corrected" | string;

export type CognitiveState = {
  understanding: number;
  confusion: number;
  engagement: number;
  confidence: number;
  surface_recall: number;
};

export type CognitiveMisconception = {
  name: string;
  concept: string;
  description: string;
  semantic_type: string;
  strength: number;
  status: CognitiveStatus;
  triggered: boolean;
  correction_started: boolean;
  corrected: boolean;
  stable_correct_evidence_count: number;
  transfer_evidence: number;
};

export type StudentResponseEvidence = {
  states_correct_conclusion: boolean;
  conclusion_level: string;
  explains_reason_correctly: boolean;
  shows_residual_misconception: boolean;
  shows_uncertainty: boolean;
  linguistic_hedging: boolean;
  conceptual_uncertainty: boolean;
  knowledge_precision: string;
  evidence_insufficient: boolean;
  parrots_teacher: boolean;
  transfer_success: boolean;
  evidence_level: number;
};

export type CognitiveTraceRound = {
  round: number;
  teacher_text: string;
  student_text: string;
  action_type: string | null;
  state_before: CognitiveState;
  state_after: CognitiveState;
  misconception_before: CognitiveMisconception | null;
  misconception_after: CognitiveMisconception | null;
  evidence: StudentResponseEvidence | null;
  correction_opportunity: { correction_opportunity: boolean; opportunity_strength: number };
  prompt_mode: string | null;
};

export type CognitiveTrace = {
  initial_state: CognitiveState;
  initial_misconception: CognitiveMisconception | null;
  current_state: CognitiveState;
  current_misconception: CognitiveMisconception | null;
  rounds: CognitiveTraceRound[];
};

const STATUS_LABELS: Record<string, string> = {
  active: "错误认知稳定",
  weakening: "错误认知开始动摇",
  provisional: "初步形成正确理解",
  corrected: "已形成稳定理解",
};

const ACTION_LABELS: Record<string, string> = {
  explanation: "讲解",
  question: "提问",
  guided_question: "引导式提问",
  example: "举例",
  feedback: "反馈",
  correction: "纠错",
  understanding_check: "理解确认",
  direct_answer: "直接给出答案",
  classroom_interaction: "课堂互动",
  off_topic: "非教学话题",
};

export function statusLabel(status: CognitiveStatus | null | undefined): string {
  return status ? STATUS_LABELS[status] ?? "认知状态记录" : "暂无状态记录";
}

export function actionLabel(action: string | null | undefined): string {
  return action ? ACTION_LABELS[action] ?? action : "教学行为未记录";
}

export function statusDescription(status: CognitiveStatus | null | undefined): string {
  switch (status) {
    case "active":
      return "学生仍较确信原有想法，适合继续暴露认知冲突。";
    case "weakening":
      return "学生开始注意到原有想法与例子之间的冲突。";
    case "provisional":
      return "学生大体理解正确，但还需要新的变式来确认稳定性。";
    case "corrected":
      return "学生已用独立解释和迁移证据表现出稳定理解。";
    default:
      return "当前暂无足够的认知过程分析。";
  }
}

export function teachingAdvice(status: CognitiveStatus | null | undefined): string {
  switch (status) {
    case "active":
      return "建议继续用对比或具体例子暴露认知冲突，不宜马上进入复杂迁移。";
    case "weakening":
      return "建议要求学生解释关键变量之间的关系，帮助其把冲突说清楚。";
    case "provisional":
      return "建议使用新的变式题检查理解是否稳定，避免只停留在复述结论。";
    case "corrected":
      return "当前错误认知已基本纠正，可以进入更复杂的应用练习。";
    default:
      return "暂无下一步教学建议。";
  }
}

export function strengthDelta(round: CognitiveTraceRound): number {
  const before = round.misconception_before?.strength ?? 0;
  const after = round.misconception_after?.strength ?? before;
  return Number((after - before).toFixed(4));
}

export function strengthInterpretation(value: number): string {
  if (value >= 0.7) return "错误认知仍较牢固";
  if (value >= 0.35) return "错误认知正在减弱";
  return "错误认知较弱";
}

export function strengthChangeLabel(before: number, after: number): string {
  const delta = after - before;
  if (delta <= -0.03) return "错误认知明显减弱";
  if (delta >= 0.03) return "错误认知进一步强化";
  return "错误认知暂时没有明显变化";
}

export function masteryReasons(round?: CognitiveTraceRound): string[] {
  if (!round?.evidence) return [];
  const evidence = round.evidence;
  const reasons: string[] = [];
  if (evidence.explains_reason_correctly) reasons.push("能独立说明关键关系");
  if (evidence.transfer_success) reasons.push("能在新题中完成迁移");
  if (!evidence.shows_residual_misconception && evidence.states_correct_conclusion) {
    reasons.push("最近回答未再表现原有错误认知");
  }
  if (round.misconception_after?.stable_correct_evidence_count && round.misconception_after.stable_correct_evidence_count > 1) {
    reasons.push("连续获得了正确理解证据");
  }
  return reasons.slice(0, 3);
}

export function missingEvidence(trace: CognitiveTrace): string[] {
  const current = trace.current_misconception;
  const latest = trace.rounds.at(-1);
  if (!current) return ["完成一轮教学后再观察学生的认知证据"];
  if (current.status === "corrected") return masteryReasons(latest);
  const evidence = latest?.evidence;
  const missing: string[] = [];
  if (current.status === "active") {
    missing.push("先让学生说出当前判断依据");
    missing.push("用对比或例子建立认知冲突");
  } else {
    if (!evidence?.explains_reason_correctly) missing.push("需要学生说明关键关系，而不只是复述结论");
    if (evidence?.shows_residual_misconception || current.status === "weakening") missing.push("还需检查原有错误认知是否真正消退");
    if ((current.transfer_evidence ?? 0) < 1) missing.push("再完成一次新的变式迁移");
    if ((current.stable_correct_evidence_count ?? 0) < 2) missing.push("再获得一次独立且稳定的正确解释");
  }
  return missing.slice(0, 3);
}

export function timelineNodeLabel(round: CognitiveTraceRound): string | null {
  const before = round.misconception_before;
  const after = round.misconception_after;
  if (before?.status !== after?.status) return `状态：${statusLabel(after?.status)}`;
  if (round.evidence?.transfer_success) return "迁移成功";
  if ((after?.stable_correct_evidence_count ?? 0) > (before?.stable_correct_evidence_count ?? 0)) return "获得稳定证据";
  if (hasStateChange(round)) return strengthChangeLabel(before?.strength ?? 0, after?.strength ?? 0);
  return null;
}

export function hasStateChange(round: CognitiveTraceRound): boolean {
  return round.misconception_before?.status !== round.misconception_after?.status
    || Math.abs(strengthDelta(round)) >= 0.005;
}
