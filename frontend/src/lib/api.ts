import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { getToken, getRefreshToken, saveTokens, clearAuth } from "./auth";

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

// ── Silent session refresh ─────────────────────────────────────────────────────
// Access tokens live 30 minutes; on a 401 we exchange the refresh token for a
// new pair (single-flight so parallel 401s share one refresh) and retry once.

let refreshInFlight: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) throw new Error("no refresh token");
  // Plain axios: must not recurse through the api instance's interceptors
  const { data } = await axios.post(`${BASE}/api/v1/auth/refresh`, {
    refresh_token: refreshToken,
  });
  saveTokens(data.access_token, data.refresh_token);
  return data.access_token as string;
}

function logoutToLogin(): void {
  clearAuth();
  window.location.reload();
}

api.interceptors.response.use(
  (res) => res,
  async (err: AxiosError) => {
    const original = err.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    const status = err.response?.status;
    const isAuthCall = original?.url?.includes("/auth/") ?? false;

    if (status === 401 && original && !original._retried && !isAuthCall) {
      original._retried = true;
      try {
        refreshInFlight ??= refreshAccessToken().finally(() => {
          refreshInFlight = null;
        });
        const newToken = await refreshInFlight;
        original.headers.Authorization = `Bearer ${newToken}`;
        return api.request(original);
      } catch {
        logoutToLogin();
        return Promise.reject(err);
      }
    }

    console.error("[API]", status, err.response?.data ?? err.message);
    if (status === 401 && !isAuthCall) {
      // Retried and still unauthorized — session is truly dead
      logoutToLogin();
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
