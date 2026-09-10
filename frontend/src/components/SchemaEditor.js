import React, { useState, useEffect } from "react";

function SchemaEditor({ schema, onReExtract, loading }) {
  const [text, setText] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (schema) setText(JSON.stringify(schema, null, 2));
  }, [schema]);

  const handleReExtract = () => {
    try {
      const parsed = JSON.parse(text);
      setError("");
      onReExtract(parsed);
    } catch (e) {
      setError("Invalid JSON — check your syntax and try again.");
    }
  };

  return (
    <div className="result-block">
      <div className="result-header">
        <h3>Input JSON Structure</h3>
        <span className="se-badge">Editable</span>
      </div>

      <textarea
        className="schema-textarea"
        value={text}
        onChange={e => { setText(e.target.value); setError(""); }}
        spellCheck={false}
      />

      {error && <div className="se-error">⚠ {error}</div>}

      <div className="se-reextract-bar">
        <span className="se-hint">Edit the schema then re-extract to get output in your format.</span>
        <button
          className={`re-extract-btn ${loading ? "loading" : ""}`}
          onClick={handleReExtract}
          disabled={loading}
        >
          {loading ? (
            <span className="btn-inner"><span className="spinner" /> Re-Extracting...</span>
          ) : (
            "⟳  Re-Extract with this Schema"
          )}
        </button>
      </div>
    </div>
  );
}

export default SchemaEditor;