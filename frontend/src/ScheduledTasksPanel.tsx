import { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import { useI18n } from './i18n';
import type { PendingReminder, Project } from './types';

export default function ScheduledTasksPanel({ projects, onClose }: { projects: Project[]; onClose: () => void }) {
  const { lang } = useI18n();
  const [tasks, setTasks] = useState<PendingReminder[] | null>(null);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let active = true;
    setError('');
    Promise.all(projects.map((project) => api.listPendingReminders(project.id)))
      .then((lists) => { if (active) setTasks(lists.flat().sort((a, b) => a.wake_ts - b.wake_ts)); })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : String(err)); });
    return () => { active = false; };
  }, [projects, revision]);
  useEffect(() => {
    const timer = setInterval(refresh, 15000);
    return () => clearInterval(timer);
  }, [refresh]);
  return <div className="modal-backdrop settings-backdrop">
    <div className="modal global-settings" role="dialog" aria-modal="true" aria-label={lang === 'zh' ? '定时任务' : 'Scheduled tasks'}>
      <div className="modal-head">
        <button type="button" className="settings-back" aria-label={lang === 'zh' ? '返回聊天' : 'Back to chat'} onClick={onClose}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="m10 5-7 7 7 7M3 12h18" /></svg></button>
        <span className="modal-title">{lang === 'zh' ? '定时任务' : 'Scheduled tasks'}</span>
        <button type="button" className="btn ghost sm scheduled-refresh" onClick={refresh}>{lang === 'zh' ? '刷新' : 'Refresh'}</button>
      </div>
      <div className="scheduled-content">
        {error ? <p role="alert">{error}</p> : tasks === null ? <p>{lang === 'zh' ? '加载中…' : 'Loading…'}</p> : tasks.length === 0 ? <div className="scheduled-empty"><h2>{lang === 'zh' ? '暂无定时任务' : 'No scheduled tasks'}</h2><p>{lang === 'zh' ? '已设置的定时提醒和唤醒任务会显示在这里。' : 'Scheduled reminders and wakeups will appear here.'}</p></div> : <div className="scheduled-list">
          {tasks.map((task) => <article key={`${task.project_id}:${task.schedule_id}`} className="scheduled-task">
            <div><strong>{task.message}</strong><small>{projects.find((project) => project.id === task.project_id)?.name ?? task.project_id}</small></div>
            <time dateTime={new Date(task.wake_ts * 1000).toISOString()}>{new Date(task.wake_ts * 1000).toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US', { timeZone: 'Asia/Shanghai' })}</time>
          </article>)}
        </div>}
      </div>
    </div>
  </div>;
}
