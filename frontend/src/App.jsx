import React, { useEffect, useState } from "react";
import Upload from "./components/Upload";
import Result from "./components/Result";
import SchemaEditor from "./components/SchemaEditor";
import Sidebar from "./components/Sidebar";
import Chat from "./components/Chat";
import Logo from "./components/Logo";
import Auth from "./components/Auth";
import api, { extractErrorMessage } from "./api/client";
import { useAuth } from "./context/AuthContext";
import "./App.css";

const THEME_KEY = "docquery_theme";
const SIDEBAR_KEY = "docquery_sidebar_collapsed";

function AppShell() {
  const [result, setResult] = useState(null);
  const [schema, setSchema] = useState(null);
  const [error, setError] = useState(null);
  const [reLoading, setReLoading] = useState(false);
  const [extractionId, setExtractionId] = useState(null);  // DB row ID from /extract
  const [lastFilename, setLastFilename] = useState(null);
  const [lastFileType, setLastFileType] = useState(null);
  const [historyKey, setHistoryKey] = useState(0); // bump to refresh the sidebar
  const [sidebarOpen, setSidebarOpen] = useState(false); // mobile drawer
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(SIDEBAR_KEY) === "1";
  });
  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(THEME_KEY) === "dark";
  });

  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed ? "1" : "0");
  }, [sidebarCollapsed]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", darkMode ? "dark" : "light");
    localStorage.setItem(THEME_KEY, darkMode ? "dark" : "light");
  }, [darkMode]);

  const handleReExtract = async (editedSchema) => {
    if (!extractionId) {
      setError("No extraction found. Please upload a file first.");
      return;
    }

    setReLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await api.post("/reextract", {
        extraction_id: extractionId,
        schema: editedSchema,
        filename: lastFilename,
      });
      setResult(res.data.data);
    } catch (err) {
      setError(extractErrorMessage(err, "Re-extraction failed"));
    } finally {
      setReLoading(false);
    }
  };

  // Jump to a previously-uploaded file from the History sidebar so its
  // extracted data + chat thread can be picked back up.
  const handleSelectHistory = (ex) => {
    setExtractionId(ex.id);
    setLastFilename(ex.filename);
    setLastFileType((ex.file_type || "").replace("-reextract", ""));
    setSchema(ex.schema || null);
    setResult(ex.data !== undefined ? ex.data : null);
    setError(null);
    setSidebarOpen(false);
  };

  // "New File" — clears the active document so the upload panel takes
  // over again. Used both from the sidebar button and after deleting the
  // currently-open file.
  const handleNewFile = () => {
    setExtractionId(null);
    setLastFilename(null);
    setLastFileType(null);
    setSchema(null);
    setResult(null);
    setError(null);
    setSidebarOpen(false);
  };

  return (
    <div className="app">
      <div className={`app-layout ${sidebarCollapsed ? "sidebar-is-collapsed" : ""}`}>
        <Sidebar
          activeId={extractionId}
          onSelect={handleSelectHistory}
          onNewFile={handleNewFile}
          refreshKey={historyKey}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
          darkMode={darkMode}
          onToggleDarkMode={() => setDarkMode((d) => !d)}
        />

        <div className="container">
          <header className="header">
            <button
              className="mobile-menu-btn"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open menu"
            >
              ☰
            </button>
            <div className="logo-mark">
              <Logo size={56} />
            </div>
            <h1>DocQuery</h1>
            <p className="subtitle">
              LLM-powered extraction from PDF, Excel &amp; CSV files
            </p>
          </header>

          {extractionId && (
            <div className="active-doc-banner">
              <div className="active-doc-info">
                <span className="active-doc-icon">📄</span>
                <div>
                  <span className="active-doc-name">{lastFilename}</span>
                  {lastFileType && <span className="active-doc-type">{lastFileType}</span>}
                </div>
              </div>
              <button className="new-file-btn new-file-btn-inline" onClick={handleNewFile}>
                <span aria-hidden="true">＋</span> New File
              </button>
            </div>
          )}

          {!extractionId && (
            <Upload
              setResult={setResult}
              setSchema={setSchema}
              setError={setError}
              setExtractionId={setExtractionId}
              setLastFilename={(name) => {
                setLastFilename(name);
                setLastFileType(null);
              }}
              onUploaded={() => setHistoryKey((k) => k + 1)}
            />
          )}

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

function App() {
  const { status } = useAuth();

  if (status === "checking") {
    return (
      <div className="app-loading-screen">
        <span className="spinner" />
      </div>
    );
  }

  return status === "loggedIn" ? <AppShell /> : <Auth />;
}

export default App;
