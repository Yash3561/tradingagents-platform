import axios from "axios";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const api = axios.create({
  baseURL: `${BASE}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    console.error("[API]", err.response?.status, err.response?.data ?? err.message);
    return Promise.reject(err);
  }
);

export const WS_BASE = (import.meta.env.VITE_WS_URL ?? "ws://localhost:8000") + "/api/v1/ws";
