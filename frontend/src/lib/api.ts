import axios from "axios";
import { getToken } from "./auth";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/** API host root (no /api/v1) — for host-level endpoints like /health. */
export const API_ROOT = BASE;

export const api = axios.create({
  baseURL: `${BASE}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    console.error("[API]", err.response?.status, err.response?.data ?? err.message);
    if (err.response?.status === 401) {
      // Token expired or invalid — clear storage, reload triggers auth gate in App.tsx
      localStorage.removeItem("tap_token");
      localStorage.removeItem("tap_user");
      window.location.reload();
    }
    return Promise.reject(err);
  }
);

export const WS_BASE = (import.meta.env.VITE_WS_URL ?? "ws://localhost:8000") + "/api/v1/ws";

/** WebSocket URL with the auth token attached — the server rejects unauthenticated sockets. */
export function wsUrl(path: string): string {
  const token = getToken();
  return `${WS_BASE}${path}${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}
