import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import api, { getToken, setToken, extractErrorMessage } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // "checking" avoids a login-screen flash while we verify a stored token.
  const [status, setStatus] = useState("checking");

  const loadMe = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setStatus("loggedOut");
      return;
    }
    try {
      const res = await api.get("/auth/me");
      setUser(res.data);
      setStatus("loggedIn");
    } catch {
      setToken(null);
      setUser(null);
      setStatus("loggedOut");
    }
  }, []);

  useEffect(() => {
    loadMe();
    const onUnauthorized = () => {
      setUser(null);
      setStatus("loggedOut");
    };
    window.addEventListener("docquery:unauthorized", onUnauthorized);
    return () => window.removeEventListener("docquery:unauthorized", onUnauthorized);
  }, [loadMe]);

  const login = useCallback(async (email, password) => {
    try {
      const res = await api.post("/auth/login", { email, password });
      setToken(res.data.access_token);
      setUser(res.data.user);
      setStatus("loggedIn");
      return { ok: true };
    } catch (err) {
      return { ok: false, message: extractErrorMessage(err, "Login failed.") };
    }
  }, []);

  const register = useCallback(async (email, password) => {
    try {
      const res = await api.post("/auth/register", { email, password });
      setToken(res.data.access_token);
      setUser(res.data.user);
      setStatus("loggedIn");
      return { ok: true };
    } catch (err) {
      return { ok: false, message: extractErrorMessage(err, "Registration failed.") };
    }
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setStatus("loggedOut");
  }, []);

  return (
    <AuthContext.Provider value={{ user, status, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
