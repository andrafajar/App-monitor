import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Activity, AlertTriangle, CircleGauge, Lock, Network, Router } from "lucide-react";
import axios from "axios";
import { AggregateTrafficChart } from "@/components/TrafficPanel";
import { Status } from "@/components/Status";
import "@/App.css";

const raw = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL}/api/public` });

export default function DisplayBoard() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try { const r = await raw.get(`/display/${token}`); if (alive) { setData(r.data); setError(""); } }
      catch (err) { if (alive) setError(err.response?.status === 404 ? "This display link is not active. Ask an administrator to enable it." : "Display temporarily unavailable"); }
    };
    load();
    const t = setInterval(load, 15000);
    return () => { alive = false; clearInterval(t); };
  }, [token]);

  if (error) return <div className="display-shell"><div className="display-empty" data-testid="display-error"><Lock size={18} />{error}</div></div>;
  if (!data) return <div className="display-shell"><div className="display-empty"><Activity size={18} />Loading board…</div></div>;

  const health = data.counts.total ? Math.round(data.counts.online * 100 / data.counts.total) : 0;
  return <div className="display-shell" data-testid="display-board">
    <header className="display-top">
      <div className="brand-mark"><Network size={20} /></div>
      <div><b data-testid="display-title">{data.workspace.title}</b><span>NetPulse NOC display · read only · refreshes every 15s</span></div>
      <a className="button secondary compact" href="/login" data-testid="display-signin"><Lock size={13} />Sign in to manage</a>
    </header>
    <div className="display-metrics">
      <div className="metric"><div className="metric-icon cyan"><Router size={17} /></div><div><p>Devices</p><strong data-testid="display-total">{data.counts.total}</strong><small>{data.counts.online} online · {data.counts.offline} offline</small></div></div>
      <div className="metric"><div className="metric-icon green"><CircleGauge size={17} /></div><div><p>Reachability</p><strong>{health}%</strong><small>via RouterOS API</small></div></div>
      <div className="metric"><div className="metric-icon amber"><AlertTriangle size={17} /></div><div><p>Alarms 24h</p><strong>{data.counts.alarms_24h}</strong><small>dispatched to Telegram roles</small></div></div>
      <div className="metric"><div className="metric-icon violet"><Activity size={17} /></div><div><p>Aggregate now</p><strong>{data.traffic.length ? `${data.traffic[data.traffic.length - 1].inbound} / ${data.traffic[data.traffic.length - 1].outbound}` : "—"}</strong><small>Mbps in / out</small></div></div>
    </div>
    <div className="display-grid">
      <section className="panel traffic-panel"><div className="panel-head"><div><p className="eyebrow">LIVE BANDWIDTH</p><h2>Aggregate traffic</h2></div></div>
        {data.traffic.length ? <AggregateTrafficChart data={data.traffic} /> : <div className="drawer-message"><Activity size={16} />Waiting for the first bandwidth sample.</div>}</section>
      <section className="panel alarm-panel"><div className="panel-head"><div><p className="eyebrow">SIGNAL CENTER</p><h2>Recent alarms</h2></div></div>
        <div className="alarm-list">{data.alarms.length === 0 && <div className="drawer-message"><AlertTriangle size={16} />No alarms.</div>}
          {data.alarms.map((a, i) => <div key={i} className={`alarm-item ${a.kind === "router-unreachable" ? "danger" : a.kind === "cpu-threshold" ? "warning" : "info"}`} data-testid={`display-alarm-${i}`}>
            <div className="alarm-symbol"><AlertTriangle size={16} /></div><div><b>{a.kind}</b><span>{a.device} · {a.detail}</span><small>{new Date(a.created_at).toLocaleString()}</small></div></div>)}</div></section>
    </div>
    <section className="panel routers-panel"><div className="panel-head table-head"><div><p className="eyebrow">FLEET / {data.counts.total} DEVICES</p><h2>Device health</h2></div></div>
      <div className="table-wrap"><table><thead><tr><th>DEVICE</th><th>GROUP</th><th>STATUS</th><th>CPU</th><th>MEMORY</th><th>VERSION</th><th>UPTIME</th></tr></thead><tbody>
        {data.devices.map(d => <tr key={d.id} onClick={() => { window.location.href = "/login"; }} data-testid={`display-device-${d.id}`}>
          <td><div className="router-name"><div className="router-icon cyan"><Router size={15} /></div><div><b>{d.name}</b><span>{d.host || "sign in to see addressing"}</span></div></div></td>
          <td><span className="group-label">{d.group}</span></td><td><Status value={d.status} /></td>
          <td><div className="bar-value"><span>{d.cpu}%</span><i><b style={{ width: `${d.cpu}%` }} /></i></div></td>
          <td><div className="bar-value"><span>{d.memory ? `${d.memory}%` : "—"}</span><i><b className={d.memory > 70 ? "warn" : ""} style={{ width: `${d.memory}%` }} /></i></div></td>
          <td className="mono">{d.version}</td><td className="muted">{d.uptime}</td>
        </tr>)}
      </tbody></table></div></section>
    <p className="display-foot">Clicking a device opens the sign-in page — configuration, credentials and terminals stay behind login.</p>
  </div>;
}
