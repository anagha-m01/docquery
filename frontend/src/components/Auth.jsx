import React, { useState } from "react";
import Logo from "./Logo";
import { useAuth } from "../context/AuthContext";

function Auth() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState("login"); // 'login' | 'register'
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const action = mode === "login" ? login : register;
    const result = await action(email.trim(), password);

    if (!result.ok) setError(result.message);
    setLoading(false);
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">
          <Logo size={56} />
        </div>
        <h1 className="auth-title">DocQuery</h1>
        <p className="auth-subtitle">
          {mode === "login" ? "Sign in to your account" : "Create an account to get started"}
        </p>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="auth-label">
            Email
            <input
              type="email"
              className="auth-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
          </label>

          <label className="auth-label">
            Password
            <input
              type="password"
              className="auth-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={mode === "register" ? 8 : undefined}
              required
            />
          </label>

          {mode === "register" && (
            <p className="auth-hint">Use at least 8 characters.</p>
          )}

          {error && (
            <div className="error-banner auth-error">
              <span className="error-icon">⚠</span>
              {error}
            </div>
          )}

          <button className={`auth-submit-btn ${loading ? "loading" : ""}`} disabled={loading}>
            {loading ? (
              <span className="btn-inner">
                <span className="spinner" />
                {mode === "login" ? "Signing in…" : "Creating account…"}
              </span>
            ) : mode === "login" ? (
              "Sign In"
            ) : (
              "Create Account"
            )}
          </button>
        </form>

        <button
          type="button"
          className="auth-switch-btn"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setError(null);
          }}
        >
          {mode === "login"
            ? "Don't have an account? Sign up"
            : "Already have an account? Sign in"}
        </button>
      </div>
    </div>
  );
}

export default Auth;
