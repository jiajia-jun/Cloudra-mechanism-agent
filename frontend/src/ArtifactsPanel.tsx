import { useState, useEffect, useMemo } from 'react';
import { api } from './api';
import type { Project } from './types';
import { useI18n } from './i18n';

interface ArtifactItem {
  artifact_id: string;
  conversation_id: string;
  session_id: string;
  name: string;
  mime_type: string;
  size: number;
  sha256?: string;
  storage_path?: string;
  created_at: string;
}

export function fmtBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function ArtifactsPanel({
  project,
  onError,
}: {
  project: Project;
  onError?: (err: unknown) => void;
}) {
  const { t } = useI18n();
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState<'all' | 'xyz' | 'log' | 'report' | 'image'>('all');
  const [previewItem, setPreviewItem] = useState<ArtifactItem | null>(null);

  const fetchArtifacts = () => {
    setLoading(true);
    api.artifacts(project.id)
      .then((res) => {
        setArtifacts((res as unknown as ArtifactItem[]) || []);
      })
      .catch((err) => {
        if (onError) onError(err);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchArtifacts();
  }, [project.id]);

  const filteredArtifacts = useMemo(() => {
    return artifacts.filter((a) => {
      const matchSearch =
        !search.trim() ||
        a.name.toLowerCase().includes(search.toLowerCase()) ||
        a.artifact_id.toLowerCase().includes(search.toLowerCase());

      if (!matchSearch) return false;

      if (filterType === 'all') return true;
      const ext = a.name.split('.').pop()?.toLowerCase() ?? '';
      if (filterType === 'xyz') return ['xyz', 'mol', 'pdb', 'cif'].includes(ext);
      if (filterType === 'log') return ['log', 'out', 'txt'].includes(ext);
      if (filterType === 'report') return ['json', 'md', 'csv', 'yaml', 'yml'].includes(ext);
      if (filterType === 'image') return ['png', 'svg', 'jpg', 'jpeg', 'webp'].includes(ext);
      return true;
    });
  }, [artifacts, search, filterType]);

  const totalSize = useMemo(() => {
    return artifacts.reduce((acc, a) => acc + (a.size || 0), 0);
  }, [artifacts]);

  return (
    <div className="artifacts-panel">
      {/* Top Controls Bar */}
      <div className="artifacts-header">
        <div className="artifacts-title-area">
          <span className="artifacts-title">{t.artifactsTitle}</span>
          <span className="badge sm">{t.artifactsCount(artifacts.length)}</span>
          <span className="badge sm mono">{fmtBytes(totalSize)}</span>
        </div>

        <div className="artifacts-actions">
          <div className="search-box">
            <input
              type="text"
              className="input sm"
              placeholder={t.artifactsSearchPlaceholder}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search && (
              <button type="button" className="search-clear-btn" onClick={() => setSearch('')}>
                ✕
              </button>
            )}
          </div>

          <div className="btn-group sm">
            <button
              type="button"
              className={`btn outline sm ${filterType === 'all' ? 'active' : ''}`}
              onClick={() => setFilterType('all')}
            >
              {t.artifactsFilterAll}
            </button>
            <button
              type="button"
              className={`btn outline sm ${filterType === 'xyz' ? 'active' : ''}`}
              onClick={() => setFilterType('xyz')}
            >
              {t.artifactsFilterXyz}
            </button>
            <button
              type="button"
              className={`btn outline sm ${filterType === 'log' ? 'active' : ''}`}
              onClick={() => setFilterType('log')}
            >
              {t.artifactsFilterLog}
            </button>
            <button
              type="button"
              className={`btn outline sm ${filterType === 'report' ? 'active' : ''}`}
              onClick={() => setFilterType('report')}
            >
              {t.artifactsFilterReport}
            </button>
            <button
              type="button"
              className={`btn outline sm ${filterType === 'image' ? 'active' : ''}`}
              onClick={() => setFilterType('image')}
            >
              {t.artifactsFilterImage}
            </button>
          </div>

          <button type="button" className="btn ghost sm" onClick={fetchArtifacts} disabled={loading}>
            {loading ? '…' : t.hubRefresh}
          </button>
        </div>
      </div>

      {/* Artifacts List or Grid */}
      <div className="artifacts-body">
        {loading ? (
          <div className="chat-empty">{t.artifactsLoading}</div>
        ) : filteredArtifacts.length === 0 ? (
          <div className="chat-empty">
            {artifacts.length === 0
              ? t.artifactsEmptyProject
              : t.artifactsEmptyFilter}
          </div>
        ) : (
          <div className="artifacts-grid">
            {filteredArtifacts.map((art) => {
              const ext = art.name.split('.').pop()?.toLowerCase() ?? 'file';
              const downloadUrl = api.artifactDownloadUrl(project.id, art.artifact_id);
              const isImg = ['png', 'svg', 'jpg', 'jpeg', 'webp'].includes(ext);

              return (
                <div key={art.artifact_id} className="artifact-card">
                  <div className="artifact-card-top">
                    <span className={`artifact-ext-badge ${ext}`}>{ext.toUpperCase()}</span>
                    <span className="artifact-size">{fmtBytes(art.size)}</span>
                  </div>

                  <div className="artifact-name" title={art.name}>
                    {art.name}
                  </div>

                  <div className="artifact-meta">
                    <span className="mono-time">{art.created_at ? art.created_at.slice(0, 19).replace('T', ' ') : '-'}</span>
                    {art.sha256 && (
                      <span className="mono-hash" title={`SHA256: ${art.sha256}`}>
                        {art.sha256.slice(0, 8)}…
                      </span>
                    )}
                  </div>

                  <div className="artifact-card-actions">
                    <a
                      href={downloadUrl}
                      download={art.name}
                      className="btn primary sm"
                      title={t.artifactsDownloadHint}
                    >
                      {t.artifactsDownload}
                    </a>
                    {isImg && (
                      <button
                        type="button"
                        className="btn outline sm"
                        onClick={() => setPreviewItem(art)}
                      >
                        {t.artifactsPreview}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Image Preview Modal */}
      {previewItem && (
        <div className="modal-backdrop" onClick={() => setPreviewItem(null)}>
          <div className="modal-card image-preview-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-title">{previewItem.name}</span>
              <button type="button" className="modal-close" onClick={() => setPreviewItem(null)}>
                ✕
              </button>
            </div>
            <div className="modal-body preview-img-wrap">
              <img
                src={api.artifactDownloadUrl(project.id, previewItem.artifact_id)}
                alt={previewItem.name}
                style={{ maxWidth: '100%', maxHeight: '70vh', objectFit: 'contain' }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
