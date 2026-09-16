import React, { useState } from "react";
import Upload from "./components/Upload";
import Result from "./components/Result";
import SchemaEditor from "./components/SchemaEditor";
import Sidebar from "./components/Sidebar";
import Chat from "./components/Chat";
import Logo from "./components/Logo";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function App() {
  const [result, setResult] = useState(null);
  const [schema, setSchema] = useState(null);
  const [error, setError] = useState(null);
  const [reLoading, setReLoading] = useState(false);
  const [extractionId, setExtractionId] = useState(null);  // DB row ID from /extract
  const [lastFilename, setLastFilename] = useState(null);
  const [historyKey, setHistoryKey] = useState(0); // bump to refresh the sidebar

  const handleReExtract = async (editedSchema) => {
    if (!extractionId) {
      setError("No extraction found. Please upload a file first.");
      return;
    }

    setReLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch(`${API_URL}/reextract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          extraction_id: extractionId,
          schema: editedSchema,
          filename: lastFilename,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Re-extraction failed");
      }

      const data = await res.json();
      setResult(data.data);
    } catch (err) {
      setError(err.message || "Re-extraction failed");
    } finally {
      setReLoading(false);
    }
  };

  // Jump to a previously-uploaded file from the History sidebar so its
  // extracted data + chat thread can be picked back up.
  const handleSelectHistory = (ex) => {
    setExtractionId(ex.id);
    setLastFilename(ex.filename);
    setSchema(ex.schema || null);
    setResult(ex.data !== undefined ? ex.data : null);
    setError(null);
  };

  return (
    <div className="app">
      <div className="app-layout">
        <Sidebar
          activeId={extractionId}
          onSelect={handleSelectHistory}
          refreshKey={historyKey}
        />

        <div className="container">
          <header className="header">
            <div className="logo-mark">
              <Logo size={76} />
            </div>
            <h1>DocQuery</h1>
            <p className="subtitle">
              LLM-powered extraction from PDF, Excel &amp; CSV files
            </p>
          </header>

          <Upload
            setResult={setResult}
            setSchema={setSchema}
            setError={setError}
            setExtractionId={setExtractionId}
            setLastFilename={setLastFilename}
            onUploaded={() => setHistoryKey((k) => k + 1)}
          />

          {error && (
            <div className="error-banner">
              <span className="error-icon">⚠</span>
              {error}
            </div>
          )}

          {schema && (
            <div className="results-area">
              <SchemaEditor
                schema={schema}
                onReExtract={handleReExtract}
                loading={reLoading}
              />
            </div>
          )}

          {result && (
            <div className="results-area">
              <Result result={result} label="Extracted Output JSON" />
            </div>
          )}

          <div className="results-area">
            <Chat extractionId={extractionId} filename={lastFilename} />
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;

