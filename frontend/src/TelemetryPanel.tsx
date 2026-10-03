/**
 * TelemetryPanel — LLM 遥测只读视图（/api/v2/telemetry/*）。
 *
 * Near-fullscreen modal over the token aggregation and prompt-cache
 * analysis endpoints: totals cards, per-agent / per-project tables with a
 * since/until date filter, cache hit-rate breakdowns (by day, by session
 * request-count bucket, by model), the missed-token distribution, top
 * misses, and full-context export downloads (session JSONL / project zip,
 * authenticated via the ?token= query fallback like artifact downloads).
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  api,
  type TelemetryAgentRow,
  type TelemetryCacheResponse,
  type TelemetryProjectRow,
  type TelemetryTokensResponse,
  type TelemetryTotals,
} from './api';

interface TelemetryPanelProps {
  onClose: () => void;
  onToast: (kind: 'ok' | 'error' | 'info', text: string) => void;
}

type TelemetryTab = 'overview' | 'agents' | 'projects' | 'cache' | 'export';

function fmtTok(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return n.toLocaleString();
}

function fmtCompact(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  if (Math.abs(n) >= 1_000_000) {
    return `${(n / 1_000_000).toFixed(2)}M`;
  }
  if (Math.abs(n) >= 1_000) {
    return `${(n / 1_000).toFixed(1)}k`;
  }
  return n.toLocaleString();
}

function fmtPct(x: number | null | undefined): string {
  if (x == null || !Number.isFinite(x)) return '—';
  return `${(x * 100).toFixed(1)}%`;
}

function fmtTs(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function IdBadge({ id, fallback = '—' }: { id: string | null | undefined; fallback?: string }) {
  const [copied, setCopied] = useState(false);
  if (!id) return <span style={{ color: 'var(--fg-tertiary)' }}>{fallback}</span>;

  const short = id.length > 20 ? `${id.slice(0, 8)}…${id.slice(-6)}` : id;

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    void navigator.clipboard.writeText(id);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <span className="tm-id-badge" title={`${id} (点击复制完整 ID)`} onClick={handleCopy}>
      <code className="tm-id-text">{short}</code>
      <span className="tm-id-copy" title="复制">{copied ? '✓' : '复制'}</span>
    </span>
  );
}

function HitRateBadge({ rate }: { rate: number | null | undefined }) {
  if (rate == null || !Number.isFinite(rate)) {
    return <span style={{ color: 'var(--fg-tertiary)' }}>—</span>;
  }
  const pct = rate * 100;
  let cls = 'tm-badge-low';
  if (pct >= 50) cls = 'tm-badge-high';
  else if (pct >= 20) cls = 'tm-badge-mid';

  return (
    <span className={`tm-hit-badge ${cls}`}>
      {pct.toFixed(1)}%
    </span>
  );
}

function ProportionBar({
  leftLabel,
  leftVal,
  leftColor,
  rightLabel,
  rightVal,
  rightColor,
}: {
  leftLabel: string;
  leftVal: number;
  leftColor: string;
  rightLabel: string;
  rightVal: number;
  rightColor: string;
}) {
  const total = Math.max(0, leftVal) + Math.max(0, rightVal);
  const leftPct = total > 0 ? (Math.max(0, leftVal) / total) * 100 : 50;
  const rightPct = 100 - leftPct;

  return (
    <div className="tm-ratio-wrap">
      <div className="tm-ratio-labels">
        <span style={{ color: leftColor }}>
          {leftLabel}: <b>{fmtCompact(leftVal)}</b> ({fmtTok(leftVal)}) — {leftPct.toFixed(1)}%
        </span>
        <span style={{ color: rightColor }}>
          {rightLabel}: <b>{fmtCompact(rightVal)}</b> ({fmtTok(rightVal)}) — {rightPct.toFixed(1)}%
        </span>
      </div>
      <div className="tm-ratio-bar">
        <div style={{ width: `${leftPct}%`, background: leftColor, transition: 'width 0.3s var(--ease)' }} />
        <div style={{ width: `${rightPct}%`, background: rightColor, transition: 'width 0.3s var(--ease)' }} />
      </div>
    </div>
  );
}

function TotalsCells({ t }: { t: TelemetryTotals }) {
  return (
    <>
      <td className="tm-num">{fmtTok(t.requests)}</td>
      <td className="tm-num">{fmtTok(t.prompt_tokens)}</td>
      <td className="tm-num">{fmtTok(t.completion_tokens)}</td>
      <td className="tm-num">{fmtTok(t.cached_tokens)}</td>
      <td className="tm-num" style={{ fontWeight: 600 }}>{fmtTok(t.total_tokens)}</td>
      <td className="tm-num"><HitRateBadge rate={t.hit_rate} /></td>
      <td>{fmtTs(t.first_request_at)}</td>
      <td>{fmtTs(t.last_request_at)}</td>
    </>
  );
}

const TOTALS_HEADERS = (
  <>
    <th className="tm-th-num">Requests</th>
    <th className="tm-th-num">Prompt</th>
    <th className="tm-th-num">Completion</th>
    <th className="tm-th-num">Cached</th>
    <th className="tm-th-num">Total Tokens</th>
    <th className="tm-th-num">Hit Rate</th>
    <th>First Request</th>
    <th>Last Request</th>
  </>
);

export default function TelemetryPanel({ onClose, onToast }: TelemetryPanelProps) {
  const [tab, setTab] = useState<TelemetryTab>('overview');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [tokens, setTokens] = useState<TelemetryTokensResponse | null>(null);
  const [cache, setCache] = useState<TelemetryCacheResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [exportSessionId, setExportSessionId] = useState('');
  const [exportProjectId, setExportProjectId] = useState('');

  const load = useCallback(
    async (sinceDate: string, untilDate: string) => {
      setLoading(true);
      try {
        // `until` is inclusive of the picked day; the backend compares ISO
        // timestamps, so a bare date would mean midnight at the day's start.
        const sinceIso = sinceDate || undefined;
        const untilIso = untilDate ? `${untilDate}T23:59:59` : undefined;
        const [t, c] = await Promise.all([
          api.telemetryTokens(sinceIso, untilIso),
          api.telemetryCache(sinceIso, untilIso),
        ]);
        setTokens(t);
        setCache(c);
      } catch (e) {
        onToast('error', e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [onToast],
  );

  useEffect(() => {
    void load('', '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyPreset = (preset: 'all' | 'today' | '7d' | '30d') => {
    if (preset === 'all') {
      setSince('');
      setUntil('');
      void load('', '');
      return;
    }
    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, '0');
    const fmt = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const todayStr = fmt(now);

    let sinceStr = todayStr;
    if (preset === '7d') {
      const d7 = new Date(now.getTime() - 7 * 86400000);
      sinceStr = fmt(d7);
    } else if (preset === '30d') {
      const d30 = new Date(now.getTime() - 30 * 86400000);
      sinceStr = fmt(d30);
    }

    setSince(sinceStr);
    setUntil(todayStr);
    void load(sinceStr, todayStr);
  };

  const totals = tokens?.totals ?? null;
  const overall = cache?.overall ?? null;
  const missedDist = cache?.miss_distribution ?? null;

  // Filtered lists
  const filteredAgents = useMemo(() => {
    const list = tokens?.agents ?? [];
    if (!searchQuery.trim()) return list;
    const q = searchQuery.trim().toLowerCase();
    return list.filter(
      (r: TelemetryAgentRow) =>
        r.session_id.toLowerCase().includes(q) ||
        (r.project_id && r.project_id.toLowerCase().includes(q)),
    );
  }, [tokens?.agents, searchQuery]);

  const filteredProjects = useMemo(() => {
    const list = tokens?.projects ?? [];
    if (!searchQuery.trim()) return list;
    const q = searchQuery.trim().toLowerCase();
    return list.filter((r: TelemetryProjectRow) => r.project_id.toLowerCase().includes(q));
  }, [tokens?.projects, searchQuery]);

  const filteredMisses = useMemo(() => {
    const list = cache?.top_misses ?? [];
    if (!searchQuery.trim()) return list;
    const q = searchQuery.trim().toLowerCase();
    return list.filter(
      (r) =>
        r.model.toLowerCase().includes(q) ||
        (r.session_id && r.session_id.toLowerCase().includes(q)) ||
        (r.project_id && r.project_id.toLowerCase().includes(q)),
    );
  }, [cache?.top_misses, searchQuery]);

  const sortedModels = useMemo(() => {
    const list = [...(cache?.by_model ?? [])];
    list.sort((a, b) => (b.total_tokens ?? 0) - (a.total_tokens ?? 0));
    return list;
  }, [cache?.by_model]);

  return (
    <div className="modal-backdrop">
      <div className="modal tm-modal">
        {/* Pinned Header */}
        <div className="tm-head">
          <div className="tm-head-left">
            <span className="tm-title">LLM Telemetry (全局 Token 遥测)</span>
            <span className="tm-scope-badge">
              {since || until ? `${since || 'Start'} → ${until || 'End'}` : '全部历史'}
            </span>
          </div>
          <button className="btn ghost sm" type="button" onClick={onClose} title="关闭 (Esc)">
            ✕
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="tm-tabs-bar">
          <button
            type="button"
            className={`tab ${tab === 'overview' ? 'active' : ''}`}
            onClick={() => setTab('overview')}
          >
            总览与模型
          </button>
          <button
            type="button"
            className={`tab ${tab === 'agents' ? 'active' : ''}`}
            onClick={() => setTab('agents')}
          >
            会话明细 ({tokens?.agents.length ?? 0})
          </button>
          <button
            type="button"
            className={`tab ${tab === 'projects' ? 'active' : ''}`}
            onClick={() => setTab('projects')}
          >
            项目统计 ({tokens?.projects.length ?? 0})
          </button>
          <button
            type="button"
            className={`tab ${tab === 'cache' ? 'active' : ''}`}
            onClick={() => setTab('cache')}
          >
            缓存分析
          </button>
          <button
            type="button"
            className={`tab ${tab === 'export' ? 'active' : ''}`}
            onClick={() => setTab('export')}
          >
            数据导出
          </button>
        </div>

        {/* Filter Bar */}
        <div className="tm-filter-bar">
          <div className="tm-presets">
            <button
              className={`btn ghost sm ${!since && !until ? 'active' : ''}`}
              type="button"
              disabled={loading}
              onClick={() => applyPreset('all')}
            >
              全部
            </button>
            <button
              className="btn ghost sm"
              type="button"
              disabled={loading}
              onClick={() => applyPreset('today')}
            >
              今日
            </button>
            <button
              className="btn ghost sm"
              type="button"
              disabled={loading}
              onClick={() => applyPreset('7d')}
            >
              近 7 天
            </button>
            <button
              className="btn ghost sm"
              type="button"
              disabled={loading}
              onClick={() => applyPreset('30d')}
            >
              近 30 天
            </button>
          </div>

          <div className="tm-date-inputs">
            <input
              className="input sm"
              type="date"
              value={since}
              onChange={(e) => setSince(e.target.value)}
              title="起始日期 (since)"
            />
            <span style={{ color: 'var(--fg-tertiary)' }}>→</span>
            <input
              className="input sm"
              type="date"
              value={until}
              onChange={(e) => setUntil(e.target.value)}
              title="截止日期 (until)"
            />
            <button
              className="btn primary sm"
              type="button"
              disabled={loading}
              onClick={() => void load(since, until)}
            >
              {loading ? '加载中…' : '查询'}
            </button>
            {(since || until) && (
              <button
                className="btn ghost sm"
                type="button"
                disabled={loading}
                onClick={() => applyPreset('all')}
              >
                重置
              </button>
            )}
          </div>

          {(tab === 'agents' || tab === 'projects' || tab === 'cache') && (
            <div style={{ marginLeft: 'auto' }}>
              <input
                className="input sm tm-search-input"
                placeholder={
                  tab === 'projects'
                    ? '搜索 Project ID…'
                    : tab === 'cache'
                    ? '搜索 Model / ID…'
                    : '搜索 Session / Project ID…'
                }
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          )}
        </div>

        {/* Scrollable Body */}
        <div className="tm-body">
          {tab === 'overview' && (
            <>
              {/* Primary KPI Grid */}
              <div className="tm-kpi-grid">
                <div className="tm-kpi-card" title="所有会话 Prompt + Completion 的总和">
                  <div className="tm-kpi-header">
                    <span>总 Token 消耗</span>
                    <span style={{ color: 'var(--fg-secondary)' }}>Total Tokens</span>
                  </div>
                  <div className="tm-kpi-val-row">
                    <span className="tm-kpi-value">{fmtCompact(totals?.total_tokens)}</span>
                    <span className="tm-kpi-exact">({fmtTok(totals?.total_tokens)})</span>
                  </div>
                  <div className="tm-kpi-sub">
                    <span>输入 {fmtCompact(totals?.prompt_tokens)}</span>
                    <span>·</span>
                    <span>输出 {fmtCompact(totals?.completion_tokens)}</span>
                  </div>
                </div>

                <div className="tm-kpi-card" title="Cached Tokens / Prompt Tokens">
                  <div className="tm-kpi-header">
                    <span>缓存命中率</span>
                    <HitRateBadge rate={totals?.hit_rate} />
                  </div>
                  <div className="tm-kpi-val-row">
                    <span className="tm-kpi-value">{fmtPct(totals?.hit_rate)}</span>
                  </div>
                  <div className="tm-kpi-sub">
                    <span style={{ color: 'var(--green)' }}>
                      已节省 {fmtCompact(totals?.cached_tokens)} tokens
                    </span>
                  </div>
                </div>

                <div className="tm-kpi-card" title="向模型发起的调用次数与单次平均开销">
                  <div className="tm-kpi-header">
                    <span>LLM 调用次数</span>
                    <span style={{ color: 'var(--fg-secondary)' }}>Requests</span>
                  </div>
                  <div className="tm-kpi-val-row">
                    <span className="tm-kpi-value">{fmtTok(totals?.requests)}</span>
                    <span className="tm-kpi-exact">次</span>
                  </div>
                  <div className="tm-kpi-sub">
                    <span>
                      平均每次{' '}
                      {fmtCompact(
                        totals?.requests ? Math.round(totals.total_tokens / totals.requests) : 0,
                      )}{' '}
                      tokens
                    </span>
                  </div>
                </div>

                <div className="tm-kpi-card" title="涵盖的会话与项目规模">
                  <div className="tm-kpi-header">
                    <span>覆盖规模</span>
                    <span style={{ color: 'var(--fg-secondary)' }}>Scope</span>
                  </div>
                  <div className="tm-kpi-val-row">
                    <span className="tm-kpi-value">{fmtTok(totals?.sessions)}</span>
                    <span className="tm-kpi-exact">会话</span>
                    <span style={{ color: 'var(--fg-tertiary)', margin: '0 4px' }}>/</span>
                    <span className="tm-kpi-value">{fmtTok(totals?.projects)}</span>
                    <span className="tm-kpi-exact">项目</span>
                  </div>
                  <div className="tm-kpi-sub">
                    <span>跨度: {fmtTs(totals?.first_request_at)} 起</span>
                  </div>
                </div>
              </div>

              {/* Visual Proportion Section */}
              {totals && (
                <div className="tm-ratio-section">
                  <ProportionBar
                    leftLabel="Prompt (输入消耗)"
                    leftVal={totals.prompt_tokens}
                    leftColor="rgb(56, 189, 248)"
                    rightLabel="Completion (生成消耗)"
                    rightVal={totals.completion_tokens}
                    rightColor="rgb(168, 85, 247)"
                  />
                  <ProportionBar
                    leftLabel="Cached (已缓存命中)"
                    leftVal={totals.cached_tokens}
                    leftColor="var(--green)"
                    rightLabel="Missed (未缓存消耗)"
                    rightVal={Math.max(0, totals.prompt_tokens - totals.cached_tokens)}
                    rightColor="var(--yellow)"
                  />
                </div>
              )}

              {/* Model Breakdown */}
              <div className="tm-table-box">
                <div className="tm-table-box-head">
                  <div className="tm-table-box-title">
                    <span>模型调用与消耗分布 (By Model)</span>
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--fg-tertiary)' }}>
                    共 {sortedModels.length} 个模型
                  </span>
                </div>
                <div className="tm-table-wrap" style={{ maxHeight: 300 }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Model</th>
                        {TOTALS_HEADERS}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedModels.length === 0 ? (
                        <tr>
                          <td colSpan={9} className="empty-hint">
                            {tokens ? '该时间段内无 LLM 调用记录' : '加载中…'}
                          </td>
                        </tr>
                      ) : (
                        sortedModels.map((row) => (
                          <tr key={row.model}>
                            <td style={{ fontFamily: 'var(--mono)', fontWeight: 600 }}>
                              {row.model}
                            </td>
                            <TotalsCells t={row} />
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Daily Timeline */}
              <div className="tm-table-box">
                <div className="tm-table-box-head">
                  <div className="tm-table-box-title">
                    <span>按日消耗趋势 (By Day)</span>
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--fg-tertiary)' }}>
                    共 {(cache?.by_day ?? []).length} 天
                  </span>
                </div>
                <div className="tm-table-wrap" style={{ maxHeight: 260 }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Day</th>
                        {TOTALS_HEADERS}
                      </tr>
                    </thead>
                    <tbody>
                      {(cache?.by_day ?? []).length === 0 ? (
                        <tr>
                          <td colSpan={9} className="empty-hint">
                            {cache ? '该时间段内无记录' : '加载中…'}
                          </td>
                        </tr>
                      ) : (
                        (cache?.by_day ?? []).map((row) => (
                          <tr key={row.day}>
                            <td style={{ fontFamily: 'var(--mono)' }}>{row.day}</td>
                            <TotalsCells t={row} />
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Session Request Count Buckets */}
              <div className="tm-table-box">
                <div className="tm-table-box-head">
                  <div className="tm-table-box-title">
                    <span>单会话调用频次分桶 (By Session Request Count)</span>
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--fg-tertiary)' }}>
                    长短会话缓存效益对比
                  </span>
                </div>
                <div className="tm-table-wrap" style={{ maxHeight: 220 }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Bucket</th>
                        <th className="tm-th-num">Sessions</th>
                        {TOTALS_HEADERS}
                      </tr>
                    </thead>
                    <tbody>
                      {(cache?.by_request_bucket ?? []).map((row) => (
                        <tr key={row.bucket}>
                          <td style={{ fontWeight: 600 }}>{row.bucket} 次请求</td>
                          <td className="tm-num">{fmtTok(row.sessions)}</td>
                          <TotalsCells t={row} />
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

          {tab === 'agents' && (
            <div className="tm-table-box" style={{ flex: 1 }}>
              <div className="tm-table-box-head">
                <div className="tm-table-box-title">
                  <span>Agent 会话消耗明细 (By Agent)</span>
                </div>
                <span style={{ fontSize: 11, color: 'var(--fg-tertiary)' }}>
                  显示 {filteredAgents.length} / {tokens?.agents.length ?? 0} 条
                </span>
              </div>
              <div className="tm-table-wrap" style={{ maxHeight: 'calc(100vh - 280px)' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Session ID</th>
                      <th>Project ID</th>
                      {TOTALS_HEADERS}
                      <th>Export</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAgents.length === 0 ? (
                      <tr>
                        <td colSpan={11} className="empty-hint">
                          {tokens ? '无匹配的会话记录' : '加载中…'}
                        </td>
                      </tr>
                    ) : (
                      filteredAgents.map((row) => (
                        <tr key={row.session_id}>
                          <td><IdBadge id={row.session_id} /></td>
                          <td><IdBadge id={row.project_id} fallback="—" /></td>
                          <TotalsCells t={row} />
                          <td>
                            <a
                              className="btn ghost sm"
                              href={api.telemetrySessionExportUrl(row.session_id)}
                              title="下载该会话全量上下文 (JSONL)"
                              style={{ height: 24, padding: '0 8px', fontSize: 11 }}
                            >
                              导出 ↓
                            </a>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {tab === 'projects' && (
            <div className="tm-table-box" style={{ flex: 1 }}>
              <div className="tm-table-box-head">
                <div className="tm-table-box-title">
                  <span>项目消耗明细 (By Project)</span>
                </div>
                <span style={{ fontSize: 11, color: 'var(--fg-tertiary)' }}>
                  显示 {filteredProjects.length} / {tokens?.projects.length ?? 0} 个项目
                </span>
              </div>
              <div className="tm-table-wrap" style={{ maxHeight: 'calc(100vh - 280px)' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Project ID</th>
                      <th className="tm-th-num">Sessions</th>
                      {TOTALS_HEADERS}
                      <th>Export</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredProjects.length === 0 ? (
                      <tr>
                        <td colSpan={11} className="empty-hint">
                          {tokens ? '无匹配的项目记录' : '加载中…'}
                        </td>
                      </tr>
                    ) : (
                      filteredProjects.map((row) => (
                        <tr key={row.project_id}>
                          <td><IdBadge id={row.project_id} /></td>
                          <td className="tm-num">{fmtTok(row.sessions)}</td>
                          <TotalsCells t={row} />
                          <td>
                            <a
                              className="btn ghost sm"
                              href={api.telemetryProjectExportUrl(row.project_id)}
                              title="下载该项目所有会话上下文打包文件 (ZIP)"
                              style={{ height: 24, padding: '0 8px', fontSize: 11 }}
                            >
                              导出 ↓
                            </a>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {tab === 'cache' && (
            <>
              {/* Cache Distribution Cards */}
              <div className="tm-kpi-grid">
                <div className="tm-kpi-card">
                  <div className="tm-kpi-header">
                    <span>全局命中率</span>
                    <HitRateBadge rate={overall?.hit_rate} />
                  </div>
                  <div className="tm-kpi-val-row">
                    <span className="tm-kpi-value">{fmtPct(overall?.hit_rate)}</span>
                  </div>
                  <div className="tm-kpi-sub">
                    <span>已缓存 {fmtCompact(overall?.cached_tokens)} tokens</span>
                  </div>
                </div>

                <div className="tm-kpi-card">
                  <div className="tm-kpi-header">
                    <span>单次未命中中位数</span>
                    <span style={{ color: 'var(--fg-secondary)' }}>Median</span>
                  </div>
                  <div className="tm-kpi-val-row">
                    <span className="tm-kpi-value">{fmtTok(missedDist?.median)}</span>
                    <span className="tm-kpi-exact">tokens</span>
                  </div>
                  <div className="tm-kpi-sub">
                    <span>常规请求未命中基线</span>
                  </div>
                </div>

                <div className="tm-kpi-card">
                  <div className="tm-kpi-header">
                    <span>P90 未命中</span>
                    <span style={{ color: 'var(--yellow)' }}>P90</span>
                  </div>
                  <div className="tm-kpi-val-row">
                    <span className="tm-kpi-value">{fmtTok(missedDist?.p90)}</span>
                    <span className="tm-kpi-exact">tokens</span>
                  </div>
                  <div className="tm-kpi-sub">
                    <span>90% 请求未命中低于此值</span>
                  </div>
                </div>

                <div className="tm-kpi-card">
                  <div className="tm-kpi-header">
                    <span>P99 未命中</span>
                    <span style={{ color: 'var(--yellow-soft)' }}>P99</span>
                  </div>
                  <div className="tm-kpi-val-row">
                    <span className="tm-kpi-value">{fmtTok(missedDist?.p99)}</span>
                    <span className="tm-kpi-exact">tokens</span>
                  </div>
                  <div className="tm-kpi-sub">
                    <span>极少见大上下文重传</span>
                  </div>
                </div>

                <div className="tm-kpi-card">
                  <div className="tm-kpi-header">
                    <span>最大单次未命中</span>
                    <span style={{ color: 'rgb(239, 68, 68)' }}>Max</span>
                  </div>
                  <div className="tm-kpi-val-row">
                    <span className="tm-kpi-value">{fmtTok(missedDist?.max)}</span>
                    <span className="tm-kpi-exact">tokens</span>
                  </div>
                  <div className="tm-kpi-sub">
                    <span>单次最大无缓存请求</span>
                  </div>
                </div>
              </div>

              {/* Top Misses Table */}
              <div className="tm-table-box" style={{ flex: 1 }}>
                <div className="tm-table-box-head">
                  <div className="tm-table-box-title">
                    <span>Top 缓存未命中调用 (Top Cache Misses)</span>
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--fg-tertiary)' }}>
                    显示 {filteredMisses.length} 条调用
                  </span>
                </div>
                <div className="tm-table-wrap" style={{ maxHeight: 'calc(100vh - 350px)' }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Model</th>
                        <th>Session ID</th>
                        <th>Project ID</th>
                        <th className="tm-th-num">Prompt</th>
                        <th className="tm-th-num">Cached</th>
                        <th className="tm-th-num">Missed Tokens</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredMisses.length === 0 ? (
                        <tr>
                          <td colSpan={7} className="empty-hint">
                            {cache ? '该时间段内无未命中记录' : '加载中…'}
                          </td>
                        </tr>
                      ) : (
                        filteredMisses.map((row, i) => (
                          <tr key={`${row.created_at ?? ''}-${row.session_id ?? ''}-${i}`}>
                            <td>{fmtTs(row.created_at)}</td>
                            <td style={{ fontFamily: 'var(--mono)', fontWeight: 500 }}>
                              {row.model}
                            </td>
                            <td><IdBadge id={row.session_id} /></td>
                            <td><IdBadge id={row.project_id} fallback="—" /></td>
                            <td className="tm-num">{fmtTok(row.prompt_tokens)}</td>
                            <td className="tm-num">{fmtTok(row.cached_tokens)}</td>
                            <td className="tm-num tm-missed-val">{fmtTok(row.missed_tokens)}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

          {tab === 'export' && (
            <div className="tm-export-grid">
              <div className="tm-export-card">
                <div className="tm-export-title">
                  <span>单会话上下文导出 (Session JSONL)</span>
                </div>
                <div className="tm-export-desc">
                  导出指定 Agent 会话的完整上下文事件序列（包含 Prompt 前缀、追加内容、压缩摘要与 LLM 回复），采用 JSON Lines 格式。
                </div>
                <div className="tm-export-row">
                  <input
                    className="input"
                    style={{ flex: 1, fontFamily: 'var(--mono)', fontSize: 12 }}
                    value={exportSessionId}
                    onChange={(e) => setExportSessionId(e.target.value)}
                    placeholder="输入 session id (如 agent-xxxx...)"
                  />
                  {exportSessionId.trim() ? (
                    <a
                      className="btn primary sm"
                      href={api.telemetrySessionExportUrl(exportSessionId.trim())}
                      title="下载 JSONL 文件"
                    >
                      下载 JSONL ↓
                    </a>
                  ) : (
                    <button className="btn outline sm" type="button" disabled>
                      下载 JSONL ↓
                    </button>
                  )}
                </div>
              </div>

              <div className="tm-export-card">
                <div className="tm-export-title">
                  <span>项目全量会话打包 (Project ZIP)</span>
                </div>
                <div className="tm-export-desc">
                  打包导出指定项目下的所有 Agent 会话上下文文件，压缩为 ZIP 文件，便于离线回放、审计或分析提示词缓存效率。
                </div>
                <div className="tm-export-row">
                  <input
                    className="input"
                    style={{ flex: 1, fontFamily: 'var(--mono)', fontSize: 12 }}
                    value={exportProjectId}
                    onChange={(e) => setExportProjectId(e.target.value)}
                    placeholder="输入 project id (如 proj-xxxx...)"
                  />
                  {exportProjectId.trim() ? (
                    <a
                      className="btn primary sm"
                      href={api.telemetryProjectExportUrl(exportProjectId.trim())}
                      title="下载 ZIP 文件"
                    >
                      打包下载 ZIP ↓
                    </a>
                  ) : (
                    <button className="btn outline sm" type="button" disabled>
                      打包下载 ZIP ↓
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
