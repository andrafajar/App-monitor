import { useEffect, useState } from "react";
import { BellRing, Loader2, Save } from "lucide-react";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/auth/AuthContext";

const MODES = [
  { id: "all", label: "All interfaces", hint: "every enabled interface, including VLANs and bridges" },
  { id: "ethernet", label: "Ethernet & SFP only", hint: "physical ports (ether*, sfp*, combo*)" },
  { id: "selected", label: "Only the interfaces I pick", hint: "choose from the live list below" },
  { id: "off", label: "Do not watch interfaces", hint: "CPU and unreachable alarms still apply" },
];

export function AlarmWatchPanel({ routerId, routerName, onNotice }) {
  const { can } = useAuth();
  const [data, setData] = useState(null);
  const [mode, setMode] = useState("all");
  const [picked, setPicked] = useState([]);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const writable = can("alarms", "write");

  const load = async () => {
    try {
      const r = await api.get(`/routers/${routerId}/alarm-interfaces`);
      setData(r.data); setMode(r.data.mode); setPicked(r.data.interfaces || []);
    } catch (err) { onNotice(errorText(err, "Could not read interface list")); setData({ available: [], watching: [] }); }
  };
  useEffect(() => { load(); }, [routerId]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (name) => setPicked(p => (p.includes(name) ? p.filter(x => x !== name) : [...p, name]));
  const save = async () => {
    setBusy(true);
    try { await api.put(`/routers/${routerId}/alarm-interfaces`, { mode, interfaces: picked }); onNotice(`${routerName}: interface watch saved (${mode})`); load(); }
    catch (err) { onNotice(errorText(err, "Save failed")); } finally { setBusy(false); }
  };

  if (!data) return <div className="res-loading" data-testid="alarm-watch-loading"><Loader2 size={14} className="spin" />Reading interfaces…</div>;
  const list = (data.available || []).filter(i => `${i.name} ${i.type}`.toLowerCase().includes(filter.toLowerCase()));
  return <div data-testid="alarm-watch-panel">
    <div className="res-toolbar"><b data-testid="alarm-watch-count">{data.watching?.length || 0} interface{data.watching?.length === 1 ? "" : "s"} watched now</b>
      {writable && <button className="button primary compact" onClick={save} disabled={busy} data-testid="alarm-watch-save">{busy ? <Loader2 size={13} className="spin" /> : <Save size={13} />}Save watch list</button>}</div>
    <p className="backup-note"><BellRing size={12} /> Every 15 minutes NetPulse compares the running state of the watched interfaces and sends an up/down alarm to the Telegram channel of each role that covers this router's group.</p>
    <div className="watch-modes">
      {MODES.map(m => <label key={m.id} className={`watch-mode ${mode === m.id ? "on" : ""}`} data-testid={`alarm-watch-mode-${m.id}`}>
        <input type="radio" name="watch-mode" checked={mode === m.id} onChange={() => setMode(m.id)} disabled={!writable} />
        <div><b>{m.label}</b><span className="muted">{m.hint}</span></div>
      </label>)}
    </div>
    {mode === "selected" && <>
      <div className="res-toolbar"><b>{picked.length} selected</b><div className="res-tools"><input className="watch-filter" value={filter} onChange={e => setFilter(e.target.value)} placeholder="Filter interfaces…" data-testid="alarm-watch-filter" /></div></div>
      <div className="watch-list" data-testid="alarm-watch-list">
        {list.length === 0 && <span className="muted">{data.error ? `Interface list unavailable (${data.error})` : "No interfaces match."}</span>}
        {list.map(i => <label key={i.name} className={`watch-item ${picked.includes(i.name) ? "on" : ""}`} data-testid={`alarm-watch-iface-${i.name}`}>
          <input type="checkbox" checked={picked.includes(i.name)} onChange={() => toggle(i.name)} disabled={!writable} />
          <b>{i.name}</b><span className="muted">{i.type}</span>{i.running ? <span className="tg-pill on">up</span> : <span className="tg-pill off">down</span>}
        </label>)}
      </div>
    </>}
  </div>;
}
