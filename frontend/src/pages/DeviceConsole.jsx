import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { AlertTriangle, Loader2, Network } from "lucide-react";
import { WorkspacePage } from "@/components/RouterWorkspace";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/auth/AuthContext";
import Login from "@/pages/Login";
import "@/App.css";

/** Standalone console window for one device only (Proxmox-style popup) — no sidebar, no fleet navigation. */
export default function DeviceConsole() {
  const { routerId } = useParams();
  const [params] = useSearchParams();
  const { user, can } = useAuth();  // user: null = checking, false = anonymous
  const [device, setDevice] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = async () => {
    try { const r = await api.get(`/routers/${routerId}`); setDevice(r.data.router); setError(""); }
    catch (e) { setError(errorText(e, "This device is not available for your account")); }
  };
  useEffect(() => { if (user) load(); }, [user, routerId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (device) document.title = `${device.name} · NetPulse console`; }, [device]);
  useEffect(() => { if (!notice) return; const t = setTimeout(() => setNotice(""), 4000); return () => clearTimeout(t); }, [notice]);

  if (user === null) return <div className="display-shell"><div className="display-empty"><Loader2 size={18} className="spin" />Opening console…</div></div>;
  if (user === false) return <Login />;
  if (error) return <div className="display-shell"><div className="display-empty" data-testid="console-error"><AlertTriangle size={18} />{error}</div></div>;
  if (!device) return <div className="display-shell"><div className="display-empty"><Loader2 size={18} className="spin" />Loading {routerId}…</div></div>;

  return <div className="console-shell" data-testid="device-console">
    <header className="console-top"><div className="brand-mark"><Network size={16} /></div>
      <div><b>NetPulse console</b><span>single device window · read-write follows your role</span></div>
      <button className="button secondary compact" onClick={() => window.close()} data-testid="console-close">Close window</button>
    </header>
    {notice && <div className="console-notice" data-testid="console-notice">{notice}</div>}
    <WorkspacePage router={device} initialCat={params.get("cat") || ""} onNotice={setNotice} onRefresh={load}
      onGoSettings={() => window.open("/?nav=my-settings", "_blank", "noopener")} canWriteRouters={can("routers", "write")} />
  </div>;
}
