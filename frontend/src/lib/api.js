import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
export const TOKEN_KEY = "netpulse_token";
export const WS_KEY = "netpulse_workspace";

export const api = axios.create({ baseURL: API, withCredentials: true });

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem(TOKEN_KEY);
  const ws = localStorage.getItem(WS_KEY);
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  if (ws) cfg.headers["X-Workspace"] = ws;
  return cfg;
});

api.interceptors.response.use(r => r, err => {
  if (err.response?.status === 401 && !String(err.config?.url || "").includes("/auth/")) {
    localStorage.removeItem(TOKEN_KEY);
    window.dispatchEvent(new Event("netpulse:unauthorized"));
  }
  return Promise.reject(err);
});

export function errorText(err, fallbackMsg = "Something went wrong") {
  const detail = err?.response?.data?.detail;
  if (detail == null) return err?.message || fallbackMsg;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(e => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).join(" ");
  if (typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export const slug = (s) => String(s).toLowerCase().replaceAll(/[^a-z0-9]+/g, "-");
