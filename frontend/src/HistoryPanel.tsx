import { useEffect,useState } from 'react';
import { formatDate,formatScore,requestJson } from './api';
import { GrowthChart } from './Charts';
import type { HistoryItem,VirtualStudent,TeachingSession } from './types';

type Page = {items: HistoryItem[]; total: number; page: number; page_size: number};
export function HistoryPanel({refreshKey, onSessionSelect}: {refreshKey: number | string; onSessionSelect?: (session: TeachingSession) => void}) {
  const [page, setPage] = useState(1);
  const [student, setStudent] = useState('');
  const [version, setVersion] = useState('2');
  const [data, setData] = useState<Page>({items: [], total: 0, page: 1, page_size: 10});
  const [growth, setGrowth] = useState<HistoryItem[]>([]);
  const [students, setStudents] = useState<VirtualStudent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [opening, setOpening] = useState<number | null>(null);
  async function openReport(id: number) {
    setOpening(id);
    try { onSessionSelect?.(await requestJson<TeachingSession>(`/api/sessions/${id}`)); }
    catch (error) { setError(error instanceof Error ? error.message : '报告加载失败'); }
    finally { setOpening(null); }
  }
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    const filter = student ? `&student_id=${student}` : '';
    Promise.all([
      requestJson<Page>(`/api/sessions/history?page=${page}${filter}`),
      requestJson<HistoryItem[]>(`/api/sessions/growth?rubric_version=${version}${filter}`),
      requestJson<VirtualStudent[]>('/api/virtual-students'),
    ]).then(([history, recent, profiles]) => { if (active) { setData(history); setGrowth(recent.reverse()); setStudents(profiles); } })
      .catch(error => { if (active) setError(error instanceof Error ? error.message : '历史加载失败'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [page, student, version, refreshKey, retry]);
  return <section className="history-panel">
    <div className="evaluation-header"><div><span className="section-kicker">实训历史</span><h2>你的教学练习轨迹</h2></div><span>{data.total} 次已完成实训</span></div>
    <div className="history-toolbar"><label>筛选学生 <select value={student} onChange={event => {setStudent(event.target.value); setPage(1);}}><option value="">全部学生</option>{students.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label><label>曲线评分版本 <select value={version} onChange={event => setVersion(event.target.value)}><option value="2">第二版 · 证据评分</option><option value="1">第一版 · 历史评分</option></select></label></div>
    {loading ? <p role="status">正在加载历史记录…</p> : error ? <div className="error-banner" role="alert">{error} <button onClick={() => setRetry(value => value + 1)}>重新加载</button></div> : <>
      <p className="history-chart-caption">当前筛选下最近 {growth.length} 次练习 · 评分第 {version} 版</p>
      <GrowthChart items={growth} />
      {!data.items.length && <p>尚无符合条件的已完成实训。</p>}
      <div className="history-list">{data.items.map(item => <div className="history-row" key={item.id}><span>{formatDate(item.ended_at ?? item.started_at)}</span><strong>{onSessionSelect ? <button className="history-open" disabled={opening !== null} aria-label={`查看第 ${item.id} 次实训报告`} onClick={() => openReport(item.id)}>{opening === item.id ? '正在载入…' : item.topic}</button> : item.topic}</strong><span>{item.virtual_student_name} · 第 {item.rubric_version} 版</span><b>{formatScore(item.overall_score)}</b></div>)}</div>
      <nav className="history-pagination" aria-label="历史记录分页"><button disabled={page === 1} onClick={() => setPage(p => p-1)}>上一页</button><span role="status">第 {page} / {Math.max(1, Math.ceil(data.total / data.page_size))} 页 · 共 {data.total} 条</span><button disabled={page * data.page_size >= data.total} onClick={() => setPage(p => p+1)}>下一页</button></nav>
    </>}
  </section>;
}
