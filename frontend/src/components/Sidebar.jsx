import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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

function Sidebar({ activeId, onSelect, refreshKey }) {
  const [extractions, setExtractions] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${API_URL}/extractions`);
      setExtractions(res.data.extractions || []);
    } catch (err) {
      // Silently ignore — history is a convenience, not critical path.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="sidebar-icon">🕘</span>
        <h2>History</h2>
      </div>

      <div className="sidebar-list">
        {loading && extractions.length === 0 && (
          <div className="sidebar-empty">Loading…</div>
        )}

        {!loading && extractions.length === 0 && (
          <div className="sidebar-empty">
            Nothing uploaded yet. Extract a file to start a chat.
          </div>
        )}

        {extractions.map((ex) => (
          <button
            key={ex.id}
            className={`sidebar-item ${ex.id === activeId ? "active" : ""}`}
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
        ))}
      </div>
    </aside>
  );
}

export default Sidebar;

