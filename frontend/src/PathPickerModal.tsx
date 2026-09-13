import React, { useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api';
import type { FsBrowseEntry, FsBrowseShortcut } from './types';

export interface PathPickerModalProps {
  isOpen: boolean;
  title?: string;
  initialPath?: string;
  extraShortcuts?: Array<{ name: string; path: string }>;
  onSelect: (path: string) => void;
  onClose: () => void;
}

export const PathPickerModal: React.FC<PathPickerModalProps> = ({
  isOpen,
  title = 'Select Directory',
  initialPath,
  extraShortcuts,
  onSelect,
  onClose,
}) => {
  const [currentPath, setCurrentPath] = useState<string>('');
  const [selectedPath, setSelectedPath] = useState<string>('');
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [entries, setEntries] = useState<FsBrowseEntry[]>([]);
  const [shortcuts, setShortcuts] = useState<FsBrowseShortcut[]>([]);
  const [showHidden, setShowHidden] = useState<boolean>(false);
  const [filterText, setFilterText] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [isEditingPath, setIsEditingPath] = useState<boolean>(false);
  const [editPathValue, setEditPathValue] = useState<string>('');

  const [isCreatingFolder, setIsCreatingFolder] = useState<boolean>(false);
  const [newFolderName, setNewFolderName] = useState<string>('');
  const [creatingFolder, setCreatingFolder] = useState<boolean>(false);
  const [systemPickerLoading, setSystemPickerLoading] = useState<boolean>(false);

  const newFolderInputRef = useRef<HTMLInputElement>(null);
  const manualPathInputRef = useRef<HTMLInputElement>(null);

  const loadDirectory = async (targetPath?: string, hidden = showHidden) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.browseFs(targetPath, hidden);
      setCurrentPath(resp.current);
      setSelectedPath(resp.current);
      setParentPath(resp.parent);
      setEntries(resp.entries);
      setShortcuts(resp.shortcuts);
      setEditPathValue(resp.current);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
      setIsCreatingFolder(false);
      setIsEditingPath(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      void loadDirectory(initialPath || undefined);
    }
  }, [isOpen, initialPath]);

  // Handle Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Focus inputs when revealed
  useEffect(() => {
    if (isCreatingFolder) {
      newFolderInputRef.current?.focus();
    }
  }, [isCreatingFolder]);

  useEffect(() => {
    if (isEditingPath) {
      manualPathInputRef.current?.focus();
      manualPathInputRef.current?.select();
    }
  }, [isEditingPath]);

  // Compute breadcrumbs for currentPath
  const breadcrumbs = useMemo(() => {
    if (!currentPath) return [];
    const parts = currentPath.split('/').filter(Boolean);
    const crumbs: Array<{ label: string; path: string }> = [{ label: '/', path: '/' }];
    let accum = '';
    for (const part of parts) {
      accum += '/' + part;
      crumbs.push({ label: part, path: accum });
    }
    return crumbs;
  }, [currentPath]);

  // Combined shortcuts (built-in + extra recent project workspaces)
  const allShortcuts = useMemo(() => {
    const list = [...shortcuts];
    if (extraShortcuts) {
      for (const extra of extraShortcuts) {
        if (!list.some((s) => s.path === extra.path)) {
          list.push(extra);
        }
      }
    }
    return list;
  }, [shortcuts, extraShortcuts]);

  // Filtered directory entries
  const filteredEntries = useMemo(() => {
    if (!filterText.trim()) return entries;
    const q = filterText.trim().toLowerCase();
    return entries.filter((e) => e.name.toLowerCase().includes(q));
  }, [entries, filterText]);

  const handleToggleHidden = () => {
    const nextHidden = !showHidden;
    setShowHidden(nextHidden);
    void loadDirectory(currentPath, nextHidden);
  };

  const handleCreateFolder = async () => {
    const trimmed = newFolderName.trim();
    if (!trimmed) return;
    setCreatingFolder(true);
    setError(null);
    try {
      const fullPath = currentPath === '/' ? `/${trimmed}` : `${currentPath}/${trimmed}`;
      await api.mkdirFs(fullPath);
      setNewFolderName('');
      setIsCreatingFolder(false);
      await loadDirectory(fullPath, showHidden);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreatingFolder(false);
    }
  };

  const handleNativePicker = async () => {
    setSystemPickerLoading(true);
    setError(null);
    try {
      const res = await api.systemPickerFs();
      if (res.supported && res.path) {
        onSelect(res.path);
        onClose();
      } else if (!res.supported) {
        // Not supported or not macOS — just stay in web picker
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSystemPickerLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal path-picker-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="modal-head path-picker-head">
          <div className="path-picker-title-row">
            <span className="modal-title">{title}</span>
            <span className="badge sm">GUI Picker</span>
          </div>
          <div className="path-picker-head-actions">
            <button
              type="button"
              className="btn ghost sm system-picker-btn"
              title="Open native OS folder dialog"
              disabled={systemPickerLoading}
              onClick={() => void handleNativePicker()}
            >
              {systemPickerLoading ? 'Opening…' : '🖥️ System Dialog'}
            </button>
            <button type="button" className="btn ghost sm modal-close-btn" onClick={onClose}>
              ✕
            </button>
          </div>
        </div>

        {/* Shortcuts Bar */}
        <div className="path-picker-shortcuts">
          <span className="shortcuts-label">Quick:</span>
          {allShortcuts.map((sc) => (
            <button
              key={sc.path}
              type="button"
              className={`btn ghost sm path-shortcut-chip ${currentPath === sc.path ? 'active' : ''}`}
              title={sc.path}
              onClick={() => void loadDirectory(sc.path)}
            >
              {sc.name === 'Home'
                ? '🏠 Home'
                : sc.name === 'Desktop'
                  ? '🖥️ Desktop'
                  : sc.name === 'Documents'
                    ? '📄 Docs'
                    : sc.name === 'CWD'
                      ? '💼 CWD'
                      : sc.name === 'Root'
                        ? '💾 /'
                        : `📁 ${sc.name}`}
            </button>
          ))}
        </div>

        {/* Path navigation bar & Breadcrumbs */}
        <div className="path-picker-nav">
          <button
            type="button"
            className="btn ghost sm path-nav-btn"
            disabled={!parentPath || loading}
            title={parentPath ? `Up to ${parentPath}` : 'At root'}
            onClick={() => parentPath && void loadDirectory(parentPath)}
          >
            ⬆️ Up
          </button>
          <button
            type="button"
            className="btn ghost sm path-nav-btn"
            disabled={loading}
            title="Refresh current folder"
            onClick={() => void loadDirectory(currentPath)}
          >
            🔄
          </button>

          <div className="path-breadcrumbs-wrap">
            {isEditingPath ? (
              <form
                className="path-manual-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  void loadDirectory(editPathValue.trim() || undefined);
                }}
              >
                <input
                  ref={manualPathInputRef}
                  className="input path-manual-input"
                  value={editPathValue}
                  onChange={(e) => setEditPathValue(e.target.value)}
                  onBlur={() => setIsEditingPath(false)}
                  onKeyDown={(e) => {
                    if (e.key === 'Escape') {
                      setIsEditingPath(false);
                      setEditPathValue(currentPath);
                    }
                  }}
                  placeholder="Enter absolute path and press Enter…"
                />
              </form>
            ) : (
              <div className="path-breadcrumbs" title="Click a segment to jump; click ✏️ to edit">
                {breadcrumbs.map((crumb, idx) => (
                  <React.Fragment key={crumb.path}>
                    {idx > 1 && <span className="crumb-sep">/</span>}
                    <button
                      type="button"
                      className={`crumb-btn ${idx === breadcrumbs.length - 1 ? 'crumb-active' : ''}`}
                      onClick={() => void loadDirectory(crumb.path)}
                    >
                      {crumb.label}
                    </button>
                  </React.Fragment>
                ))}
              </div>
            )}
            <button
              type="button"
              className="btn ghost sm path-edit-toggle"
              title={isEditingPath ? 'Done editing' : 'Edit path directly'}
              onClick={() => {
                if (!isEditingPath) setEditPathValue(currentPath);
                setIsEditingPath(!isEditingPath);
              }}
            >
              ✏️
            </button>
          </div>
        </div>

        {/* Toolbar: filter, show hidden, new folder */}
        <div className="path-picker-toolbar">
          <input
            className="input path-filter-input"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="Filter folders in this view…"
          />
          <label className="path-picker-checkbox-label">
            <input
              type="checkbox"
              checked={showHidden}
              onChange={handleToggleHidden}
            />
            Show hidden (.dotfiles)
          </label>
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => setIsCreatingFolder(!isCreatingFolder)}
          >
            ➕ New Folder
          </button>
        </div>

        {/* Inline New Folder Form */}
        {isCreatingFolder && (
          <div className="path-new-folder-bar">
            <input
              ref={newFolderInputRef}
              className="input path-new-folder-input"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="Folder name…"
              onKeyDown={(e) => {
                if (e.key === 'Enter') void handleCreateFolder();
                if (e.key === 'Escape') setIsCreatingFolder(false);
              }}
              disabled={creatingFolder}
            />
            <button
              type="button"
              className="btn primary sm"
              onClick={() => void handleCreateFolder()}
              disabled={!newFolderName.trim() || creatingFolder}
            >
              {creatingFolder ? 'Creating…' : 'Create'}
            </button>
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => setIsCreatingFolder(false)}
            >
              Cancel
            </button>
          </div>
        )}

        {/* Error notice if any */}
        {error && <div className="path-picker-error">⚠️ {error}</div>}

        {/* Folder List */}
        <div className="path-picker-list-wrap">
          {loading ? (
            <div className="path-picker-empty">Loading directory contents…</div>
          ) : filteredEntries.length === 0 ? (
            <div className="path-picker-empty">
              {filterText ? 'No matching folders found.' : 'No subdirectories in this folder.'}
            </div>
          ) : (
            <div className="path-picker-list">
              {filteredEntries.map((entry) => {
                const isSelected = selectedPath === entry.path;
                return (
                  <div
                    key={entry.path}
                    className={`path-folder-row ${isSelected ? 'selected' : ''}`}
                    onClick={() => setSelectedPath(entry.path)}
                    onDoubleClick={() => void loadDirectory(entry.path)}
                    title={`Click to select; double-click to open (${entry.path})`}
                  >
                    <span className="folder-icon">📁</span>
                    <span className="folder-name">{entry.name}</span>
                    {entry.mtime && (
                      <span className="folder-mtime">
                        {new Date(entry.mtime * 1000).toLocaleDateString()}
                      </span>
                    )}
                    <button
                      type="button"
                      className="btn ghost sm folder-open-btn"
                      title={`Open ${entry.name}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        void loadDirectory(entry.path);
                      }}
                    >
                      Open ➔
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="path-picker-footer">
          <div className="path-picker-selection">
            <span className="selection-label">Selected:</span>
            <span className="selection-path" title={selectedPath}>
              {selectedPath || currentPath || 'None'}
            </span>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn ghost sm" onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className="btn primary sm path-confirm-btn"
              disabled={!selectedPath && !currentPath}
              onClick={() => {
                const finalPath = selectedPath || currentPath;
                if (finalPath) {
                  onSelect(finalPath);
                  onClose();
                }
              }}
            >
              Select This Folder
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
