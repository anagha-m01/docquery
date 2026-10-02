import React from "react";

function ConfirmDialog({ open, title, message, confirmLabel = "Confirm", danger = false, loading = false, onConfirm, onCancel }) {
  if (!open) return null;

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <h3 className="modal-title">{title}</h3>
        <p className="modal-message">{message}</p>
        <div className="modal-actions">
          <button className="modal-btn modal-btn-cancel" onClick={onCancel} disabled={loading}>
            Cancel
          </button>
          <button
            className={`modal-btn ${danger ? "modal-btn-danger" : "modal-btn-primary"}`}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? (
              <span className="btn-inner">
                <span className="spinner" /> Working…
              </span>
            ) : (
              confirmLabel
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmDialog;
