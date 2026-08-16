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

export function hasStateChange(round: CognitiveTraceRound): boolean {
  return round.misconception_before?.status !== round.misconception_after?.status
    || Math.abs(strengthDelta(round)) >= 0.005;
}
