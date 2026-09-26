import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, Download, Gauge, Image, Loader2 } from "lucide-react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorText } from "@/lib/api";

const RANGES = [{ label: "Live", hours: 0 }, { label: "1 day", hours: 24 }, { label: "2 days", hours: 48 }, { label: "1 week", hours: 168 }, { label: "Last month", hours: 720 }];
const LIVE_POINTS = 60;
const stamp = (iso, hours) => new Date(iso).toLocaleString([], hours <= 24 ? { hour: "2-digit", minute: "2-digit" } : { day: "2-digit", month: "short", hour: "2-digit" });

const download = (href, name) => { const a = document.createElement("a"); a.href = href; a.download = name; a.click(); };

/** PNG export: serialise the chart SVG and paint it on a canvas (no extra dependency). */
const svgToPng = (container, name) => {
  const svg = container?.querySelector("svg");
  if (!svg) return false;
  const box = svg.getBoundingClientRect();
  const clone = svg.cloneNode(true);
  clone.setAttribute("width", box.width); clone.setAttribute("height", box.height);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const blob = new Blob([`<svg xmlns="http://www.w3.org/2000/svg" width="${box.width}" height="${box.height}"><rect width="100%" height="100%" fill="#0b1220"/>${clone.innerHTML}</svg>`], { type: "image/svg+xml" });
  const url = URL.createObjectURL(blob);
  const img = new window.Image();
  img.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = box.width * 2; canvas.height = box.height * 2;
    const ctx = canvas.getContext("2d");
    ctx.scale(2, 2); ctx.drawImage(img, 0, 0);
    download(canvas.toDataURL("image/png"), name);
    URL.revokeObjectURL(url);
  };
  img.src = url;
  return true;
};

export function InterfaceGraphs({ deviceId, deviceType = "mikrotik", onNotice }) {
  const [ifaces, setIfaces] = useState([]);
  const [iface, setIface] = useState("");
  const [hours, setHours] = useState(24);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [comments, setComments] = useState({});
  const [live, setLive] = useState([]);
  const liveMode = hours === 0;
  const chartRef = useRef(null);

  useEffect(() => {
    if (deviceType !== "mikrotik") return;
    api.get(`/routers/${deviceId}/resources/interfaces`)
      .then(r => setComments(Object.fromEntries((r.data.items || []).filter(i => i.comment).map(i => [i.name, i.comment]))))
      .catch(() => setComments({}));
  }, [deviceId, deviceType]);

  useEffect(() => {
    api.get(`/devices/${deviceId}/snmp`).then(r => {
      const rows = r.data.snmp?.interfaces || [];
      const mode = r.data.config?.record_mode || "all";
      const recorded = mode === "all" ? rows.map(i => i.name) : (r.data.config?.recorded || []);
      setIfaces(rows.filter(i => recorded.includes(i.name)));
      setIface(prev => prev || recorded[0] || "");
    }).catch(e => onNotice?.(errorText(e, "Could not read the interface list")));
  }, [deviceId, onNotice]);

  const load = useCallback(async () => {
    if (!iface || hours === 0) { setLoading(false); return; }
    setLoading(true);
    try { const r = await api.get(`/devices/${deviceId}/interface-history`, { params: { iface, hours } }); setData(r.data); }
    catch (e) { onNotice?.(errorText(e, "Could not read the history")); }
    finally { setLoading(false); }
  }, [deviceId, iface, hours, onNotice]);
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, [load]);

  // Live view: RouterOS API counters for MikroTik (5s), SNMP sweeps for every other vendor (15s).
  useEffect(() => {
    if (!liveMode || !iface) return;
    let alive = true;
    setLive([]);
    const tick = async () => {
      try {
        const row = deviceType === "mikrotik"
          ? (await api.get(`/routers/${deviceId}/traffic`)).data.items?.find(i => i.name === iface)
          : (await api.post(`/devices/${deviceId}/snmp/scan`)).data.snmp?.interfaces?.find(i => i.name === iface);
        if (!alive || !row) return;
        setLive(s => [...s.slice(-LIVE_POINTS), { time: new Date().toLocaleTimeString(), rx_mbps: row.rx_mbps || 0, tx_mbps: row.tx_mbps || 0 }]);
      } catch (e) { if (alive) onNotice?.(errorText(e, "Live sampling failed")); }
    };
    tick();
    const t = setInterval(tick, deviceType === "mikrotik" ? 5000 : 15000);
    return () => { alive = false; clearInterval(t); };
  }, [liveMode, iface, deviceId, deviceType, onNotice]);

  const exportCsv = () => {
    if (!traffic.length) return onNotice?.("Nothing to export yet");
    const rows = [["timestamp", "interface", "rx_mbps", "tx_mbps"], ...traffic.map(p => [p.ts || p.time, iface, p.rx_mbps, p.tx_mbps])];
    const csv = rows.map(r => r.join(",")).join("\n");
    download(`data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`, `${iface}-${liveMode ? "live" : `${hours}h`}.csv`);
    onNotice?.(`Exported ${traffic.length} rows for ${iface}`);
  };
  const exportPng = () => {
    if (!svgToPng(chartRef.current, `${iface}-${liveMode ? "live" : `${hours}h`}.png`)) onNotice?.("Chart is not ready yet");
  };

  const labelled = ifaces.map(i => ({ ...i, alias: i.alias || comments[i.name] || "" }));
  const traffic = liveMode ? live : (data?.traffic || []).map(p => ({ ...p, time: stamp(p.ts, hours) }));
  const ping = liveMode ? [] : (data?.ping || []).map(p => ({ ...p, time: stamp(p.ts, hours) }));
  const stats = traffic.length
    ? { avg: { rx: +(traffic.reduce((a, p) => a + p.rx_mbps, 0) / traffic.length).toFixed(3), tx: +(traffic.reduce((a, p) => a + p.tx_mbps, 0) / traffic.length).toFixed(3) },
        peak: { rx: Math.max(...traffic.map(p => p.rx_mbps)), tx: Math.max(...traffic.map(p => p.tx_mbps)) } }
    : { avg: { rx: 0, tx: 0 }, peak: { rx: 0, tx: 0 } };

  return <div data-testid="interface-graphs">
    <div className="res-toolbar">
      <div className="res-tools">
        <span className="graph-picker">Interface
        <select value={iface} onChange={e => setIface(e.target.value)} data-testid="graph-iface">
          {ifaces.length === 0 && <option value="">no recorded interface</option>}
          {labelled.map(i => <option key={i.name} value={i.name}>{`${i.name}${i.alias ? ` (${i.alias})` : ""} · ${i.status}`}</option>)}
        </select></span>
        {RANGES.map(r => <button key={r.label} className={`button compact ${hours === r.hours ? "primary" : "secondary"}`} onClick={() => setHours(r.hours)} data-testid={`graph-range-${r.label.replace(/ /g, "-").toLowerCase()}`}>{r.label}</button>)}
      </div>
      <div className="res-tools">
        <button className="button secondary compact" onClick={exportCsv} data-testid="graph-export-csv"><Download size={13} />CSV</button>
        <button className="button secondary compact" onClick={exportPng} data-testid="graph-export-png"><Image size={13} />PNG</button>
      </div>
      <span className="muted" data-testid="graph-meta">{liveMode
        ? `live · ${deviceType === "mikrotik" ? "RouterOS API every 5s" : "SNMP sweep every 15s"} · ${live.length} points`
        : data ? `${data.samples} samples · ${Math.round(data.bucket_seconds / 60)} min buckets · kept ${data.retention_days} days` : "—"}</span>
    </div>

    {loading && !liveMode ? <div className="res-loading"><Loader2 size={14} className="spin" />Reading SNMP history…</div>
      : traffic.length === 0 ? <div className="drawer-message" data-testid="graph-empty"><Activity size={16} />{liveMode ? "Waiting for the first live sample…" : "No history yet for this interface. SNMP samples land every minute — pick the interface under SNMP → recorded interfaces and come back shortly."}</div>
        : <>
          <div className="snmp-stats">
            <div className="snmp-stat"><span>Average in / out</span><b data-testid="graph-average">{stats.avg.rx} / {stats.avg.tx}</b><small>Mbps over the window</small></div>
            <div className="snmp-stat"><span>Peak in / out</span><b data-testid="graph-peak">{stats.peak.rx} / {stats.peak.tx}</b><small>Mbps</small></div>
            <div className="snmp-stat"><span>Ping average</span><b>{ping.length ? `${(ping.reduce((a, p) => a + p.ping_ms, 0) / ping.length).toFixed(1)} ms` : liveMode ? "live view" : "—"}</b><small>ICMP every 60s</small></div>
            <div className="snmp-stat"><span>Packet loss</span><b>{ping.length ? `${(ping.reduce((a, p) => a + p.loss, 0) / ping.length).toFixed(1)}%` : "—"}</b><small>window average</small></div>
          </div>
          <p className="eyebrow chart-label">TRAFFIC · {iface}{labelled.find(i => i.name === iface)?.alias ? ` · ${labelled.find(i => i.name === iface).alias}` : ""}</p>
          <div className="chart" ref={chartRef} data-testid="graph-traffic">
            <ResponsiveContainer width="100%" height="100%"><AreaChart data={traffic}>
              <defs><linearGradient id="hrx" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#38bdf8" stopOpacity=".32" /><stop offset="100%" stopColor="#38bdf8" stopOpacity="0" /></linearGradient>
                <linearGradient id="htx" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f59e0b" stopOpacity=".25" /><stop offset="100%" stopColor="#f59e0b" stopOpacity="0" /></linearGradient></defs>
              <CartesianGrid stroke="#1b2941" vertical={false} />
              <XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={40} />
              <YAxis tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} width={38} unit="M" />
              <Tooltip contentStyle={{ background: "#111827", border: "1px solid #26344b", borderRadius: 6, color: "#f8fafc", fontSize: 12 }} />
              <Area type="monotone" dataKey="rx_mbps" name="rx Mbps" stroke="#38bdf8" fill="url(#hrx)" strokeWidth={2} />
              <Area type="monotone" dataKey="tx_mbps" name="tx Mbps" stroke="#f59e0b" fill="url(#htx)" strokeWidth={2} />
            </AreaChart></ResponsiveContainer>
          </div>
          {ping.length > 0 && <><p className="eyebrow chart-label">LATENCY · ICMP</p>
          <div className="chart chart-sm" data-testid="graph-ping">
            <ResponsiveContainer width="100%" height="100%"><LineChart data={ping}>
              <CartesianGrid stroke="#1b2941" vertical={false} />
              <XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={40} />
              <YAxis tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} width={38} unit="ms" />
              <Tooltip contentStyle={{ background: "#111827", border: "1px solid #26344b", borderRadius: 6, color: "#f8fafc", fontSize: 12 }} />
              <Line type="monotone" dataKey="ping_ms" name="rtt ms" stroke="#37c58c" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="loss" name="loss %" stroke="#f87171" strokeWidth={1.5} dot={false} />
            </LineChart></ResponsiveContainer>
          </div></>}
        </>}
    <p className="backup-note"><Gauge size={13} /> Live view reads the device directly; 1 day to last month come from SNMP counters sampled every minute and ICMP pings every 60 seconds. History stops at 30 days because older samples are deleted automatically.</p>
  </div>;
}
