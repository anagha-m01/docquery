import React, { useState } from "react";
import Upload from "./components/Upload";
import Result from "./components/Result";
import SchemaEditor from "./components/SchemaEditor";
import "./App.css";

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

function App() {
  const [result, setResult] = useState(null);
  const [schema, setSchema] = useState(null);
  const [error, setError] = useState(null);
  const [reLoading, setReLoading] = useState(false);
  const [extractionId, setExtractionId] = useState(null);  // DB row ID from /extract
  const [lastFilename, setLastFilename] = useState(null);

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

  return (
    <div className="app">
      <div className="container">
        <header className="header">
          <div className="logo-mark">⬡</div>
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
      </div>
    </div>
  );
}

export default App;