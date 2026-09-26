import { useEffect, useRef, useState } from "react";
import { Activity, Loader2, Pause, Play } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorText } from "@/lib/api";
import { PermissionPopup } from "@/components/ConfigEditor";

const fmt = (mbps) => (mbps >= 1 ? `${mbps.toFixed(2)} Mbps` : `${(mbps * 1000).toFixed(0)} kbps`);

export function TrafficPanel({ routerId, onGoSettings }) {
  const [state, setState] = useState({ loading: true, error: "", items: [], totals: null, interval: 0 });
  const [series, setSeries] = useState([]);
  const [focus, setFocus] = useState("__all__");
  const [paused, setPaused] = useState(false);
  const [permErr, setPermErr] = useState(null);
  const timer = useRef(null);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const r = await api.get(`/routers/${routerId}/traffic`);
        if (!alive) return;
        setState({ loading: false, error: "", items: r.data.items || [], totals: r.data.totals, interval: r.data.interval });
        if (r.data.interval > 0) setSeries(s => [...s.slice(-39), {
          time: new Date(r.data.sampled_at).toLocaleTimeString(),
          total: { inbound: r.data.totals.rx_mbps, outbound: r.data.totals.tx_mbps },
          byIface: Object.fromEntries((r.data.items || []).map(i => [i.name, { inbound: i.rx_mbps, outbound: i.tx_mbps }])),
        }]);
      } catch (err) {
        if (!alive) return;
        if ([403, 428, 401].includes(err.response?.status)) setPermErr(err);
        setState(s => ({ ...s, loading: false, error: errorText(err, "Could not read interface counters") }));
      }
    };
    poll();
    timer.current = setInterval(() => { if (!paused) poll(); }, 5000);
    return () => { alive = false; clearInterval(timer.current); };
  }, [routerId, paused]);

  if (state.loading) return <div className="res-loading" data-testid="traffic-loading"><Loader2 size={14} className="spin" />Sampling interface counters…</div>;
  if (state.error) return <><div className="res-error" data-testid="traffic-error">{state.error}</div><PermissionPopup error={permErr} onClose={() => setPermErr(null)} onGoSettings={onGoSettings} /></>;

  const max = Math.max(1, ...state.items.flatMap(i => [i.rx_mbps, i.tx_mbps]));
  const picked = focus === "__all__" ? null : state.items.find(i => i.name === focus);
  const chartData = series.map(p => ({ time: p.time, ...(focus === "__all__" ? p.total : (p.byIface?.[focus] || { inbound: 0, outbound: 0 })) }));
  const head = focus === "__all__" ? { rx: state.totals?.rx_mbps || 0, tx: state.totals?.tx_mbps || 0 } : { rx: picked?.rx_mbps || 0, tx: picked?.tx_mbps || 0 };
  return <>
    <div className="res-toolbar">
      <b data-testid="traffic-total">↓ {fmt(head.rx)} · ↑ {fmt(head.tx)}<span className="muted"> · {focus === "__all__" ? "all uplinks" : focus}</span></b>
      <div className="res-tools">
        <span className="graph-picker">Interface
          <select value={focus} onChange={e => setFocus(e.target.value)} data-testid="traffic-iface">
            <option value="__all__">All interfaces (aggregate)</option>
            {state.items.map(i => <option key={i.name} value={i.name}>{`${i.name} · ${i.running === "true" ? "running" : "down"}`}</option>)}
          </select>
        </span>
        <span className="muted">{state.interval ? `${state.interval}s window · live 5s` : "warming up…"}</span>
        <button className="button secondary compact" onClick={() => setPaused(p => !p)} data-testid="traffic-pause">{paused ? <><Play size={13} />Resume</> : <><Pause size={13} />Pause</>}</button>
      </div>
    </div>
    <div className="chart chart-sm" data-testid="traffic-chart">
      <ResponsiveContainer width="100%" height="100%"><AreaChart data={chartData}>
        <defs><linearGradient id="rxg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#38bdf8" stopOpacity=".3" /><stop offset="100%" stopColor="#38bdf8" stopOpacity="0" /></linearGradient>
          <linearGradient id="txg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f59e0b" stopOpacity=".25" /><stop offset="100%" stopColor="#f59e0b" stopOpacity="0" /></linearGradient></defs>
        <XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} width={34} unit="M" />
        <Tooltip contentStyle={{ background: "#111827", border: "1px solid #26344b", borderRadius: 6, color: "#f8fafc", fontSize: 12 }} />
        <Area type="monotone" dataKey="inbound" name="rx Mbps" stroke="#38bdf8" fill="url(#rxg)" strokeWidth={2} />
        <Area type="monotone" dataKey="outbound" name="tx Mbps" stroke="#f59e0b" fill="url(#txg)" strokeWidth={2} />
      </AreaChart></ResponsiveContainer>
    </div>
    <div className="res-table" data-testid="traffic-table"><table><thead><tr><th>INTERFACE</th><th>TYPE</th><th>STATE</th><th>RX</th><th>TX</th><th>LOAD</th></tr></thead><tbody>
      {state.items.length === 0 && <tr><td colSpan={6} className="res-empty">No physical interfaces reported.</td></tr>}
      {state.items.map((i, idx) => <tr key={i.name} onClick={() => setFocus(f => (f === i.name ? "__all__" : i.name))} className={`${i.running === "true" ? "" : "row-disabled"} ${focus === i.name ? "row-focus" : ""}`} data-testid={`traffic-row-${idx}`}>
        <td><b>{i.name}</b>{i.comment ? <span className="muted"> · {i.comment}</span> : null}</td>
        <td className="muted">{i.type}</td>
        <td>{i.running === "true" ? <span className="tg-pill on">running</span> : <span className="tg-pill off">down</span>}</td>
        <td className="mono" data-testid={`traffic-rx-${i.name}`}>{i.ready ? fmt(i.rx_mbps) : "—"}</td>
        <td className="mono" data-testid={`traffic-tx-${i.name}`}>{i.ready ? fmt(i.tx_mbps) : "—"}</td>
        <td><div className="bar-value"><i><b style={{ width: `${Math.min(100, (i.rx_mbps + i.tx_mbps) * 100 / max)}%` }} /></i></div></td>
      </tr>)}
    </tbody></table></div>
    <p className="backup-note">Bandwidth is calculated from live RouterOS interface byte counters sampled every 5 seconds through the persistent API session. Pick an interface above (or click a row) to chart it on its own; the 30-day history lives under Interface Graphs (SNMP).</p>
    <PermissionPopup error={permErr} onClose={() => setPermErr(null)} onGoSettings={onGoSettings} />
  </>;
}

export function AggregateTrafficChart({ data }) {
  return <div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data}>
    <defs><linearGradient id="inbound" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#38bdf8" stopOpacity=".30" /><stop offset="100%" stopColor="#38bdf8" stopOpacity="0" /></linearGradient>
      <linearGradient id="outbound" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a78bfa" stopOpacity=".2" /><stop offset="100%" stopColor="#a78bfa" stopOpacity="0" /></linearGradient></defs>
    <XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
    <YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} width={34} unit="M" />
    <Tooltip contentStyle={{ background: "#111827", border: "1px solid #26344b", borderRadius: 6, color: "#f8fafc" }} />
    <Area type="monotone" dataKey="inbound" name="rx Mbps" stroke="#38bdf8" fill="url(#inbound)" strokeWidth={2} />
    <Area type="monotone" dataKey="outbound" name="tx Mbps" stroke="#a78bfa" fill="url(#outbound)" strokeWidth={2} />
  </AreaChart></ResponsiveContainer></div>;
}

export function TrafficEmpty({ live, routers }) {
  if (live) return null;
  return <div className="drawer-message" data-testid="traffic-warming"><Activity size={16} />{routers ? "Sampling RouterOS interface counters — the first live point appears after the next poll (20s)." : "No reachable router in this workspace to sample bandwidth from."}</div>;
}
