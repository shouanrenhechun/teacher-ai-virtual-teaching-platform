import {
  hasStateChange,
  statusDescription,
  statusLabel,
  teachingAdvice,
} from "./src/cognitiveVisualization.ts";

const assert = (condition, message) => {
  if (!condition) throw new Error(message);
};

assert(statusLabel("weakening") === "错误认知开始动摇", "状态中文映射失败");
assert(statusDescription("corrected").includes("稳定理解"), "状态解释映射失败");
assert(teachingAdvice("provisional").includes("变式题"), "教学建议映射失败");
assert(
  hasStateChange({
    round: 1,
    teacher_text: "",
    student_text: "",
    action_type: null,
    state_before: { understanding: 0.5, confusion: 0.3, engagement: 0.4, confidence: 0.4, surface_recall: 0 },
    state_after: { understanding: 0.5, confusion: 0.3, engagement: 0.4, confidence: 0.4, surface_recall: 0 },
    misconception_before: { strength: 0.8, status: "active" },
    misconception_after: { strength: 0.7, status: "weakening" },
    evidence: null,
    correction_opportunity: { correction_opportunity: true, opportunity_strength: 0.7 },
    prompt_mode: "conflicted",
  }),
  "状态变化识别失败",
);
