import axios from "axios";

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const TOKEN_KEY = "docquery_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

const api = axios.create({ baseURL: API_URL });

// Attach the bearer token to every request automatically.
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// A 401 means the token is missing/expired — clear it and let the app
// fall back to the login screen. We dispatch a custom event instead of
// importing AuthContext here to avoid a circular import.
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      setToken(null);
      window.dispatchEvent(new CustomEvent("docquery:unauthorized"));
    }
    return Promise.reject(err);
  }
);

export function extractErrorMessage(err, fallback) {
  return err.response?.data?.detail || err.message || fallback;
}

export default api;