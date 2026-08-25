import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Activity, AlertTriangle, Bell, ChevronDown, ChevronRight, CircleGauge,
  Cpu, Database, Ellipsis, LayoutDashboard, Menu, Network, Plus,
  RefreshCw, Router, Search, Settings2, ShieldCheck, SlidersHorizontal,
  Terminal, Users, Wifi, X
} from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import "@/App.css";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const fallback = {
  routers: [
    { id: "r-01", name: "HQ Core Router", host: "10.10.0.1", group: "Head Office", status: "online", cpu: 28, memory: 42, uptime: "21d 04h 18m", interfaces: 14, traffic: "842 Mbps", version: "7.14.3", color: "cyan" },
    { id: "r-02", name: "East Branch", host: "10.21.0.1", group: "Region East", status: "online", cpu: 64, memory: 71, uptime: "8d 12h 09m", interfaces: 8, traffic: "318 Mbps", version: "7.13.5", color: "green" },
    { id: "r-03", name: "Warehouse Gateway", host: "10.30.0.1", group: "Operations", status: "warning", cpu: 83, memory: 77, uptime: "3d 07h 44m", interfaces: 11, traffic: "1.24 Gbps", version: "7.12.1", color: "amber" },
    { id: "r-04", name: "Partner PT ABC", host: "172.16.20.1", group: "Partner · PT ABC", status: "offline", cpu: 0, memory: 0, uptime: "—", interfaces: 6, traffic: "—", version: "7.11.2", color: "red" },
  ],
  groups: ["All routers", "Head Office", "Region East", "Operations", "Partner · PT ABC"],
  traffic: [0, 28, 21, 44, 36, 58, 45, 66, 52, 73, 62, 81].map((v, i) => ({ time: `${String(i + 8).padStart(2, "0")}:00`, inbound: v + 12, outbound: Math.max(8, v - 3) })),
};

const nav = [
  { label: "Overview", icon: LayoutDashboard }, { label: "Routers", icon: Router },
  { label: "Groups & Tenants", icon: Users }, { label: "Alarms", icon: Bell, count: 3 },
  { label: "Audit log", icon: ShieldCheck },
];

function Status({ value }) {
  const map = { online: ["Online", "status-online"], warning: ["Warning", "status-warning"], offline: ["Offline", "status-offline"] };
  const [label, cls] = map[value] || map.offline;
  return <span data-testid={`router-status-${value}`} className={`status ${cls}`}><i />{label}</span>;
}

function Metric({ icon: Icon, label, value, detail, tone = "cyan" }) {
  return <div className="metric" data-testid={`metric-${label.toLowerCase().replaceAll(" ", "-")}`}>
    <div className={`metric-icon ${tone}`}><Icon size={17} /></div><div><p>{label}</p><strong>{value}</strong><small>{detail}</small></div>
  </div>;
}

function App() {
  const [data, setData] = useState(fallback); const [active, setActive] = useState("Overview");
  const [group, setGroup] = useState("All routers"); const [query, setQuery] = useState("");
  const [drawer, setDrawer] = useState(false); const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState(null); const [drawerTab, setDrawerTab] = useState("Interfaces");
  useEffect(() => { axios.get(`${API}/monitoring/overview`).then(r => r.data && setData(r.data)).catch(() => {}); }, []);
  const routers = useMemo(() => data.routers.filter(r => (group === "All routers" || r.group === group) && `${r.name} ${r.host}`.toLowerCase().includes(query.toLowerCase())), [data, group, query]);
  const online = data.routers.filter(r => r.status === "online").length;
  const show = (label) => { setActive(label); setNotice(`${label} view selected`); setTimeout(() => setNotice(""), 1800); };
  return <div className="app-shell">
    <aside className={`sidebar ${drawer ? "open" : ""}`} data-testid="main-sidebar">
      <div className="brand"><div className="brand-mark"><Network size={20} /></div><div><b>NETPULSE</b><span>mikrotik control plane</span></div><button className="icon-btn mobile-close" onClick={() => setDrawer(false)} data-testid="close-sidebar-button"><X size={17} /></button></div>
      <div className="workspace"><span>WORKSPACE</span><button data-testid="workspace-selector">Central Operations <ChevronDown size={14} /></button></div>
      <nav>{nav.map(({ label, icon: Icon, count }) => <button key={label} onClick={() => show(label)} className={active === label ? "active" : ""} data-testid={`nav-${label.toLowerCase().replaceAll(" ", "-")}`}><Icon size={17} />{label}{count && <em>{count}</em>}</button>)}</nav>
      <div className="side-section"><span>DEVICE GROUPS</span>{data.groups.slice(1).map(g => <button key={g} onClick={() => { setGroup(g); show("Routers"); }} data-testid={`group-${g.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}`}><i className="group-dot" />{g}<small>{data.routers.filter(r => r.group === g).length}</small></button>)}</div>
      <div className="sidebar-bottom"><button className={active === "Settings" ? "active" : ""} onClick={() => show("Settings")} data-testid="nav-settings"><Settings2 size={17} />Settings</button><div className="user-chip"><div className="avatar">SA</div><div><b>Super Admin</b><span>Full access</span></div><Ellipsis size={16} /></div></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><button className="icon-btn menu-btn" onClick={() => setDrawer(true)} data-testid="open-sidebar-button"><Menu size={19} /></button><div className="crumb"><span>Workspace</span><ChevronRight size={14} /><b>{active}</b></div><div className="top-actions"><div className="connection"><i />Live polling <span>30s</span></div><button className="icon-btn" onClick={() => setNotice("All systems refreshed")} data-testid="refresh-monitoring-button"><RefreshCw size={17} /></button><button className="notification" onClick={() => show("Alarms")} data-testid="open-notifications-button"><Bell size={17} /><i /></button><div className="top-avatar">SA</div></div></header>
      <section className="content">
        <div className="page-heading"><div><p className="eyebrow">CENTRAL MONITORING / {new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase()}</p><h1>{active === "Overview" ? "Network overview" : active}</h1><p className="subheading">A real-time view of your MikroTik infrastructure and active signals.</p></div><div className="heading-actions"><button className="button secondary" onClick={() => setNotice("Widget layout saved")} data-testid="customize-dashboard-button"><SlidersHorizontal size={16} />Customize</button><button className="button primary" onClick={() => setNotice("Router onboarding opened")} data-testid="add-router-button"><Plus size={16} />Add router</button></div></div>
        {notice && <div className="toast" data-testid="notification-toast"><Activity size={16} />{notice}</div>}
        <div className="metrics-grid"><Metric icon={Router} label="Total routers" value={data.routers.length} detail={`${online} online · 1 warning`} /><Metric icon={CircleGauge} label="Network health" value="94.2%" detail="↑ 2.8% from yesterday" tone="green" /><Metric icon={Activity} label="Aggregate traffic" value="2.40 Gbps" detail="Inbound across 3 routers" tone="violet" /><Metric icon={AlertTriangle} label="Active alarms" value="03" detail="2 high · 1 medium" tone="amber" /></div>
        <div className="main-grid"><section className="panel traffic-panel"><div className="panel-head"><div><p className="eyebrow">BANDWIDTH TELEMETRY</p><h2>Aggregate traffic</h2></div><div className="periods"><button className="selected" data-testid="traffic-period-24h">24H</button><button data-testid="traffic-period-7d">7D</button><button data-testid="traffic-period-30d">30D</button></div></div><div className="chart-legend"><span><i className="legend-in" />Inbound <b>2.40 Gbps</b></span><span><i className="legend-out" />Outbound <b>1.18 Gbps</b></span></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data.traffic}><defs><linearGradient id="inbound" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#38bdf8" stopOpacity=".30" /><stop offset="100%" stopColor="#38bdf8" stopOpacity="0" /></linearGradient><linearGradient id="outbound" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a78bfa" stopOpacity=".2" /><stop offset="100%" stopColor="#a78bfa" stopOpacity="0" /></linearGradient></defs><XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} /><YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} width={32} /><Tooltip contentStyle={{ background: "#111827", border: "1px solid #26344b", borderRadius: 6, color: "#f8fafc" }} /><Area type="monotone" dataKey="inbound" stroke="#38bdf8" fill="url(#inbound)" strokeWidth={2} /><Area type="monotone" dataKey="outbound" stroke="#a78bfa" fill="url(#outbound)" strokeWidth={2} /></AreaChart></ResponsiveContainer></div></section>
          <section className="panel alarm-panel"><div className="panel-head"><div><p className="eyebrow">SIGNAL CENTER</p><h2>Active alarms</h2></div><button className="text-btn" onClick={() => show("Alarms")} data-testid="view-all-alarms-button">View all <ChevronRight size={14} /></button></div><div className="alarm-list"><div className="alarm-item danger"><div className="alarm-symbol"><AlertTriangle size={16} /></div><div><b>CPU threshold exceeded</b><span>Warehouse Gateway · 83% CPU</span><small>2 minutes ago</small></div><button className="alarm-menu" data-testid="alarm-menu-cpu"><Ellipsis size={16} /></button></div><div className="alarm-item warning"><div className="alarm-symbol"><Wifi size={16} /></div><div><b>Interface status changed</b><span>East Branch · ether4 is down</span><small>18 minutes ago</small></div><button className="alarm-menu" data-testid="alarm-menu-interface"><Ellipsis size={16} /></button></div><div className="alarm-item info"><div className="alarm-symbol"><Bell size={16} /></div><div><b>Telegram notification sent</b><span>Partner · PT ABC · resolved</span><small>42 minutes ago</small></div><button className="alarm-menu" data-testid="alarm-menu-telegram"><Ellipsis size={16} /></button></div></div></section></div>
        <section className="panel routers-panel"><div className="panel-head table-head"><div><p className="eyebrow">INVENTORY / {data.routers.length} DEVICES</p><h2>Router fleet</h2></div><div className="table-tools"><div className="search"><Search size={15} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Filter routers..." data-testid="router-search-input" /></div><select value={group} onChange={e => setGroup(e.target.value)} data-testid="router-group-filter">{data.groups.map(g => <option key={g}>{g}</option>)}</select><button className="icon-btn" data-testid="router-table-settings"><SlidersHorizontal size={16} /></button></div></div><div className="table-wrap"><table><thead><tr><th>ROUTER</th><th>GROUP</th><th>STATUS</th><th>CPU</th><th>MEMORY</th><th>TRAFFIC</th><th>UPTIME</th><th></th></tr></thead><tbody>{routers.map(r => <tr key={r.id} onClick={() => setSelected(r)} data-testid={`router-row-${r.id}`}><td><div className="router-name"><div className={`router-icon ${r.color}`}><Router size={15} /></div><div><b>{r.name}</b><span>{r.host} · ROS {r.version}</span></div></div></td><td><span className="group-label">{r.group}</span></td><td><Status value={r.status} /></td><td><div className="bar-value"><span>{r.cpu}%</span><i><b style={{ width: `${r.cpu}%` }} /></i></div></td><td><div className="bar-value"><span>{r.memory ? `${r.memory}%` : "—"}</span><i><b className={r.memory > 70 ? "warn" : ""} style={{ width: `${r.memory}%` }} /></i></div></td><td className="mono">{r.traffic}</td><td className="muted">{r.uptime}</td><td><button className="row-arrow" onClick={(e) => { e.stopPropagation(); setSelected(r); }} data-testid={`router-details-${r.id}`}><ChevronRight size={16} /></button></td></tr>)}</tbody></table>{routers.length === 0 && <div className="empty-state" data-testid="empty-router-state">No routers match this filter.</div>}</div></section>
        <div className="footer-note"><span><Database size={14} />Native RouterOS graph data · lightweight cache</span><span>Last sync: just now · <b>All systems operational</b></span></div>
      </section>
    </main>
    {selected && <div className="drawer-backdrop" onClick={() => setSelected(null)}><aside className="router-drawer" onClick={e => e.stopPropagation()} data-testid="router-details-drawer"><div className="drawer-head"><div><p className="eyebrow">ROUTER DETAIL</p><h2>{selected.name}</h2><span className="muted mono">{selected.host}</span></div><button className="icon-btn" onClick={() => setSelected(null)} data-testid="close-router-details"><X size={18} /></button></div><Status value={selected.status} /><div className="drawer-stats"><div><span>CPU</span><b>{selected.cpu}%</b></div><div><span>Memory</span><b>{selected.memory}%</b></div><div><span>Uptime</span><b>{selected.uptime}</b></div></div><div className="tabs"><button className={drawerTab === "Interfaces" ? "active" : ""} onClick={() => setDrawerTab("Interfaces")} data-testid="router-tab-interfaces">Interfaces</button><button className={drawerTab === "Resources" ? "active" : ""} onClick={() => setDrawerTab("Resources")} data-testid="router-tab-resources">Resources</button><button className={drawerTab === "Logs" ? "active" : ""} onClick={() => setDrawerTab("Logs")} data-testid="router-tab-logs">Logs</button></div>{drawerTab === "Interfaces" && <div data-testid="router-interfaces-panel"><div className="interface-row"><span><Wifi size={15} />ether1 · uplink</span><Status value="online" /><b>842 Mbps</b></div><div className="interface-row"><span><Wifi size={15} />ether4 · office</span><Status value={selected.status === "warning" ? "warning" : "online"} /><b>318 Mbps</b></div></div>}{drawerTab === "Resources" && <div className="drawer-message" data-testid="router-resources-panel"><Cpu size={17} />Resource snapshot · CPU {selected.cpu}% · memory {selected.memory}%</div>}{drawerTab === "Logs" && <div className="drawer-message" data-testid="router-logs-panel"><Terminal size={17} />No new critical events · stream connected</div>}<button className="button secondary full" onClick={() => setNotice("Connection test started")} data-testid="test-router-connection"><RefreshCw size={15} />Test connection</button><button className="button primary full" onClick={() => setNotice("Configuration console opened")} data-testid="open-router-console"><Terminal size={15} />Open WebFig console</button></aside></div>}
  </div>;
}
export default App;