import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { LineChart as EChartsLineChart, RadarChart as EChartsRadarChart } from "echarts/charts";
import { GridComponent, RadarComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([EChartsLineChart, EChartsRadarChart, GridComponent, RadarComponent, TooltipComponent, CanvasRenderer]);

type ConnectionState = "loading" | "ok" | "error";

type Scenario = {
  id: number;
  title: string;
  subject: string;
  grade: string;
  topic: string;
  teaching_goal: string;
  description: string;
};

type KnowledgeState = {
  id: number;
  knowledge_point: string;
  mastery: number;
};

type VirtualStudent = {
  id: number;
  name: string;
  grade: string;
  base_level: number;
  personality_description: string;
  initiative: number;
  confidence: number;
  knowledge_states: KnowledgeState[];
};

type DialogueRecord = {
  id: number;
  session_id: number;
  speaker: "teacher" | "student" | string;
  content: string;
  sequence: number;
  timestamp: string;
};

type SessionState = {
  understanding: number;
  confusion: number;
  engagement: number;
  confidence: number;
};

type BehaviorSummary = {
  explanation_count: number;
  question_count: number;
  guided_question_count: number;
  example_count: number;
  feedback_count: number;
  correction_count: number;
  understanding_check_count: number;
  direct_answer_count: number;
};

type KeyTeachingSnippet = {
  round: number;
  action_type: string;
  teacher_text: string;
  student_text: string;
  evidence: string;
};

type EvaluationReport = {
  session_id: number;
  knowledge_accuracy: number;
  questioning: number;
  feedback: number;
  misconception_diagnosis: number;
  scaffolding: number;
  overall_score: number;
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

type TeachingSession = {
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
  evaluation: EvaluationReport | null;
};

type HistoryItem = {
  id: number;
  started_at: string;
  ended_at: string | null;
  status: string;
  scenario_id: number;
  topic: string;
  virtual_student_name: string;
  overall_score: number | null;
};

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const SESSION_STORAGE_KEY = "teaching-session-id";

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new Error("网络连接失败，请确认后端正在 8000 端口运行。");
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : `请求失败（HTTP ${response.status}）`;
    throw new ApiError(detail, response.status);
  }
  return payload as T;
}

function jsonHeaders() {
  return { "Content-Type": "application/json" };
}

function App() {
  const [connectionState, setConnectionState] = useState<ConnectionState>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [students, setStudents] = useState<VirtualStudent[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<number | null>(null);
  const [selectedStudentId, setSelectedStudentId] = useState<number | null>(null);
  const [session, setSession] = useState<TeachingSession | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    let active = true;

    Promise.all([
      requestJson<{ status?: string }>("/api/health"),
      requestJson<Scenario[]>("/api/scenarios"),
      requestJson<VirtualStudent[]>("/api/virtual-students"),
    ])
      .then(async ([health, scenarioData, studentData]) => {
        if (health.status !== "ok") throw new Error("健康检查返回内容异常");
        if (!active) return;

        setScenarios(scenarioData);
        setStudents(studentData);
        setSelectedScenarioId(scenarioData[0]?.id ?? null);
        setSelectedStudentId(studentData[0]?.id ?? null);

        const storedSessionId = window.localStorage.getItem(SESSION_STORAGE_KEY);
        if (storedSessionId) {
          try {
            const restored = await requestJson<TeachingSession>(`/api/sessions/${storedSessionId}`);
            if (active) {
              setSession(restored);
              setSelectedScenarioId(restored.scenario_id);
              setSelectedStudentId(restored.virtual_student_id);
            }
          } catch (error: unknown) {
            if (error instanceof ApiError && error.status === 404) {
              window.localStorage.removeItem(SESSION_STORAGE_KEY);
            } else {
              throw error;
            }
          }
        }
        if (active) setConnectionState("ok");
      })
      .catch((error: unknown) => {
        if (!active) return;
        setConnectionState("error");
        setErrorMessage(error instanceof Error ? error.message : "无法连接后端");
      });

    return () => {
      active = false;
    };
  }, []);

  const selectedScenario = useMemo(
    () => scenarios.find((scenario) => scenario.id === selectedScenarioId) ?? scenarios[0],
    [scenarios, selectedScenarioId],
  );
  const selectedStudent = useMemo(
    () => students.find((student) => student.id === selectedStudentId) ?? students[0],
    [students, selectedStudentId],
  );

  const startSession = async () => {
    if (!selectedScenario || !selectedStudent || starting || session) return;
    setStarting(true);
    setErrorMessage("");
    try {
      const created = await requestJson<TeachingSession>("/api/sessions", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({ scenario_id: selectedScenario.id, virtual_student_id: selectedStudent.id }),
      });
      window.localStorage.setItem(SESSION_STORAGE_KEY, String(created.id));
      setSession(created);
    } catch (error: unknown) {
      setErrorMessage(error instanceof Error ? error.message : "创建实训失败");
    } finally {
      setStarting(false);
    }
  };

  const leaveSession = () => {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    setSession(null);
    setErrorMessage("");
  };

  const connectionText = {
    loading: "正在同步教学案例…",
    ok: "后端连接正常",
    error: "后端连接异常",
  }[connectionState];

  if (session) {
    return (
      <main className="app-shell">
        <header className="topbar">
          <div>
            <div className="eyebrow">AI TEACHING PRACTICE · MODULE 08</div>
            <h1>{session.status === "active" ? "模拟课堂" : "实训报告"}</h1>
          </div>
          <div className={`connection connection-${connectionState}`} aria-live="polite">
            <span className="connection-dot" />
            <span>{connectionText}</span>
          </div>
        </header>
        <Classroom session={session} onSessionChange={setSession} onLeave={leaveSession} />
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">AI TEACHING PRACTICE · MODULE 05</div>
          <h1>选择你的教学实训案例</h1>
        </div>
        <div className={`connection connection-${connectionState}`} aria-live="polite">
          <span className="connection-dot" />
          <span>{connectionText}</span>
          {connectionState === "error" && <small>{errorMessage}</small>}
        </div>
      </header>

      {connectionState === "error" ? (
        <section className="empty-state">
          <span className="empty-icon">!</span>
          <h2>暂时无法载入实训案例</h2>
          <p>{errorMessage} 请确认后端运行在 8000 端口。</p>
        </section>
      ) : connectionState === "loading" ? (
        <section className="empty-state loading-state" aria-live="polite">
          <span className="empty-icon loading-icon">…</span>
          <h2>正在载入实训案例</h2>
          <p>正在同步教学场景和虚拟学生画像，请稍候。</p>
        </section>
      ) : (
        <div className="workspace-grid">
          <section className="content-column">
            <div className="section-heading">
              <div>
                <span className="section-kicker">01 / 教学场景</span>
                <h2>实训场景列表</h2>
              </div>
              <span className="count-badge">{scenarios.length} 个案例</span>
            </div>
            <div className="scenario-list">
              {scenarios.map((scenario) => (
                <button
                  className={`scenario-card ${selectedScenario?.id === scenario.id ? "is-selected" : ""}`}
                  key={scenario.id}
                  type="button"
                  onClick={() => setSelectedScenarioId(scenario.id)}
                >
                  <span className="scenario-number">案例 {String(scenario.id).padStart(2, "0")}</span>
                  <strong>{scenario.title}</strong>
                  <span className="scenario-meta">{scenario.subject} · {scenario.grade} · {scenario.topic}</span>
                  <span className="scenario-arrow">→</span>
                </button>
              ))}
            </div>

            {selectedScenario && (
              <article className="scenario-detail">
                <div className="detail-label">场景详情</div>
                <h2>{selectedScenario.title}</h2>
                <p>{selectedScenario.description}</p>
                <div className="goal-box">
                  <span className="goal-icon">◎</span>
                  <div>
                    <span className="detail-label">本次教学目标</span>
                    <p>{selectedScenario.teaching_goal}</p>
                  </div>
                </div>
              </article>
            )}

            <div className="section-heading student-heading">
              <div>
                <span className="section-kicker">02 / 虚拟学生</span>
                <h2>选择一位学生</h2>
              </div>
              <span className="muted-note">核心画像已准备就绪</span>
            </div>
            <div className="student-list">
              {students.map((student, index) => (
                <button
                  className={`student-card ${selectedStudent?.id === student.id ? "is-selected" : ""}`}
                  key={student.id}
                  type="button"
                  onClick={() => setSelectedStudentId(student.id)}
                >
                  <span className={`avatar avatar-${index + 1}`}>{student.name.slice(-1)}</span>
                  <span className="student-card-copy">
                    <strong>{student.name}</strong>
                    <span>{student.personality_description}</span>
                  </span>
                  <span className="student-level">基础 {formatPercent(student.base_level)}</span>
                  <span className="select-mark">{selectedStudent?.id === student.id ? "✓" : ""}</span>
                </button>
              ))}
            </div>
          </section>

          <aside className="profile-panel">
            {selectedStudent ? (
              <>
                <div className="profile-header">
                  <span className={`avatar avatar-large avatar-${selectedStudent.id}`}>{selectedStudent.name.slice(-1)}</span>
                  <div>
                    <span className="detail-label">当前选择</span>
                    <h2>{selectedStudent.name}</h2>
                    <span className="profile-grade">{selectedStudent.grade} · 虚拟学生</span>
                  </div>
                </div>
                <div className="profile-stats">
                  <ProfileBar label="基础水平" value={selectedStudent.base_level} />
                  <ProfileBar label="学习主动性" value={selectedStudent.initiative} />
                  <ProfileBar label="表达信心" value={selectedStudent.confidence} />
                </div>
                <div className="profile-section">
                  <span className="detail-label">性格特点</span>
                  <p>{selectedStudent.personality_description}</p>
                </div>
                <div className="profile-section">
                  <span className="detail-label">已掌握内容</span>
                  <div className="tag-list">
                    {selectedStudent.knowledge_states.filter((item) => item.mastery >= 0.6).map((item) => (
                      <span className="tag tag-good" key={item.id}>✓ {item.knowledge_point}</span>
                    ))}
                  </div>
                </div>
                <div className="profile-section">
                  <span className="detail-label">薄弱内容</span>
                  <div className="tag-list">
                    {selectedStudent.knowledge_states.filter((item) => item.mastery < 0.6).map((item) => (
                      <span className="tag tag-weak" key={item.id}>· {item.knowledge_point}</span>
                    ))}
                  </div>
                </div>
                <div className="privacy-note">
                  <span>◇</span>
                  <p>学生的具体认知错误会在实训对话中自然呈现，不会提前展示。</p>
                </div>
                {errorMessage && <div className="error-banner">{errorMessage}</div>}
                <button className="start-button" type="button" onClick={startSession} disabled={starting}>
                  {starting ? "正在创建实训…" : `选择 ${selectedStudent.name}，开始实训`}
                </button>
              </>
            ) : (
              <div className="loading-profile">正在加载学生画像…</div>
            )}
          </aside>
        </div>
      )}
    </main>
  );
}

function ProfileBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{formatPercent(value)}</strong>
      <div className="progress-track"><i style={{ width: `${value * 100}%` }} /></div>
    </div>
  );
}

function Classroom({
  session,
  onSessionChange,
  onLeave,
}: {
  session: TeachingSession;
  onSessionChange: (session: TeachingSession) => void;
  onLeave: () => void;
}) {
  const [teacherText, setTeacherText] = useState("");
  const [sending, setSending] = useState(false);
  const [ending, setEnding] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const dialogueEndRef = useRef<HTMLDivElement>(null);
  const isCompleted = session.status !== "active";

  useEffect(() => {
    dialogueEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session.dialogue_records.length]);

  useEffect(() => {
    if (!isCompleted) return;
    let active = true;
    setHistoryLoading(true);
    setHistoryError("");
    requestJson<HistoryItem[]>("/api/sessions/history")
      .then((items) => {
        if (active) setHistory(items);
      })
      .catch((error: unknown) => {
        if (active) setHistoryError(error instanceof Error ? error.message : "实训历史加载失败");
      })
      .finally(() => {
        if (active) setHistoryLoading(false);
      });
    return () => {
      active = false;
    };
  }, [isCompleted, session.id]);

  const submitMessage = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = teacherText.trim();
    if (!text || sending || ending || isCompleted) return;
    setSending(true);
    setErrorMessage("");
    try {
      const updated = await requestJson<TeachingSession>(`/api/sessions/${session.id}/messages`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({ teacher_text: text }),
      });
      setTeacherText("");
      onSessionChange(updated);
    } catch (error: unknown) {
      setErrorMessage(error instanceof Error ? error.message : "消息发送失败");
    } finally {
      setSending(false);
    }
  };

  const finishSession = async () => {
    if (ending || sending || isCompleted) return;
    setEnding(true);
    setErrorMessage("");
    try {
      const updated = await requestJson<TeachingSession>(`/api/sessions/${session.id}/end`, { method: "POST" });
      onSessionChange(updated);
    } catch (error: unknown) {
      setErrorMessage(error instanceof Error ? error.message : "结束实训失败");
    } finally {
      setEnding(false);
    }
  };

  return (
    <section className="session-shell">
      <div className="session-layout">
        <aside className="session-sidebar">
          <div className="session-panel student-summary">
            <span className={`avatar avatar-large avatar-${session.virtual_student.id}`}>{session.virtual_student.name.slice(-1)}</span>
            <span className="detail-label">当前虚拟学生</span>
            <h2>{session.virtual_student.name}</h2>
            <span className="profile-grade">{session.virtual_student.grade} · {session.virtual_student.personality_description}</span>
          </div>
          <div className="session-panel topic-summary">
            <span className="detail-label">教学主题</span>
            <h2>{session.scenario.topic}</h2>
            <p>{session.scenario.subject} · {session.scenario.grade}</p>
            <span className="detail-label">教学目标</span>
            <p>{session.scenario.teaching_goal}</p>
          </div>
        </aside>

        <section className="session-panel session-main">
          <div className="session-main-header">
            <div>
              <span className="section-kicker">课堂对话</span>
              <h2>{isCompleted ? "本次实训已结束" : "开始你的教学引导"}</h2>
            </div>
            <span className={`status-pill ${isCompleted ? "status-completed" : "status-active"}`}>
              {isCompleted ? "已完成" : "进行中"}
            </span>
          </div>
          <div className="dialogue-list" aria-live="polite">
            {session.dialogue_records.length === 0 && (
              <div className="dialogue-empty">先用一句话开启课堂，例如：“请说说一次函数中 k 和 b 分别表示什么。”</div>
            )}
            {session.dialogue_records.map((record) => (
              <article className={`dialogue-row message-${record.speaker}`} key={record.id}>
                <span className="dialogue-speaker">{record.speaker === "teacher" ? "教师" : session.virtual_student.name}</span>
                <div className="dialogue-bubble">{record.content}</div>
              </article>
            ))}
            <div ref={dialogueEndRef} />
          </div>
          {errorMessage && <div className="error-banner session-error">{errorMessage}</div>}
          <form className="message-form" onSubmit={submitMessage}>
            <textarea
              className="message-input"
              value={teacherText}
              onChange={(event) => setTeacherText(event.target.value)}
              placeholder={isCompleted ? "本次实训已结束" : "输入你的教学话语…"}
              maxLength={4000}
              disabled={isCompleted || sending || ending}
              rows={3}
            />
            <div className="message-form-footer">
              <span className="muted-note">{teacherText.length}/4000</span>
              <button className="send-button" type="submit" disabled={isCompleted || sending || ending || !teacherText.trim()}>
                {sending ? "学生思考中…" : "发送给学生 →"}
              </button>
            </div>
          </form>
        </section>

        <aside className="session-sidebar session-right-sidebar">
          <div className="session-panel state-panel">
            <span className="detail-label">训练状态</span>
            <p className="state-hint">仅展示课堂反馈指标，不显示学生的内部认知错误。</p>
            <StateBar label="理解度" value={session.state.understanding} tone="green" />
            <StateBar label="困惑度" value={session.state.confusion} tone="orange" />
            <StateBar label="参与度" value={session.state.engagement} tone="blue" />
            <StateBar label="表达信心" value={session.state.confidence} tone="purple" />
          </div>
          <div className="session-actions">
            <button className="end-button" type="button" onClick={finishSession} disabled={isCompleted || sending || ending}>
              {ending ? "正在结束…" : "结束实训"}
            </button>
            {isCompleted && <button className="back-button" type="button" onClick={onLeave}>返回案例选择</button>}
          </div>
        </aside>
      </div>
      {session.evaluation && (
        <EvaluationPanel report={session.evaluation} behaviorSummary={session.behavior_summary} />
      )}
      {isCompleted && (
        <HistoryPanel items={history} loading={historyLoading} error={historyError} />
      )}
    </section>
  );
}

function EvaluationPanel({ report, behaviorSummary }: { report: EvaluationReport; behaviorSummary: BehaviorSummary }) {
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
        <div className="evaluation-total"><strong>{report.overall_score}</strong><span>/ 100</span></div>
      </div>
      <div className="evaluation-scores">
        {dimensions.map(([label, score]) => (
          <div className="evaluation-score" key={label}>
            <div><span>{label}</span><strong>{score}</strong></div>
            <div className="state-track"><i className="state-fill state-green" style={{ width: `${score}%` }} /></div>
          </div>
        ))}
      </div>
      <RadarChart report={report} />
      <p className="evaluation-summary">{report.summary}</p>
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
              <strong>第 {snippet.round} 轮 · {snippet.action_type}</strong>
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

function RadarChart({ report }: { report: EvaluationReport }) {
  const chartRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!chartRef.current) return;
    const chart = echarts.init(chartRef.current);
    chart.setOption({
      animation: false,
      tooltip: { trigger: "item" },
      radar: {
        indicator: [
          { name: "知识准确性", max: 100 },
          { name: "提问与引导", max: 100 },
          { name: "教学反馈", max: 100 },
          { name: "错误诊断", max: 100 },
          { name: "支架式教学", max: 100 },
        ],
        splitNumber: 4,
        axisName: { color: "#56746e", fontSize: 12 },
        splitArea: { areaStyle: { color: ["#fbfdfc", "#f5faf8"] } },
        splitLine: { lineStyle: { color: "#d9ebe5" } },
        axisLine: { lineStyle: { color: "#d9ebe5" } },
      },
      series: [{
        type: "radar",
        data: [{
          value: [
            report.knowledge_accuracy,
            report.questioning,
            report.feedback,
            report.misconception_diagnosis,
            report.scaffolding,
          ],
          name: "本次实训",
          symbol: "circle",
          symbolSize: 5,
          lineStyle: { color: "#0f766e", width: 2 },
          itemStyle: { color: "#0f766e" },
          areaStyle: { color: "rgba(76, 174, 153, .25)" },
        }],
      }],
    });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [report]);
  return <div className="radar-chart" ref={chartRef} aria-label="五维能力雷达图" />;
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

function HistoryPanel({ items, loading, error }: { items: HistoryItem[]; loading: boolean; error: string }) {
  return (
    <section className="history-panel">
      <div className="evaluation-header">
        <div>
          <span className="section-kicker">实训历史</span>
          <h2>你的教学练习轨迹</h2>
        </div>
        <span className="muted-note">{items.length} 次已完成实训</span>
      </div>
      {loading && <p className="history-empty">正在加载历史记录…</p>}
      {error && <p className="error-banner">{error}</p>}
      {!loading && !error && items.length === 0 && <p className="history-empty">完成第一次实训后，这里会出现你的练习记录。</p>}
      {!loading && !error && items.length > 0 && (
        <>
          {items.length > 1 && <GrowthChart items={items} />}
          <div className="history-list">
            {items.slice().reverse().map((item) => (
              <div className="history-row" key={item.id}>
                <span>{formatDate(item.started_at)}</span>
                <strong>{item.topic}</strong>
                <span>{item.virtual_student_name}</span>
                <b>{item.overall_score === null ? "—" : item.overall_score}</b>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function GrowthChart({ items }: { items: HistoryItem[] }) {
  const chartRef = useRef<HTMLDivElement>(null);
  const scoredItems = items.filter((item): item is HistoryItem & { overall_score: number } => item.overall_score !== null);
  useEffect(() => {
    if (!chartRef.current || scoredItems.length < 2) return;
    const chart = echarts.init(chartRef.current);
    chart.setOption({
      animation: false,
      tooltip: { trigger: "axis" },
      grid: { left: 42, right: 20, top: 20, bottom: 32 },
      xAxis: { type: "category", data: scoredItems.map((item) => formatDate(item.started_at)), axisLabel: { color: "#78908b" } },
      yAxis: { type: "value", min: 0, max: 100, axisLabel: { color: "#78908b" }, splitLine: { lineStyle: { color: "#edf3f0" } } },
      series: [{ type: "line", data: scoredItems.map((item) => item.overall_score), smooth: false, symbol: "circle", symbolSize: 7, lineStyle: { color: "#0f766e", width: 2 }, itemStyle: { color: "#0f766e" }, areaStyle: { color: "rgba(76, 174, 153, .12)" } }],
    });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => { window.removeEventListener("resize", resize); chart.dispose(); };
  }, [items, scoredItems.length]);
  return scoredItems.length > 1 ? <div className="growth-chart" ref={chartRef} aria-label="实训总分成长曲线" /> : null;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(new Date(value));
}

function EvaluationList({ title, items, className }: { title: string; items: string[]; className: string }) {
  return (
    <div className={`evaluation-list ${className}`}>
      <span className="detail-label">{title}</span>
      <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function StateBar({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="state-bar">
      <div><span>{label}</span><strong>{formatPercent(value)}</strong></div>
      <div className="state-track"><i className={`state-fill state-${tone}`} style={{ width: `${value * 100}%` }} /></div>
    </div>
  );
}

export default App;
