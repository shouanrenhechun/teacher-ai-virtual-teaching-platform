import type { CognitiveTrace } from './cognitiveVisualization';
export type ConnectionState = "loading" | "ok" | "error";

export type Scenario = {
  id: number;
  title: string;
  subject: string;
  grade: string;
  topic: string;
  teaching_goal: string;
  description: string;
};

export type KnowledgeState = {
  id: number;
  knowledge_point: string;
  mastery: number;
};

export type VirtualStudent = {
  id: number;
  name: string;
  grade: string;
  base_level: number;
  personality_description: string;
  initiative: number;
  confidence: number;
  knowledge_states: KnowledgeState[];
};

export type DialogueRecord = {
  id: number;
  session_id: number;
  speaker: "teacher" | "student" | string;
  content: string;
  sequence: number;
  timestamp: string;
  request_id: string | null;
  response_metadata: string | null;
};

export type SessionState = {
  understanding: number;
  confusion: number;
  engagement: number;
  confidence: number;
};

export type BehaviorSummary = {
  explanation_count: number;
  question_count: number;
  guided_question_count: number;
  example_count: number;
  feedback_count: number;
  correction_count: number;
  understanding_check_count: number;
  direct_answer_count: number;
  classroom_interaction_count: number;
  off_topic_count: number;
};

export type KeyTeachingSnippet = {
  round: number;
  action_type: string;
  teacher_text: string;
  student_text: string;
  evidence: string;
};

export type EvaluationReport = {
  rubric_version: number;
  evidence: {coverage?: number; independent_tasks?: number; dimensions?: Record<string, Array<{task: string; rounds?: number[]; reason?: string; checks: Array<boolean | {criterion: string; value: number; rounds: number[]; reason: string}>}>>};
  session_id: number;
  knowledge_accuracy: number | null;
  questioning: number | null;
  feedback: number | null;
  misconception_diagnosis: number | null;
  scaffolding: number | null;
  overall_score: number | null;
  summary: string;
  strengths: string[];
  problems: string[];
  suggestions: string[];
  key_teaching_snippets: KeyTeachingSnippet[];
  disclaimer: string;
  generated_at: string;
  analysis_source: string;
  analysis_error: string | null;
};

export type TeachingSession = {
  version: number;
  id: number;
  scenario_id: number;
  virtual_student_id: number;
  started_at: string;
  ended_at: string | null;
  status: "active" | "completed" | string;
  scenario: Scenario;
  virtual_student: VirtualStudent;
  dialogue_records: DialogueRecord[];
  state: SessionState;
  behavior_summary: BehaviorSummary;
  cognitive_trace?: CognitiveTrace;
  evaluation: EvaluationReport | null;
};

export type HistoryItem = {
  virtual_student_id: number;
  rubric_version: number;
  id: number;
  started_at: string;
  ended_at: string | null;
  status: string;
  scenario_id: number;
  topic: string;
  virtual_student_name: string;
  overall_score: number | null;
};
