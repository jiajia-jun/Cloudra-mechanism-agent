import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import type { CodexAuthStatus, CodexDeviceLogin } from './types';

export default function CodexAuthPanel({
  onToast,
}: {
  onToast: (kind: 'ok' | 'error', text: string) => void;
}) {
  const [status, setStatus] = useState<CodexAuthStatus | null>(null);
  const [login, setLogin] = useState<CodexDeviceLogin | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    let cancelled = false;
    api.codexAuthStatus().then((result) => {
      if (!cancelled) setStatus(result);
    }).catch((e: unknown) => {
      if (!cancelled) setError(e instanceof Error ? e.message : String(e));
    });
    return () => { cancelled = true; mounted.current = false; };
  }, []);

  useEffect(() => {
    if (!login) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const intervalMs = Math.max(1000, login.interval * 1000);

    async function poll() {
      if (cancelled) return;
      if (Date.now() / 1000 >= login!.expires_at) {
        setError('授权码已过期，请重新登录。');
        setLogin(null);
        return;
      }
      try {
        const result = await api.pollCodexLogin(login!.login_id);
        if (cancelled) return;
        if (result.status === 'authorized') {
          const updated = await api.codexAuthStatus();
          if (cancelled) return;
          setStatus(updated);
          setLogin(null);
          onToast('ok', 'Codex 登录成功；保存模型配置后即可使用。');
        } else {
          timer = setTimeout(poll, intervalMs);
        }
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        setLogin(null);
      }
    }
    timer = setTimeout(poll, intervalMs);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [login, onToast]);

  async function begin() {
    setBusy(true);
    setError('');
    try {
      const result = await api.startCodexLogin();
      if (mounted.current) setLogin(result);
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  async function logout() {
    setBusy(true);
    setError('');
    try {
      await api.logoutCodex();
      if (mounted.current) {
        setLogin(null);
        setStatus({ authenticated: false, expires_at: null, account_id: null });
      }
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <section className="modal-section" aria-label="Codex OAuth">
      <div className="modal-section-title">
        ChatGPT / Codex 登录
        <span className={`api-key-state ${status?.authenticated ? 'ok' : ''}`}>
          {status === null ? '读取登录状态…' : status.authenticated ? '已登录' : '未登录'}
        </span>
      </div>
      <p className="muted-note">
        Coordinator 和 Follower 共用此登录。完成授权后，保存下方模型配置以应用。
      </p>
      {error && <p role="alert">{error}</p>}
      {login ? (
        <div>
          <p>在授权页面输入此一次性设备码：</p>
          <p className="mono-path" style={{ fontSize: '1.25rem' }}>{login.user_code}</p>
          <a className="btn secondary sm" href={login.verification_uri} target="_blank" rel="noopener noreferrer">
            打开授权页面
          </a>
          <span className="field-hint">等待授权完成…</span>
          <button className="btn ghost sm" onClick={() => setLogin(null)}>取消等待</button>
        </div>
      ) : (
        <div className="modal-actions">
          <button className="btn secondary sm" disabled={busy} onClick={() => void begin()}>
            {busy ? '处理中…' : status?.authenticated ? '重新登录 ChatGPT / Codex' : '登录 ChatGPT / Codex'}
          </button>
          {status?.authenticated && (
            <button className="btn ghost sm" disabled={busy} onClick={() => void logout()}>
              退出 Codex 登录
            </button>
          )}
        </div>
      )}
    </section>
  );
}
