import { FormEvent,useEffect,useRef,useState } from 'react';
import {
statusDescription,
statusLabel
} from "./cognitiveVisualization";
import type { TeachingSession } from './types';

import { ApiError,jsonHeaders,requestJson } from './api';
import { CognitiveStatePanel,StateBar } from './CognitivePanels';
import { HistoryPanel } from './HistoryPanel';
import { profileTags } from './profile';
import { EvaluationPanel } from './Report';
export function Classroom({
  session,
  onSessionChange,
  onLeave,
  historyRevision = 0,
}: {
  session: TeachingSession;
  onSessionChange: (session: TeachingSession) => void;
  onLeave: () => void;
  historyRevision?: number;
}) {
  const draftKey = 'teaching-draft-' + session.id;
  const [teacherText, setTeacherText] = useState(() => localStorage.getItem(draftKey) ?? '');
  const pendingKey = 'teaching-pending-' + session.id;
  const pending = useRef<{text: string; id: string} | null>((() => {
    try { return JSON.parse(localStorage.getItem(pendingKey) ?? 'null'); } catch { return null; }
  })());
  useEffect(() => { localStorage.setItem(draftKey, teacherText); }, [draftKey, teacherText]);
  const [sending, setSending] = useState(false);
  const [ending, setEnding] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const dialogueListRef = useRef<HTMLDivElement>(null);
  const isCompleted = session.status !== "active";

  useEffect(() => {
    const dialogueList = dialogueListRef.current;
    if (!dialogueList || session.dialogue_records.length === 0) return;
    dialogueList.scrollTo({ top: dialogueList.scrollHeight, behavior: "smooth" });
  }, [session.dialogue_records.length]);

  const submitMessage = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = teacherText.trim();
    if (!text || sending || ending || isCompleted) return;
    setSending(true);
    setErrorMessage("");
    if (pending.current?.text !== text) pending.current = {text, id: crypto.randomUUID()};
    localStorage.setItem(pendingKey, JSON.stringify(pending.current));
    try {
      const updated = await requestJson<TeachingSession>(`/api/sessions/${session.id}/messages`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({ teacher_text: text, expected_version: session.version, request_id: pending.current!.id }),
      });
      setTeacherText("");
      pending.current = null;
      localStorage.removeItem(pendingKey);
      onSessionChange(updated);
    } catch (error: unknown) {
      setErrorMessage(error instanceof Error ? error.message : '消息发送失败');
      if (error instanceof ApiError && error.status === 409) {
        try { onSessionChange(await requestJson<TeachingSession>('/api/sessions/' + session.id)); setErrorMessage('已同步最新对话，草稿已保留，可以重新发送。'); } catch { /* preserve the draft */ }
      }
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
      setErrorMessage(error instanceof Error ? error.message : '结束实训失败');
      if (error instanceof ApiError && error.status === 409) {
        try { onSessionChange(await requestJson<TeachingSession>('/api/sessions/' + session.id)); } catch { /* preserve current view */ }
      }
    } finally {
      setEnding(false);
    }
  };

  if (isCompleted) {
    const current = session.cognitive_trace?.current_misconception;
    return (
      <section className="report-workspace">
        <div className="report-intro">
          <div><span className="section-kicker">本次练习已完成</span><h2>{session.scenario.topic} · {session.virtual_student.name}</h2><p>从学生的变化出发，找到下一次教学可以改进的一件事。</p></div>
          <button className="send-button" type="button" onClick={onLeave}>选择下一次实训 →</button>
        </div>
        <div className="report-highlights">
          <article><span className="detail-label">学生目前的理解</span><strong>{current ? statusLabel(current.status) : "暂无认知记录"}</strong><p>{current ? statusDescription(current.status) : "可以从完整对话中回顾学生的回答。"}</p></article>
          <article><span className="detail-label">优先复盘的问题</span><strong>{session.evaluation?.problems[0] ?? "评价尚未生成"}</strong><p>结合具体话语和学生回应，检查教学效果。</p></article>
          <article><span className="detail-label">下一次可以尝试</span><strong>{session.evaluation?.suggestions[0] ?? "回顾本次对话，寻找一次值得继续追问的回答。"}</strong></article>
        </div>
        <nav className="report-nav" aria-label="复盘内容"><a href="#review-details">详细复盘</a><a href="#review-dialogue">课堂对话</a><a href="#review-history">练习历史</a></nav>
        <div id="review-details">{session.evaluation ? <EvaluationPanel report={session.evaluation} behaviorSummary={session.behavior_summary} trace={session.cognitive_trace} /> : <p className="empty-state">本次实训已结束，暂未生成评价。你仍可查看完整对话。</p>}</div>
        <details className="report-transcript" id="review-dialogue">
          <summary>查看完整课堂对话 <span>{session.dialogue_records.filter(r => r.speaker === "teacher").length} 轮</span></summary>
          <div className="transcript-content">{session.dialogue_records.map(record => <article className={`dialogue-row message-${record.speaker}`} key={record.id}><span className="dialogue-speaker">{record.speaker === "teacher" ? "教师" : session.virtual_student.name}</span><div className="dialogue-bubble">{record.content}</div></article>)}</div>
        </details>
        <div id="review-history"><HistoryPanel refreshKey={`${session.id}:${historyRevision}`} onSessionSelect={onSessionChange} /></div>
      </section>
    );
  }

  return (
    <section className="session-shell">
      <div className="session-layout">
        <aside className="session-sidebar">
          <div className="session-panel student-summary">
            <span className={`avatar avatar-large avatar-${session.virtual_student.id}`}>{session.virtual_student.name.slice(-1)}</span>
            <span className="detail-label">当前虚拟学生</span>
            <h2>{session.virtual_student.name}</h2>
            <span className="profile-grade">{session.virtual_student.grade} · 虚拟学生</span>
            <div className="profile-tag-list session-profile-tags">
              {profileTags(session.virtual_student).map((tag) => <span key={tag}>{tag}</span>)}
            </div>
            <div className="student-traits">
              <span>学习风格</span>
              <p>{session.virtual_student.personality_description}</p>
            </div>
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
          <div ref={dialogueListRef} className="dialogue-list" aria-live="polite">
            {session.dialogue_records.length === 0 && (
              <div className="dialogue-empty">先用一句话开启课堂，例如：“请说说一次函数中 k 和 b 分别表示什么。”</div>
            )}
            {session.dialogue_records.map((record) => (
              <article className={`dialogue-row message-${record.speaker}`} key={record.id}>
                <span className="dialogue-speaker">{record.speaker === "teacher" ? "教师" : session.virtual_student.name}</span>
                <div className="dialogue-bubble">{record.content}</div>
              </article>
            ))}
          </div>
          {errorMessage && <div className="error-banner session-error">{errorMessage}</div>}
          <ResponseSource metadata={session.dialogue_records.filter(r => r.speaker === 'student').at(-1)?.response_metadata} />
          <form className="message-form" onSubmit={submitMessage}>
            <textarea
              aria-label="教师教学话语"
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
          <CognitiveStatePanel trace={session.cognitive_trace} />
          <div className="session-panel state-panel">
            <span className="detail-label">训练状态</span>
            <p className="state-hint">训练状态用于辅助观察，请结合学生的具体回答判断。</p>
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
        <EvaluationPanel report={session.evaluation} behaviorSummary={session.behavior_summary} trace={session.cognitive_trace} />
      )}
      {isCompleted && (
        <HistoryPanel refreshKey={session.id} />
      )}
    </section>
  );
}

function ResponseSource({metadata}: {metadata?: string | null}) {
  if (!metadata) return null;
  try { const value = JSON.parse(metadata); return <p className="runtime-status" role="status">{value.source === 'real' ? '本轮由真实模型生成' : value.source === 'mock' ? '本轮为离线模拟' : '模型回答未通过检查，本轮使用备用回答'}{value.retries ? ' · 已重试一次' : ''}</p>; } catch { return null; }
}
