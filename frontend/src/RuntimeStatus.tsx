import { useEffect, useState } from 'react';
import { requestJson } from './api';

export function RuntimeStatus() {
  const [label, setLabel] = useState('正在读取运行模式…');
  useEffect(() => {
    let active = true;
    requestJson<{mode: string; model_configuration: string}>('/api/health').then(data => {
      if (active) setLabel(`${data.mode === 'mock' ? '离线模拟 Mock' : '真实模型 Real'} · ${data.model_configuration === 'ready' ? '已配置' : '配置待完善'}`);
    }).catch(() => { if (active) setLabel('暂时无法读取运行模式'); });
    return () => { active = false; };
  }, []);
  return <p className="runtime-status" role="status">{label}</p>;
}

export function LegacyImport({onImported}: {onImported?: () => void}) {
  const [count, setCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => { let active = true; requestJson<{count: number}>('/api/sessions/legacy-count').then(data => { if (active) setCount(data.count); }).catch(() => {}); return () => { active = false; }; }, []);
  async function importRecords() {
    setBusy(true);
    try { const result = await requestJson<{imported: number}>('/api/sessions/import-legacy', {method: 'POST'}); setCount(0); setMessage(`已导入 ${result.imported} 条旧记录。可在实训历史中查看报告，选择原来的课堂和学生可以继续未完成实训。`); onImported?.(); }
    catch (error) { setMessage(error instanceof Error ? error.message : '导入失败'); }
    finally { setBusy(false); }
  }
  if (!count && !message) return null;
  return <section className="legacy-import">{count > 0 && <><p>本机有 {count} 条旧记录尚未归属。导入后由当前浏览器继续管理，原报告分数保留。</p><button type="button" disabled={busy} onClick={importRecords}>{busy ? '正在导入…' : '将旧记录导入当前浏览器'}</button></>}<p role="status">{message}</p></section>;
}
