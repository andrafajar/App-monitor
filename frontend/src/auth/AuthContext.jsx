import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, TOKEN_KEY, WS_KEY } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking, false = anonymous
  const [workspaceId, setWorkspaceState] = useState(localStorage.getItem(WS_KEY) || "");

  const applyUser = useCallback((u) => {
    setUser(u || false);
    if (u) {
      const stored = localStorage.getItem(WS_KEY);
      const next = u.workspace_ids.includes(stored) ? stored : (u.workspace_ids[0] || "");
      localStorage.setItem(WS_KEY, next); setWorkspaceState(next);
    }
  }, []);

  const refresh = useCallback(async () => {
    try { const r = await api.get("/auth/me"); applyUser(r.data); return r.data; }
    catch { applyUser(false); return null; }
  }, [applyUser]);

  useEffect(() => {
    // CRITICAL: skip /me when returning from Google OAuth; AuthCallback exchanges session_id first.
    if (window.location.hash?.includes("session_id=")) { setUser(false); return; }
    refresh();
  }, [refresh]);

  useEffect(() => {
    const onUnauth = () => setUser(false);
    window.addEventListener("netpulse:unauthorized", onUnauth);
    return () => window.removeEventListener("netpulse:unauthorized", onUnauth);
  }, []);

  const login = async (email, password) => {
    const r = await api.post("/auth/login", { email, password });
    localStorage.setItem(TOKEN_KEY, r.data.access_token); applyUser(r.data.user); return r.data.user;
  };
  const exchangeSession = async (sessionId) => {
    const r = await api.post("/auth/session", { session_id: sessionId });
    localStorage.setItem(TOKEN_KEY, r.data.access_token); applyUser(r.data.user); return r.data.user;
  };
  const logout = async () => {
    try { await api.post("/auth/logout"); } catch { /* ignore */ }
    localStorage.removeItem(TOKEN_KEY); setUser(false);
  };
  const setWorkspaceId = (id) => { localStorage.setItem(WS_KEY, id); setWorkspaceState(id); };
  const can = (module, level = "read") => {
    if (!user) return false;
    if (user.is_super_admin) return true;
    const rank = { none: 0, read: 1, write: 2 };
    return (rank[user.privileges?.[module] || "none"] || 0) >= rank[level];
  };

  return <AuthContext.Provider value={{ user, login, logout, refresh, exchangeSession, workspaceId, setWorkspaceId, can }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
