import React from "react";
import { Light as SyntaxHighlighter } from "react-syntax-highlighter";
import json from "react-syntax-highlighter/dist/esm/languages/hljs/json";
import { atomOneDark } from "react-syntax-highlighter/dist/esm/styles/hljs";

SyntaxHighlighter.registerLanguage("json", json);

function Result({ result, label }) {
  if (!result) return null;

  const jsonStr = JSON.stringify(result, null, 2);

  const handleDownload = () => {
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${label || "output"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="result-block">
      <div className="result-header">
        <h3>{label}</h3>
        <button className="download-btn" onClick={handleDownload} title="Download JSON">
          ⬇ Download
        </button>
      </div>
      <div className="code-wrapper">
        <SyntaxHighlighter
          language="json"
          style={atomOneDark}
          customStyle={{ margin: 0, padding: "20px", background: "transparent", fontSize: "13px" }}
        >
          {jsonStr}
        </SyntaxHighlighter>
      </div>
    </div>
  );
}

export default Result;
