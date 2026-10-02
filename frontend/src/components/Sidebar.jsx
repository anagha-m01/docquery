import React, { useEffect, useState, useCallback } from "react";
import api, { extractErrorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import ConfirmDialog from "./ConfirmDialog";
import Logo from "./Logo";

function timeAgo(dateStr) {
  const diffMs = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function Sidebar({
  activeId, onSelect, onNewFile, refreshKey,
  isOpen, onClose,
  collapsed, onToggleCollapse,
  darkMode, onToggleDarkMode,
}) {
  const { user, logout } = useAuth();
  const [extractions, setExtractions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null); // extraction object
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const res = await api.get("/extractions");
      setExtractions(res.data.extractions || []);
    } catch (err) {
      setLoadError(extractErrorMessage(err, "Couldn't load your file history."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const handleDeleteConfirmed = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await api.delete(`/extractions/${pendingDelete.id}`);
      setExtractions((prev) => prev.filter((ex) => ex.id !== pendingDelete.id));
      if (pendingDelete.id === activeId) onNewFile();
      setPendingDelete(null);
    } catch (err) {
      setLoadError(extractErrorMessage(err, "Couldn't delete this file."));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
      {isOpen && <div className="sidebar-scrim" onClick={onClose} />}

      <aside className={`sidebar ${isOpen ? "sidebar-open" : ""} ${collapsed ? "collapsed" : ""}`}>
        <div className="sidebar-brand">
          <Logo size={28} />
          <span className="sidebar-brand-name">DocQuery</span>
          <button className="sidebar-close-btn" onClick={onClose} aria-label="Close menu">
            ✕
          </button>
          <button
            className="sidebar-collapse-btn"
            onClick={onToggleCollapse}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? "»" : "«"}
          </button>
        </div>

        <button className="new-file-btn" onClick={onNewFile} title="New File">
          <span aria-hidden="true">＋</span>
          <span className="btn-label">New File</span>
        </button>

        <div className="sidebar-header">
          <span className="sidebar-icon">🕘</span>
          <h2>History</h2>
        </div>

        <div className="sidebar-list">
          {loading && extractions.length === 0 && (
            <div className="sidebar-empty">Loading…</div>
          )}

          {loadError && <div className="sidebar-empty sidebar-error">{loadError}</div>}

          {!loading && !loadError && extractions.length === 0 && (
            <div className="sidebar-empty">
              Nothing uploaded yet. Upload a file to start a chat.
            </div>
          )}

          {extractions.map((ex) => (
            <div
              key={ex.id}
              className={`sidebar-item ${ex.id === activeId ? "active" : ""}`}
            >
              <button
                className="sidebar-item-main"
                onClick={() => onSelect(ex)}
                title={ex.filename}
              >
                <span className="sidebar-item-name">{ex.filename}</span>
                <span className="sidebar-item-meta">
                  <span className="sidebar-item-type">
                    {(ex.file_type || "").replace("-reextract", "")}
                  </span>
                  <span className="sidebar-item-time">{timeAgo(ex.created_at)}</span>
                </span>
              </button>
              <button
                className="sidebar-item-delete"
                title={`Delete ${ex.filename}`}
                aria-label={`Delete ${ex.filename}`}
                onClick={() => setPendingDelete(ex)}
              >
                🗑
              </button>
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          <button className="theme-toggle-btn" onClick={onToggleDarkMode} title={darkMode ? "Switch to light mode" : "Switch to dark mode"}>
            <span aria-hidden="true">{darkMode ? "☀" : "🌙"}</span>{" "}
            <span className="theme-toggle-label">{darkMode ? "Light mode" : "Dark mode"}</span>
          </button>
          {user && (
            <div className="sidebar-user-row">
              <span className="sidebar-user-email" title={user.email}>{user.email}</span>
              <button className="sidebar-logout-btn" onClick={logout}>Log out</button>
            </div>
          )}
        </div>
      </aside>

      <ConfirmDialog
        open={!!pendingDelete}
        title="Delete this file?"
        message={
          pendingDelete
            ? `"${pendingDelete.filename}" and its extracted data and chat history will be permanently deleted. This can't be undone.`
            : ""
        }
        confirmLabel="Delete"
        danger
        loading={deleting}
        onConfirm={handleDeleteConfirmed}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  );
}

export default Sidebar;
