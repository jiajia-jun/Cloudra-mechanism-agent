import { useState } from 'react';
import { api } from './api';
import { useI18n } from './i18n';
import type { UpdateCheckResult } from './types';

const SOURCE_UPGRADE_CMD = 'git pull --ff-only && bash install.sh';

interface UpdateModalProps {
  update: UpdateCheckResult;
  onClose: () => void;
  onDismissVersion: (version: string) => void;
  onRecheck: () => Promise<void>;
  onToast: (kind: 'ok' | 'error' | 'info', text: string) => void;
}

export function UpdateModal({
  update,
  onClose,
  onDismissVersion,
  onRecheck,
  onToast,
}: UpdateModalProps) {
  const { lang } = useI18n();
  const [checking, setChecking] = useState(false);

  const handleCopySourceCmd = async () => {
    try {
      await navigator.clipboard.writeText(SOURCE_UPGRADE_CMD);
      onToast('ok', lang === 'zh' ? '已复制源码升级命令' : 'Copied upgrade command');
    } catch {
      onToast('info', SOURCE_UPGRADE_CMD);
    }
  };

  const handleRecheck = async () => {
    setChecking(true);
    try {
      await onRecheck();
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal update-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-title">
            {lang === 'zh'
              ? `发现 Cloudra 新版本 v${update.latest_version}`
              : `Cloudra v${update.latest_version} Available`}
          </div>
          <button type="button" className="btn ghost sm" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-sub">
          {lang === 'zh'
            ? `当前版本 v${update.current_version} → 最新版本 v${update.latest_version}。Cloudra 不会在后台强行覆盖文件或中断计算进程，请按你的安装方式选择升级。`
            : `Current v${update.current_version} → Latest v${update.latest_version}. Cloudra never overwrites binaries or stops running calculations automatically.`}
        </div>

        {update.active_compute_jobs > 0 && (
          <div className="update-active-warning">
            {lang === 'zh'
              ? `当前检测到 ${update.active_compute_jobs} 个活跃计算作业。后台守卫进程独立于 Web 界面，但仍建议等关键作业稳定后再替换安装包。`
              : `${update.active_compute_jobs} active compute job(s) detected. Detached guards run independently, but upgrading after active runs settle is recommended.`}
          </div>
        )}

        {update.release_notes && (
          <div className="update-notes-box">
            <div className="update-notes-label">
              {lang === 'zh' ? '本版更新说明' : 'Release highlights'}
            </div>
            <pre className="update-notes-pre">{update.release_notes}</pre>
          </div>
        )}

        {update.install_mode === 'source' && (
          <div className="update-source-box">
            <div className="update-notes-label">
              {lang === 'zh' ? '当前为源码运行，可在仓库目录执行：' : 'Running from source—update with:'}
            </div>
            <div className="update-cmd-row">
              <code>{SOURCE_UPGRADE_CMD}</code>
              <button type="button" className="btn outline sm" onClick={() => void handleCopySourceCmd()}>
                {lang === 'zh' ? '复制命令' : 'Copy'}
              </button>
            </div>
          </div>
        )}

        <div className="update-modal-actions">
          <a
            className="btn primary sm"
            href={update.release_url}
            target="_blank"
            rel="noreferrer"
          >
            {lang === 'zh' ? '前往 GitHub Release 下载' : 'Open GitHub Release'}
          </a>
          <button
            type="button"
            className="btn outline sm"
            disabled={checking}
            onClick={() => void handleRecheck()}
          >
            {checking
              ? (lang === 'zh' ? '检查中…' : 'Checking…')
              : (lang === 'zh' ? '重新检查' : 'Re-check')}
          </button>
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => {
              onDismissVersion(update.latest_version);
              onClose();
            }}
          >
            {lang === 'zh' ? '忽略此版本' : 'Dismiss this version'}
          </button>
        </div>
      </div>
    </div>
  );
}

interface UpdateCheckInlineProps {
  onToast: (kind: 'ok' | 'error', text: string) => void;
}

export function UpdateCheckInline({ onToast }: UpdateCheckInlineProps) {
  const { lang } = useI18n();
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<UpdateCheckResult | null>(null);

  const run = async () => {
    setChecking(true);
    try {
      const data = await api.checkForUpdates(true);
      setResult(data);
      if (data.status === 'up_to_date') {
        onToast('ok', lang === 'zh' ? `当前已是最新版本 v${data.current_version}` : `Already up to date (v${data.current_version})`);
      } else if (data.status === 'update_available') {
        onToast('ok', lang === 'zh' ? `发现新版本 v${data.latest_version}` : `Update available: v${data.latest_version}`);
      } else {
        onToast('error', lang === 'zh' ? `暂时无法连接 GitHub Releases：${data.error || '网络不可达'}` : `Could not reach GitHub Releases: ${data.error || 'offline'}`);
      }
    } catch (err) {
      onToast('error', err instanceof Error ? err.message : String(err));
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="modal-section update-inline-section">
      <div className="update-inline-head">
        <div>
          <div className="modal-section-title">
            {lang === 'zh' ? '版本与更新检查' : 'Version & Update Check'}
          </div>
          <div className="onboarding-callout-sub">
            {result
              ? result.status === 'update_available'
                ? (lang === 'zh'
                  ? `发现新版本 v${result.latest_version}（当前 v${result.current_version}）`
                  : `New version v${result.latest_version} available (current v${result.current_version})`)
                : result.status === 'up_to_date'
                  ? (lang === 'zh'
                    ? `当前已是最新版本 v${result.current_version}`
                    : `Up to date on v${result.current_version}`)
                  : (lang === 'zh'
                    ? `检查失败：${result.error || '无法连接 GitHub'}`
                    : `Check unavailable: ${result.error || 'offline'}`)
              : (lang === 'zh'
                ? '只读检查 GitHub Releases 最新版本，不自动覆盖文件或打断计算任务。'
                : 'Read-only check against GitHub Releases; never overwrites files or interrupts compute jobs.')}
          </div>
        </div>
        <div className="update-inline-actions">
          {result?.status === 'update_available' && (
            <a
              className="btn primary sm"
              href={result.release_url}
              target="_blank"
              rel="noreferrer"
            >
              {lang === 'zh' ? '去下载' : 'Download'}
            </a>
          )}
          <button
            type="button"
            className="btn outline sm"
            disabled={checking}
            onClick={() => void run()}
          >
            {checking
              ? (lang === 'zh' ? '检查中…' : 'Checking…')
              : (lang === 'zh' ? '检查更新' : 'Check for updates')}
          </button>
        </div>
      </div>
    </div>
  );
}
