import { useEffect, useState } from "react";
import { Activity, CircleGauge, Loader2, Router } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";

export const CARD_HOURS = [{ label: "Live", hours: 0 }, { label: "1 day", hours: 24 }, { label: "2 days", hours: 48 }, { label: "1 week", hours: 168 }, { label: "Last month", hours: 720 }];
export const CARD_TYPES = [
  { id: "iface-traffic", label: "SNMP interface traffic (device + interface + timeframe)" },
  { id: "device-count", label: "Device counters (total / online / offline)" },
  { id: "device-ping", label: "Single device ping & CPU tile" },
];
const rangeLabel = (h) => CARD_HOURS.find(r => r.hours === h)?.label || `${h}h`;

function IfaceTrafficCard({ card, devices }) {
  const [series, setSeries] = useState(null);
  const device = devices.find(d => d.id === card.device_id);
  const live = card.hours === 0;

  useEffect(() => {
    let alive = true;
    const historic = async () => {
      try {
        const r = await api.get(`/devices/${card.device_id}/interface-history`, { params: { iface: card.iface, hours: card.hours } });
        if (alive) setSeries(r.data.traffic.map(p => ({ time: new Date(p.ts).toLocaleString([], card.hours <= 48 ? { hour: "2-digit", minute: "2-digit" } : { day: "2-digit", month: "short" }), rx_mbps: p.rx_mbps, tx_mbps: p.tx_mbps })));
      } catch { if (alive) setSeries([]); }
    };
    const sample = async () => {
      try {
        const vendor = device?.device_type || "mikrotik";
        const row = vendor === "mikrotik"
          ? (await api.get(`/routers/${card.device_id}/traffic`)).data.items?.find(i => i.name === card.iface)
          : (await api.post(`/devices/${card.device_id}/snmp/scan`)).data.snmp?.interfaces?.find(i => i.name === card.iface);
        if (alive && row) setSeries(s => [...(s || []).slice(-29), { time: new Date().toLocaleTimeString(), rx_mbps: row.rx_mbps || 0, tx_mbps: row.tx_mbps || 0 }]);
      } catch { /* keep the previous points */ }
    };
    const run = live ? sample : historic;
    run();
    const t = setInterval(run, live ? 10000 : 120000);
    return () => { alive = false; clearInterval(t); };
  }, [card.device_id, card.iface, card.hours, live, device]);

  const last = series?.[series.length - 1];
  return <section className="panel traffic-panel" data-testid={`card-${card.id}`}>
    <div className="panel-head"><div>
      <p className="eyebrow">{(device?.name || card.device_id).toUpperCase()} · {card.iface} · {rangeLabel(card.hours).toUpperCase()}</p>
      <h2>{card.title || `${card.iface} traffic`}</h2>
    </div>
      <span className="muted" data-testid={`card-${card.id}-value`}>{last ? `↓ ${last.rx_mbps} / ↑ ${last.tx_mbps} Mbps` : "—"}</span>
    </div>
    {series === null ? <div className="res-loading"><Loader2 size={14} className="spin" />Loading…</div>
      : series.length === 0 ? <div className="drawer-message"><Activity size={16} />No samples yet for {card.iface}. Make sure SNMP recording includes this interface.</div>
        : <div className="chart chart-sm"><ResponsiveContainer width="100%" height="100%"><AreaChart data={series}>
          <defs><linearGradient id={`cg-${card.id}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#38bdf8" stopOpacity=".3" /><stop offset="100%" stopColor="#38bdf8" stopOpacity="0" /></linearGradient>
            <linearGradient id={`cgt-${card.id}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f59e0b" stopOpacity=".24" /><stop offset="100%" stopColor="#f59e0b" stopOpacity="0" /></linearGradient></defs>
          <XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={40} />
          <YAxis tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} width={34} unit="M" />
          <Tooltip contentStyle={{ background: "#111827", border: "1px solid #26344b", borderRadius: 6, color: "#f8fafc", fontSize: 12 }} />
          <Area type="monotone" dataKey="rx_mbps" name="rx Mbps" stroke="#38bdf8" fill={`url(#cg-${card.id})`} strokeWidth={2} />
          <Area type="monotone" dataKey="tx_mbps" name="tx Mbps" stroke="#f59e0b" fill={`url(#cgt-${card.id})`} strokeWidth={2} />
        </AreaChart></ResponsiveContainer></div>}
  </section>;
}

function CountCard({ card, devices }) {
  const total = devices.length;
  const online = devices.filter(d => d.status === "online").length;
  return <section className="panel" data-testid={`card-${card.id}`}>
    <div className="panel-head"><div><p className="eyebrow">FLEET COUNTERS</p><h2>{card.title || "Devices"}</h2></div></div>
    <div className="snmp-stats" style={{ padding: "0 18px 16px" }}>
      <div className="snmp-stat"><span>Total</span><b data-testid={`card-${card.id}-total`}>{total}</b><small>in this board scope</small></div>
      <div className="snmp-stat"><span>Online</span><b data-testid={`card-${card.id}-online`}>{online}</b><small>reachable now</small></div>
      <div className="snmp-stat"><span>Offline</span><b data-testid={`card-${card.id}-offline`}>{total - online}</b><small>need attention</small></div>
    </div>
  </section>;
}

function PingCard({ card, devices }) {
  const device = devices.find(d => d.id === card.device_id);
  return <section className="panel" data-testid={`card-${card.id}`}>
    <div className="panel-head"><div><p className="eyebrow">{(device?.name || card.device_id).toUpperCase()}</p><h2>{card.title || "Device health"}</h2></div></div>
    <div className="snmp-stats" style={{ padding: "0 18px 16px" }}>
      <div className="snmp-stat"><span>Status</span><b>{device?.status || "unknown"}</b><small>{device?.device_type || "mikrotik"}</small></div>
      <div className="snmp-stat"><span>Ping</span><b data-testid={`card-${card.id}-ping`}>{device?.ping_ms ? `${device.ping_ms} ms` : "—"}</b><small>{device?.ping_loss ?? 0}% loss</small></div>
      <div className="snmp-stat"><span>CPU</span><b>{device?.cpu ?? 0}%</b><small><CircleGauge size={11} /> last poll</small></div>
      <div className="snmp-stat"><span>Uptime</span><b>{device?.uptime || "—"}</b><small><Router size={11} /> {device?.version || ""}</small></div>
    </div>
  </section>;
}

export function BoardCards({ cards, devices, allDevices }) {
  if (!cards?.length) return null;
  const named = allDevices?.length ? allDevices : devices;  // counters follow the board scope, labels use the full inventory
  return <>{cards.map(card => card.type === "iface-traffic" ? <IfaceTrafficCard key={card.id} card={card} devices={named} />
    : card.type === "device-count" ? <CountCard key={card.id} card={card} devices={devices} />
      : <PingCard key={card.id} card={card} devices={named} />)}</>;
}
