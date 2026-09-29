import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import type { ConnectionState,Scenario,TeachingSession,VirtualStudent } from './types';

import { ApiError,formatPercent,jsonHeaders,requestJson,SESSION_STORAGE_KEY } from './api';
import { LegacyImport,RuntimeStatus } from './RuntimeStatus';
const Classroom = lazy(() => import('./Classroom').then(module => ({ default: module.Classroom })));
const HistoryPanel = lazy(() => import('./HistoryPanel').then(module => ({ default: module.HistoryPanel })));
function App() {
  const [connectionState, setConnectionState] = useState<ConnectionState>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [students, setStudents] = useState<VirtualStudent[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<number | null>(null);
  const [selectedStudentId, setSelectedStudentId] = useState<number | null>(null);
  const [session, setSession] = useState<TeachingSession | null>(null);
  const [starting, setStarting] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyRevision, setHistoryRevision] = useState(0);
  const refreshHistory = () => setHistoryRevision(value => value + 1);
  const changeSession = (updated: TeachingSession) => {
    localStorage.setItem(SESSION_STORAGE_KEY, String(updated.id));
    setSession(updated);
  };

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
        <RuntimeStatus /><LegacyImport onImported={refreshHistory} /><header className="topbar">
          <div>
            <div className="eyebrow">师范生教学实训 · {session.status === "active" ? "模拟课堂" : "教学复盘"}</div>
            <h1>{session.status === "active" ? "模拟课堂" : "实训报告"}</h1>
          </div>
          <div className={`connection connection-${connectionState}`} aria-live="polite">
            <span className="connection-dot" />
            <span>{connectionText}</span>
          </div>
        </header>
        <Suspense fallback={<p role="status">正在载入课堂…</p>}><Classroom key={session.id} session={session} onSessionChange={changeSession} onLeave={leaveSession} historyRevision={historyRevision} /></Suspense>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <RuntimeStatus /><LegacyImport onImported={refreshHistory} />
      <header className="topbar">
        <div>
          <div className="eyebrow">师范生教学实训 · 选择课堂</div>
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
                  <div className="profile-tag-list">
                    {profileTags(selectedStudent).map((tag) => <span key={tag}>{tag}</span>)}
                  </div>
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
      {connectionState === 'ok' && <details className="report-transcript home-history" onToggle={event => setHistoryOpen(event.currentTarget.open)}>
        <summary>查看已完成的实训记录</summary>
        {historyOpen && <Suspense fallback={<p role="status">正在载入历史…</p>}><HistoryPanel refreshKey={historyRevision} onSessionSelect={changeSession} /></Suspense>}
      </details>}
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
function profileTags(student: VirtualStudent): string[] {
  const cautious = /谨慎|低自信|确认/.test(student.personality_description) || student.confidence < 0.5;
  return [
    cautious ? "较谨慎" : "表达较有信心",
    student.initiative < 0.5 ? "倾向确认" : "愿意主动表达",
    cautious ? "较少主动猜测" : "愿意尝试猜测",
  ];
}

export default App;
