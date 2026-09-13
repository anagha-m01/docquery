import React, { useState } from "react";
import axios from "axios";

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

function Upload({ setResult, setSchema, setError, setExtractionId, setLastFilename, onUploaded }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const handleFile = (selected) => {
    setFile(selected);
    setError(null);
    setResult(null);
    setSchema(null);
    setExtractionId(null);
    setLastFilename(null);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFile(dropped);
  };

  const handleUpload = async () => {
    if (!file) return setError("Please select a file first.");

    const formData = new FormData();
    formData.append("file", file);

    try {
      setLoading(true);
      setError(null);
      setSchema(null);
      setResult(null);

      const res = await axios.post(`${API_URL}/extract`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      // Store the DB row ID — used by /reextract to fetch raw_text from DB
      setExtractionId(res.data.id);
      setLastFilename(file.name);

      const payload = res.data.data;
      if (payload.schema) setSchema(payload.schema);
      if (payload.data !== undefined) setResult(payload.data);
      else setResult(payload);

      if (onUploaded) onUploaded();

    } catch (err) {
      const msg =
        err.response?.data?.detail ||
        err.message ||
        "Extraction failed. Please try again.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="upload-section">
      <div
        className={`drop-zone ${dragOver ? "drag-over" : ""} ${file ? "has-file" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => document.getElementById("file-input").click()}
      >
        <input
          id="file-input"
          type="file"
          accept=".pdf,.xlsx,.xls,.csv"
          style={{ display: "none" }}
          onChange={(e) => handleFile(e.target.files[0])}
        />
        <div className="drop-icon">{file ? "📄" : "⬆"}</div>
        <div className="drop-text">
          {file ? (
            <>
              <span className="file-name">{file.name}</span>
              <span className="file-size">({(file.size / 1024).toFixed(1)} KB)</span>
            </>
          ) : (
            <>
              <span>Drop your file here or <u>browse</u></span>
              <span className="drop-hint">PDF · Excel · CSV</span>
            </>
          )}
        </div>
      </div>

      <button
        className={`extract-btn ${loading ? "loading" : ""}`}
        onClick={handleUpload}
        disabled={loading || !file}
      >
        {loading ? (
          <span className="btn-inner">
            <span className="spinner" /> Extracting...
          </span>
        ) : (
          "Extract Data"
        )}
      </button>
    </div>
  );
}

export default Upload;
