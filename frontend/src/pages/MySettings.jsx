import { useState } from "react";
import { KeyRound, Save, ShieldCheck, Trash2 } from "lucide-react";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/auth/AuthContext";

export default function MySettings({ onNotice }) {
  const { user, refresh } = useAuth();
  const [rosUser, setRosUser] = useState(user?.ros_username || "");
  const [rosPass, setRosPass] = useState("");
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [busy, setBusy] = useState("");

  const saveRos = async (e) => {
    e.preventDefault(); setBusy("ros");
    try { await api.put("/auth/me/ros-credentials", { username: rosUser.trim(), password: rosPass }); setRosPass(""); await refresh(); onNotice("MikroTik credentials saved — router sessions will use them"); }
    catch (err) { onNotice(errorText(err)); } finally { setBusy(""); }
  };
  const clearRos = async () => {
    setBusy("clear");
    try { await api.delete("/auth/me/ros-credentials"); setRosUser(""); await refresh(); onNotice("MikroTik credentials removed"); }
    catch (err) { onNotice(errorText(err)); } finally { setBusy(""); }
  };
  const savePw = async (e) => {
    e.preventDefault(); setBusy("pw");
    try { await api.put("/auth/me/password", pw); setPw({ current_password: "", new_password: "" }); onNotice("Password updated"); }
    catch (err) { onNotice(errorText(err)); } finally { setBusy(""); }
  };

  return <div className="settings-grid" data-testid="my-settings-view">
    <section className="panel notif-panel">
      <div className="panel-head"><div><p className="eyebrow">MIKROTIK ACCESS</p><h2>My RouterOS credentials</h2></div><span className="api-lock"><ShieldCheck size={13} />Encrypted at rest</span></div>
      <p className="notif-help">Routers shared with you only expose their name and IP. To open one, NetPulse logs in to the router with <b>your own</b> MikroTik user below. If your MikroTik user has read-only policy, edits will show <b>"not enough permission"</b>.</p>
      <div className="tg-status" style={{ marginBottom: 12 }}>{user?.has_ros_credentials ? <span className="tg-pill on" data-testid="ros-creds-status">Configured · {user.ros_username}</span> : <span className="tg-pill off" data-testid="ros-creds-status">Not configured</span>}</div>
      <form onSubmit={saveRos} className="add-form">
        <div className="two-col">
          <label>MikroTik username<input required value={rosUser} onChange={e => setRosUser(e.target.value)} placeholder="admin" autoComplete="off" data-testid="ros-username" /></label>
          <label>MikroTik password<input type="password" required value={rosPass} onChange={e => setRosPass(e.target.value)} placeholder="••••••••" autoComplete="new-password" data-testid="ros-password" /></label>
        </div>
        <div className="modal-actions">
          {user?.has_ros_credentials && <button type="button" className="button secondary" onClick={clearRos} disabled={busy === "clear"} data-testid="ros-clear"><Trash2 size={14} />Remove</button>}
          <button type="submit" className="button primary" disabled={busy === "ros"} data-testid="ros-save"><KeyRound size={14} />{busy === "ros" ? "Saving..." : "Save credentials"}</button>
        </div>
      </form>
    </section>
    <section className="panel notif-panel">
      <div className="panel-head"><div><p className="eyebrow">ACCOUNT</p><h2>{user?.name}</h2></div><span className="group-label">{user?.is_super_admin ? "Super Admin" : user?.role?.name || "No role"}</span></div>
      <p className="notif-help mono">{user?.email}</p>
      {user?.auth_provider !== "google" && <form onSubmit={savePw} className="add-form">
        <label>Current password<input type="password" value={pw.current_password} onChange={e => setPw(p => ({ ...p, current_password: e.target.value }))} autoComplete="current-password" data-testid="pw-current" /></label>
        <label>New password (min 8)<input type="password" required minLength={8} value={pw.new_password} onChange={e => setPw(p => ({ ...p, new_password: e.target.value }))} autoComplete="new-password" data-testid="pw-new" /></label>
        <div className="modal-actions"><button type="submit" className="button primary" disabled={busy === "pw"} data-testid="pw-save"><Save size={14} />{busy === "pw" ? "Saving..." : "Change password"}</button></div>
      </form>}
    </section>
  </div>;
}
