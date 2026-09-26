import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Activity, AlertTriangle, Bell, Check, ChevronDown, ChevronLeft, ChevronRight, CircleGauge,
  Clock, Cpu, Database, Ellipsis, ExternalLink, Eye, EyeOff, KeyRound, LayoutDashboard,
  Loader2, Menu, Network, Plus, Power, RefreshCw, Router, Save, Search, Send, Settings2,
  ShieldCheck, SlidersHorizontal, Terminal, Trash2, Users, Wifi, X
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

const DRAWER_TABS = [
  { key: "Interfaces", icon: Wifi, testid: "router-tab-interfaces", short: "Interfaces" },
  { key: "Resources", icon: Cpu, testid: "router-tab-resources", short: "Resources" },
  { key: "Logs", icon: Terminal, testid: "router-tab-logs", short: "Logs" },
  { key: "PPP Profiles", icon: Users, testid: "router-tab-ppp-profiles", short: "Profiles" },
  { key: "PPP Secrets", icon: KeyRound, testid: "router-tab-ppp-secrets", short: "Secrets" },
  { key: "System Time", icon: Clock, testid: "router-tab-system-time", short: "Clock" },
];

const RESOURCE_COLUMNS = {
  Logs: ["time", "topics", "message"],
  Interfaces: ["name", "type", "mac-address", "running", "disabled", "comment"],
  Addresses: ["address", "network", "interface", "disabled", "comment"],
  ARP: ["address", "mac-address", "interface", "dynamic", "complete"],
  "DHCP Server": ["name", "interface", "address-pool", "lease-time", "disabled"],
  "DHCP Leases": ["address", "mac-address", "host-name", "status", "expires-after"],
  Firewall: ["chain", "action", "src-address", "dst-address", "protocol", "disabled", "comment"],
  Routes: ["dst-address", "gateway", "distance", "active", "static", "disabled"],
  "PPP Profiles": ["name", "local-address", "remote-address", "rate-limit", "dns-server"],
  "PPP Secrets": ["name", "service", "profile", "password", "remote-address", "disabled"],
  Queues: ["name", "target", "max-limit", "burst-limit", "disabled"],
  Wireless: ["interface", "mac-address", "signal-strength", "tx-rate", "rx-rate", "uptime"],
  "System Time": ["time", "date", "time-zone-name", "gmt-offset", "dst-active"],
  "System Resource": ["uptime", "version", "board-name", "cpu-load", "free-memory", "total-memory"],
  "System Identity": ["name"],
  "System Health": ["name", "value", "type"],
};

const RESOURCE_KEY = {
  Logs: "logs",
  Interfaces: "interfaces",
  Addresses: "addresses",
  ARP: "arp",
  "DHCP Server": "dhcp-server",
  "DHCP Leases": "dhcp-leases",
  Firewall: "firewall",
  Routes: "routes",
  "PPP Profiles": "ppp-profiles",
  "PPP Secrets": "ppp-secrets",
  Queues: "queues",
  Wireless: "wireless-registration",
  "System Time": "system-clock",
  "System Resource": "system-resource",
  "System Identity": "system-identity",
  "System Health": "system-health",
};

const WINBOX_MENU = [
  { section: "Interfaces", items: ["Interfaces", "Wireless"] },
  { section: "IP", items: ["Addresses", "ARP", "DHCP Server", "DHCP Leases", "Firewall", "Routes"] },
  { section: "PPP", items: ["PPP Profiles", "PPP Secrets"] },
  { section: "Queues", items: ["Queues"] },
  { section: "System", items: ["System Identity", "System Resource", "System Time", "System Health"] },
  { section: "Log", items: ["Logs"] },
];

function Status({ value }) {
  const map = { online: ["Online", "status-online"], warning: ["Warning", "status-warning"], offline: ["Offline", "status-offline"], pending: ["Pending", "status-pending"], managed: ["Pending", "status-pending"] };
  const [label, cls] = map[value] || map.offline;
  return <span data-testid={`router-status-${value}`} className={`status ${cls}`}><i />{label}</span>;
}

function Metric({ icon: Icon, label, value, detail, tone = "cyan" }) {
  return <div className="metric" data-testid={`metric-${label.toLowerCase().replaceAll(" ", "-")}`}>
    <div className={`metric-icon ${tone}`}><Icon size={17} /></div><div><p>{label}</p><strong>{value}</strong><small>{detail}</small></div>
  </div>;
}

function ResourceTable({ tab, routerId, revealSecret, onRevealToggle }) {
  const resourceKey = RESOURCE_KEY[tab];
  const columns = RESOURCE_COLUMNS[tab] || [];
  const [state, setState] = useState({ loading: true, error: "", items: [] });

  useEffect(() => {
    if (!resourceKey || !routerId) return;
    const controller = new AbortController();
    setState({ loading: true, error: "", items: [] });
    const params = resourceKey === "ppp-secrets" && revealSecret ? "?reveal=true" : "";
    axios.get(`${API}/routers/${routerId}/resources/${resourceKey}${params}`, { signal: controller.signal })
      .then(r => setState({ loading: false, error: "", items: r.data?.items || [] }))
      .catch(err => {
        if (axios.isCancel(err) || err.name === "CanceledError") return;
        const status = err.response?.status;
        const detail = err.response?.data?.detail;
        const message = status === 404
          ? "This is a demo router. Configure a managed router with live RouterOS credentials to see real data here."
          : detail || "RouterOS API is unreachable. Verify the router credentials, port, and server allow-list.";
        setState({ loading: false, error: message, items: [] });
      });
    return () => controller.abort();
  }, [resourceKey, routerId, revealSecret]);

  if (state.loading) return <div className="res-loading" data-testid={`${resourceKey}-loading`}><Loader2 size={14} className="spin" />Loading {tab.toLowerCase()} from RouterOS API…</div>;
  if (state.error) return <div className="res-error" data-testid={`${resourceKey}-error`}>{state.error}</div>;

  const singleObject = tab === "System Time" || tab === "System Identity" || tab === "System Resource";
  if (singleObject) {
    const c = state.items?.[0] || {};
    return <div className="clock-grid" data-testid={`${resourceKey}-panel`}>
      {columns.map(col => <div key={col}><span>{col.replaceAll("-", " ")}</span><b data-testid={`clock-${col}`}>{c[col] ?? "—"}</b></div>)}
    </div>;
  }

  return <>
    <div className="res-toolbar">
      <b data-testid={`${resourceKey}-count`}>{state.items.length} {tab.toLowerCase()}</b>
      {tab === "PPP Secrets" && <button className={`reveal-btn ${revealSecret ? "on" : ""}`} onClick={onRevealToggle} data-testid="ppp-secrets-reveal-toggle">
        {revealSecret ? <><EyeOff size={13} />Hide passwords</> : <><Eye size={13} />Reveal passwords</>}
      </button>}
    </div>
    <div className="res-table" data-testid={`${resourceKey}-table`}>
      <table><thead><tr>{columns.map(c => <th key={c}>{c.replaceAll("-", " ").toUpperCase()}</th>)}</tr></thead>
      <tbody>
        {state.items.length === 0 && <tr><td colSpan={columns.length} className="res-empty">No entries returned by RouterOS.</td></tr>}
        {state.items.map((row, i) => <tr key={row[".id"] || i} data-testid={`${resourceKey}-row-${i}`}>
          {columns.map(c => <td key={c}>{row[c] ?? "—"}</td>)}
        </tr>)}
      </tbody></table>
    </div>
  </>;
}

function GroupTelegramRow({ group, existing, onSaved, onDeleted, onNotice }) {
  const [botToken, setBotToken] = useState("");
  const [chatId, setChatId] = useState(existing?.chat_id || "");
  const [enabled, setEnabled] = useState(existing?.enabled ?? true);
  const [busy, setBusy] = useState("");
  const isConfigured = !!existing;

  const save = async () => {
    if (!botToken && !isConfigured) { onNotice("Enter a bot token to save this group"); return; }
    setBusy("save");
    try {
      const body = { chat_id: chatId, enabled, ...(botToken ? { bot_token: botToken } : {}) };
      if (!botToken && isConfigured) {
        // just toggle enabled/chat via delete+recreate is bad; require token to update
        onNotice("Paste the bot token again to update this group");
        setBusy(""); return;
      }
      await axios.put(`${API}/notifications/telegram/${encodeURIComponent(group)}`, body);
      setBotToken("");
      onNotice(`${group}: Telegram config saved`);
      onSaved();
    } catch (e) {
      const detail = e.response?.data?.detail;
      onNotice(typeof detail === "string" ? detail : "Save failed — check bot token and chat id format");
    } finally { setBusy(""); }
  };

  const test = async () => {
    setBusy("test");
    try {
      await axios.post(`${API}/notifications/telegram/${encodeURIComponent(group)}/test`);
      onNotice(`${group}: Test message delivered to Telegram`);
    } catch (e) {
      const detail = e.response?.data?.detail;
      onNotice(typeof detail === "string" ? detail : `${group}: Telegram send failed`);
    } finally { setBusy(""); }
  };

  const remove = async () => {
    setBusy("del");
    try {
      await axios.delete(`${API}/notifications/telegram/${encodeURIComponent(group)}`);
      onNotice(`${group}: Telegram config removed`); onDeleted();
    } catch (e) { onNotice("Delete failed"); } finally { setBusy(""); }
  };

  return <div className="tg-row" data-testid={`tg-row-${group.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}`}>
    <div className="tg-head">
      <div><i className="group-dot" /><b>{group}</b></div>
      <div className="tg-status">
        {isConfigured
          ? <span className="tg-pill on" data-testid={`tg-status-${group}`}><Check size={12} />{existing.enabled ? "Enabled" : "Disabled"} · {existing.token_hint}</span>
          : <span className="tg-pill off" data-testid={`tg-status-${group}`}>Not configured</span>}
      </div>
    </div>
    <div className="tg-fields">
      <label>Bot token{isConfigured && <em> (paste to replace)</em>}
        <input type="password" value={botToken} onChange={e => setBotToken(e.target.value)} placeholder="123456789:AA...zz" data-testid={`tg-token-${group}`} autoComplete="off" />
      </label>
      <label>Chat ID
        <input value={chatId} onChange={e => setChatId(e.target.value)} placeholder="-1001234567890" data-testid={`tg-chat-${group}`} />
      </label>
      <label className="tg-toggle">
        <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} data-testid={`tg-enabled-${group}`} />
        <span>Deliver alarms</span>
      </label>
    </div>
    <div className="tg-actions">
      <button className="button primary compact" onClick={save} disabled={busy === "save"} data-testid={`tg-save-${group}`}>
        <Save size={13} />{busy === "save" ? "Saving..." : "Save"}
      </button>
      <button className="button secondary compact" onClick={test} disabled={!isConfigured || busy === "test"} data-testid={`tg-test-${group}`}>
        <Send size={13} />{busy === "test" ? "Sending..." : "Send test"}
      </button>
      {isConfigured && <button className="tg-del" onClick={remove} disabled={busy === "del"} data-testid={`tg-delete-${group}`}>
        <Trash2 size={13} />Remove
      </button>}
    </div>
  </div>;
}

function NotificationsPanel({ groups, onNotice }) {
  const [configs, setConfigs] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const load = async () => {
    try { const r = await axios.get(`${API}/notifications/telegram`); setConfigs(r.data?.items || []); }
    catch { setConfigs([]); }
    finally { setLoaded(true); }
  };
  useEffect(() => { load(); }, []);
  const byGroup = useMemo(() => Object.fromEntries(configs.map(c => [c.group, c])), [configs]);

  return <section className="panel notif-panel" data-testid="notifications-panel">
    <div className="panel-head">
      <div><p className="eyebrow">TELEGRAM DELIVERY</p><h2>Group notification channels</h2></div>
      <span className="api-lock"><ShieldCheck size={13} />Tokens encrypted at rest</span>
    </div>
    <p className="notif-help">Create a bot with <b>@BotFather</b> on Telegram to get a token, then add the bot to your group/channel and send it <b>/start</b>. Paste the token + chat ID for each device group below. Alarms (CPU threshold, interface up/down, router unreachable) will be routed to the matching group's chat.</p>
    {!loaded && <div className="res-loading"><Loader2 size={14} className="spin" />Loading Telegram configuration…</div>}
    {loaded && <div className="tg-list">
      {groups.slice(1).map(g => <GroupTelegramRow key={g} group={g} existing={byGroup[g]} onSaved={load} onDeleted={load} onNotice={onNotice} />)}
    </div>}
  </section>;
}

function AddRouterModal({ open, onClose, groups, onCreated, onNotice }) {
  const [form, setForm] = useState({ name: "", host: "", port: "8728", username: "", password: "", group: groups?.[1] || "Unassigned" });
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setForm({ name: "", host: "", port: "8728", username: "", password: "", group: groups?.[1] || "Unassigned" }); }, [open, groups]);
  if (!open) return null;
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      const body = { name: form.name.trim(), host: form.host.trim(), port: parseInt(form.port, 10) || 8728, username: form.username.trim(), password: form.password, group: form.group };
      const r = await axios.post(`${API}/routers`, body);
      onNotice(`${r.data?.router?.name || "Router"} onboarded — connection test queued`);
      onCreated(); onClose();
    } catch (err) {
      const detail = err.response?.data?.detail;
      onNotice(typeof detail === "string" ? detail : "Add router failed — check the fields and try again");
    } finally { setBusy(false); }
  };
  return <div className="modal-backdrop" onClick={onClose} data-testid="add-router-backdrop">
    <div className="modal" onClick={e => e.stopPropagation()} data-testid="add-router-modal">
      <div className="drawer-head"><div><p className="eyebrow">ONBOARDING</p><h2>Add MikroTik router</h2><span className="muted">Credentials are AES-encrypted server-side and never returned to the browser.</span></div><button className="icon-btn" onClick={onClose} data-testid="close-add-router"><X size={18} /></button></div>
      <form onSubmit={submit} className="add-form">
        <label>Display name<input required minLength={2} value={form.name} onChange={e => set("name", e.target.value)} placeholder="HQ Core Router" data-testid="add-router-name" /></label>
        <label>Host / IP<input required value={form.host} onChange={e => set("host", e.target.value)} placeholder="10.10.0.1" data-testid="add-router-host" /></label>
        <div className="two-col">
          <label>API port
            <select value={form.port} onChange={e => set("port", e.target.value)} data-testid="add-router-port">
              <option value="8728">8728 · plaintext</option>
              <option value="8729">8729 · api-ssl</option>
            </select>
          </label>
          <label>Group
            <select value={form.group} onChange={e => set("group", e.target.value)} data-testid="add-router-group">
              {(groups || []).filter(g => g !== "All routers").map(g => <option key={g} value={g}>{g}</option>)}
            </select>
          </label>
        </div>
        <label>Username<input required value={form.username} onChange={e => set("username", e.target.value)} placeholder="admin" autoComplete="off" data-testid="add-router-username" /></label>
        <label>Password<input type="password" required value={form.password} onChange={e => set("password", e.target.value)} placeholder="Router API password" autoComplete="new-password" data-testid="add-router-password" /></label>
        <div className="modal-actions">
          <button type="button" className="button secondary" onClick={onClose} data-testid="add-router-cancel">Cancel</button>
          <button type="submit" className="button primary" disabled={busy} data-testid="add-router-submit"><Plus size={14} />{busy ? "Saving..." : "Save router"}</button>
        </div>
      </form>
    </div>
  </div>;
}

function AddGroupModal({ open, onClose, onCreated, onNotice }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setName(""); }, [open]);
  if (!open) return null;
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      const r = await axios.post(`${API}/groups`, { name: name.trim() });
      onNotice(`Group "${r.data?.group}" created`); onCreated(); onClose();
    } catch (err) {
      const detail = err.response?.data?.detail;
      onNotice(typeof detail === "string" ? detail : "Add group failed");
    } finally { setBusy(false); }
  };
  return <div className="modal-backdrop" onClick={onClose} data-testid="add-group-backdrop">
    <div className="modal" onClick={e => e.stopPropagation()} data-testid="add-group-modal">
      <div className="drawer-head"><div><p className="eyebrow">DEVICE GROUPS</p><h2>Add group</h2><span className="muted">Groups scope routers, Telegram alerts, and future tenant access.</span></div><button className="icon-btn" onClick={onClose} data-testid="close-add-group"><X size={18} /></button></div>
      <form onSubmit={submit} className="add-form">
        <label>Group name<input required minLength={2} maxLength={60} value={name} onChange={e => setName(e.target.value)} placeholder="Region West" data-testid="add-group-name" /></label>
        <div className="modal-actions">
          <button type="button" className="button secondary" onClick={onClose} data-testid="add-group-cancel">Cancel</button>
          <button type="submit" className="button primary" disabled={busy} data-testid="add-group-submit"><Plus size={14} />{busy ? "Saving..." : "Create group"}</button>
        </div>
      </form>
    </div>
  </div>;
}

function WorkspacePage({ router, onBack, onNotice, onRefresh, onRemove }) {
  const [cat, setCat] = useState("Interfaces");
  const [revealSecret, setRevealSecret] = useState(false);
  const [conn, setConn] = useState({ connected: false, connected_at: 0 });
  const [busy, setBusy] = useState("");
  useEffect(() => { if (cat !== "PPP Secrets") setRevealSecret(false); }, [cat]);

  const loadConn = async () => { try { const r = await axios.get(`${API}/routers/${router.id}/connection`); setConn(r.data || { connected: false }); } catch { setConn({ connected: false }); } };
  useEffect(() => { loadConn(); const t = setInterval(loadConn, 15000); return () => clearInterval(t); }, [router.id]);

  const test = async () => {
    setBusy("test"); onNotice(`Testing connection to ${router.name}…`);
    try {
      const r = await axios.post(`${API}/routers/${router.id}/test-connection`);
      onNotice(r.data?.status === "online" ? `${router.name} · CPU ${r.data?.cpu ?? 0}% · uptime ${r.data?.uptime || "—"}` : `${router.name} is unreachable: ${r.data?.error || "connection refused"}`);
      onRefresh(); loadConn();
    } catch (e) { onNotice(e.response?.data?.detail || "Connection test failed"); }
    finally { setBusy(""); }
  };
  const disconnect = async () => {
    setBusy("disc");
    try { await axios.post(`${API}/routers/${router.id}/disconnect`); onNotice(`${router.name}: session closed`); loadConn(); }
    catch (e) { onNotice("Disconnect failed"); }
    finally { setBusy(""); }
  };
  const openTab = () => window.open(`${window.location.origin}/?router=${router.id}&cat=${encodeURIComponent(cat)}`, "_blank", "noopener");

  const connLabel = conn.connected ? `Session up · ${Math.max(0, Math.round((Date.now() / 1000 - conn.connected_at) / 60))}m` : "No session";

  return <section className="workspace-page" data-testid={`workspace-${router.id}`}>
    <header className="ws-topbar">
      <div className="ws-title">
        {onBack && <button className="icon-btn" onClick={onBack} data-testid="ws-back-button"><ChevronLeft size={18} /></button>}
        <div className={`router-icon ${router.color || "cyan"}`}><Router size={17} /></div>
        <div className="ws-title-text">
          <b data-testid="ws-router-name">{router.name}</b>
          <span className="mono">{router.host} · {router.port || 8728} · ROS {router.version || "—"}</span>
        </div>
        <Status value={router.status} />
      </div>
      <div className="ws-conn"><span className={`ws-dot ${conn.connected ? "on" : "off"}`} />{connLabel}</div>
      <div className="ws-actions">
        <button className="button secondary compact" onClick={test} disabled={busy === "test"} data-testid="ws-test-connection"><RefreshCw size={13} className={busy === "test" ? "spin" : ""} />Test</button>
        <button className="button secondary compact" onClick={disconnect} disabled={busy === "disc" || !conn.connected} data-testid="ws-disconnect"><Power size={13} />Disconnect</button>
        <button className="button secondary compact" onClick={openTab} data-testid="ws-open-new-tab"><ExternalLink size={13} />New tab</button>
        {router.id?.startsWith("mr-") && onRemove && <button className="button secondary compact tg-del" onClick={() => onRemove(router.id, router.name)} data-testid="ws-remove-router"><Trash2 size={13} />Remove</button>}
      </div>
    </header>
    <div className="ws-body">
      <aside className="ws-menu" data-testid="ws-menu">
        {WINBOX_MENU.map(section => <div key={section.section} className="ws-menu-section">
          <span className="ws-menu-title">{section.section}</span>
          {section.items.map(item => <button key={item} className={cat === item ? "active" : ""} onClick={() => setCat(item)} data-testid={`ws-menu-${RESOURCE_KEY[item]}`}>{item.replace(/^(PPP|System) /, "")}</button>)}
        </div>)}
      </aside>
      <div className="ws-main" data-testid="ws-main">
        <div className="ws-cat-head">
          <p className="eyebrow">ROUTEROS API · {cat.toUpperCase()}</p>
          <h2 data-testid="ws-cat-title">{cat}</h2>
        </div>
        <ResourceTable key={`${router.id}-${cat}`} tab={cat} routerId={router.id} revealSecret={revealSecret} onRevealToggle={() => setRevealSecret(v => !v)} />
      </div>
    </div>
  </section>;
}

function App() {
  const [data, setData] = useState(fallback);
  const [active, setActive] = useState("Overview");
  const [group, setGroup] = useState("All routers");
  const [query, setQuery] = useState("");
  const [drawer, setDrawer] = useState(false);
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState(null);
  const [drawerTab, setDrawerTab] = useState("Interfaces");
  const [backupBusy, setBackupBusy] = useState(false);
  const [revealSecret, setRevealSecret] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [addGroupOpen, setAddGroupOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const loadOverview = async () => {
    try { const r = await axios.get(`${API}/monitoring/overview`); if (r.data) setData(r.data); }
    catch { /* keep fallback */ }
  };
  useEffect(() => { loadOverview(); }, []);
  // Deep-link: ?router=mr-xxx opens workspace on load
  useEffect(() => {
    const url = new URL(window.location.href);
    const rid = url.searchParams.get("router");
    if (rid && data.routers.length) {
      const r = data.routers.find(x => x.id === rid);
      if (r) { setSelected(r); setActive("Workspace"); }
    }
  }, [data.routers.length]);
  useEffect(() => { if (drawerTab !== "PPP Secrets") setRevealSecret(false); }, [drawerTab, selected]);
  useEffect(() => { if (!notice) return; const t = setTimeout(() => setNotice(""), 4200); return () => clearTimeout(t); }, [notice]);

  const openWorkspace = (r) => {
    setSelected(r); setActive("Workspace");
    const url = new URL(window.location.href); url.searchParams.set("router", r.id);
    window.history.replaceState({}, "", url.toString());
  };
  const closeWorkspace = () => {
    setSelected(null); setActive("Overview");
    const url = new URL(window.location.href); url.searchParams.delete("router"); url.searchParams.delete("cat");
    window.history.replaceState({}, "", url.toString());
  };

  const routers = useMemo(() => data.routers.filter(r => (group === "All routers" || r.group === group) && `${r.name} ${r.host}`.toLowerCase().includes(query.toLowerCase())), [data, group, query]);
  const online = data.routers.filter(r => r.status === "online").length;
  const show = (label) => { setActive(label); };
  const refresh = async () => {
    setRefreshing(true);
    try { await axios.post(`${API}/monitoring/probe-all`); } catch { /* ignore */ }
    await loadOverview(); setRefreshing(false); setNotice("Fleet inventory refreshed");
  };
  const requestResource = async (resource, label) => {
    try { await axios.get(`${API}/routers/${selected?.id || data.routers[0].id}/resources/${resource}`); setNotice(`${label} loaded from RouterOS API`); }
    catch (error) { setNotice(error.response?.data?.detail || `${label} is unavailable until a managed router is configured`); }
  };
  const queueBackup = async () => {
    setBackupBusy(true);
    try { const response = await axios.post(`${API}/routers/${selected?.id || data.routers[0].id}/backup-now`); setNotice(response.data?.message || "Backup queued"); }
    catch (error) { setNotice(error.response?.data?.detail || "Backup settings are required before running this"); }
    finally { setBackupBusy(false); }
  };
  const testConnection = async (id, name) => {
    setNotice(`Testing connection to ${name}…`);
    try {
      const r = await axios.post(`${API}/routers/${id}/test-connection`);
      const status = r.data?.status;
      setNotice(status === "online" ? `${name} is ONLINE · CPU ${r.data?.cpu ?? 0}% · uptime ${r.data?.uptime || "—"}` : `${name} is unreachable: ${r.data?.error || "connection refused"}`);
      loadOverview();
    } catch (e) {
      setNotice(e.response?.data?.detail || `Connection test failed for ${name}`);
    }
  };
  const removeGroup = async (name) => {
    try { await axios.delete(`${API}/groups/${encodeURIComponent(name)}`); setNotice(`Group "${name}" removed`); if (group === name) setGroup("All routers"); loadOverview(); }
    catch (e) { setNotice(e.response?.data?.detail || "Delete group failed"); }
  };
  const headingActions = {
    "Overview": <><button className="button secondary" onClick={() => setNotice("Widget layout saved")} data-testid="customize-dashboard-button"><SlidersHorizontal size={16} />Customize</button><button className="button primary" onClick={() => setAddOpen(true)} data-testid="add-router-button"><Plus size={16} />Add router</button></>,
    "Routers": <button className="button primary" onClick={() => setAddOpen(true)} data-testid="add-router-button"><Plus size={16} />Add router</button>,
    "Groups & Tenants": <button className="button primary" onClick={() => setAddGroupOpen(true)} data-testid="add-group-button"><Plus size={16} />Add group</button>,
    "Alarms": <button className="button primary" onClick={() => setNotice("Alarm rules editor coming next")} data-testid="new-alarm-rule-button"><Plus size={16} />New rule</button>,
  };
  const removeRouter = async (id, name) => {
    if (!id?.startsWith("mr-")) { setNotice("Demo routers cannot be removed"); return; }
    try { await axios.delete(`${API}/routers/${id}`); setNotice(`${name} removed`); setSelected(null); loadOverview(); }
    catch (e) { setNotice(e.response?.data?.detail || "Delete failed"); }
  };

  return <div className="app-shell">
    <aside className={`sidebar ${drawer ? "open" : ""}`} data-testid="main-sidebar">
      <div className="brand"><div className="brand-mark"><Network size={20} /></div><div><b>NETPULSE</b><span>mikrotik control plane</span></div><button className="icon-btn mobile-close" onClick={() => setDrawer(false)} data-testid="close-sidebar-button"><X size={17} /></button></div>
      <div className="workspace"><span>WORKSPACE</span><button data-testid="workspace-selector">Central Operations <ChevronDown size={14} /></button></div>
      <nav>{nav.map(({ label, icon: Icon, count }) => <button key={label} onClick={() => show(label)} className={active === label ? "active" : ""} data-testid={`nav-${label.toLowerCase().replaceAll(" ", "-")}`}><Icon size={17} />{label}{count && <em>{count}</em>}</button>)}</nav>
      <div className="side-section"><span>DEVICE GROUPS</span>{data.groups.slice(1).map(g => <button key={g} onClick={() => { setGroup(g); show("Routers"); }} data-testid={`group-${g.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}`}><i className="group-dot" />{g}<small>{data.routers.filter(r => r.group === g).length}</small></button>)}</div>
      <div className="sidebar-bottom"><button className={active === "Settings" ? "active" : ""} onClick={() => show("Settings")} data-testid="nav-settings"><Settings2 size={17} />Settings</button><div className="user-chip"><div className="avatar">SA</div><div><b>Super Admin</b><span>Full access</span></div><Ellipsis size={16} /></div></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><button className="icon-btn menu-btn" onClick={() => setDrawer(true)} data-testid="open-sidebar-button"><Menu size={19} /></button><div className="crumb"><span>Workspace</span><ChevronRight size={14} /><b>{active === "Workspace" && selected ? selected.name : active}</b></div><div className="top-actions"><div className="connection"><i />Live polling <span>30s</span></div><button className="icon-btn" onClick={refresh} disabled={refreshing} data-testid="refresh-monitoring-button"><RefreshCw size={17} className={refreshing ? "spin" : ""} /></button><button className="notification" onClick={() => show("Alarms")} data-testid="open-notifications-button"><Bell size={17} /><i /></button><div className="top-avatar">SA</div></div></header>
      <section className="content">
        {active !== "Workspace" && <div className="page-heading"><div><p className="eyebrow">CENTRAL MONITORING / {new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase()}</p><h1>{active === "Overview" ? "Network overview" : active}</h1><p className="subheading">{ {"Overview":"A real-time view of your MikroTik infrastructure and active signals.","Routers":"Managed device inventory across all groups.","Groups & Tenants":"Logical folders that scope access, backups, and alarms.","Alarms":"Threshold breaches and recovery events from every router.","Audit log":"Every action taken on this control plane.","Settings":"Configure notification channels, backups, and workspace preferences."}[active] || ""}</p></div><div className="heading-actions">{headingActions[active] || null}</div></div>}
        {notice && <div className="toast" data-testid="notification-toast"><Activity size={16} />{notice}</div>}
        {active === "Workspace" && selected && <WorkspacePage router={selected} onBack={closeWorkspace} onNotice={setNotice} onRefresh={loadOverview} onRemove={(id, name) => { removeRouter(id, name); closeWorkspace(); }} />}
        {active === "Settings" && <NotificationsPanel groups={data.groups} onNotice={setNotice} />}
        {active === "Groups & Tenants" && <section className="panel routers-panel" data-testid="groups-view"><div className="panel-head table-head"><div><p className="eyebrow">DEVICE GROUPS / {data.groups.length - 1} GROUPS</p><h2>Groups & tenants</h2></div></div><div className="table-wrap"><table><thead><tr><th>GROUP</th><th>ROUTERS</th><th>TELEGRAM</th><th></th></tr></thead><tbody>{data.groups.slice(1).map(g => { const count = data.routers.filter(r => r.group === g).length; return <tr key={g} data-testid={`groups-row-${g.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}`} onClick={() => { setGroup(g); show("Routers"); }}><td><div className="router-name"><div className="router-icon cyan"><Users size={15} /></div><div><b>{g}</b><span>{count} device{count !== 1 ? "s" : ""}</span></div></div></td><td className="mono">{count}</td><td><span className="muted">Configure in Settings › Notifications</span></td><td><div className="row-actions">{(data.custom_groups || []).includes(g) && count === 0 && <button className="icon-btn tg-del" onClick={(e) => { e.stopPropagation(); removeGroup(g); }} title="Remove group" data-testid={`groups-delete-${g.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}`}><Trash2 size={15} /></button>}<button className="row-arrow" data-testid={`groups-open-${g.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}`}><ChevronRight size={16} /></button></div></td></tr>; })}</tbody></table></div></section>}
        {active === "Alarms" && <section className="panel alarm-panel" data-testid="alarms-view"><div className="panel-head"><div><p className="eyebrow">SIGNAL CENTER / 3 ACTIVE</p><h2>Alarm feed</h2></div></div><div className="alarm-list"><div className="alarm-item danger"><div className="alarm-symbol"><AlertTriangle size={16} /></div><div><b>CPU threshold exceeded</b><span>Warehouse Gateway · 83% CPU</span><small>2 minutes ago</small></div></div><div className="alarm-item warning"><div className="alarm-symbol"><Wifi size={16} /></div><div><b>Interface status changed</b><span>East Branch · ether4 is down</span><small>18 minutes ago</small></div></div><div className="alarm-item info"><div className="alarm-symbol"><Bell size={16} /></div><div><b>Telegram notification sent</b><span>Partner · PT ABC · resolved</span><small>42 minutes ago</small></div></div></div></section>}
        {active === "Audit log" && <section className="panel" data-testid="audit-view"><div className="panel-head"><div><p className="eyebrow">SECURITY / IMMUTABLE</p><h2>Audit log</h2></div></div><div className="drawer-message"><ShieldCheck size={17} />Audit entries appear here once role-based writes are enabled. Read-only navigation is not logged.</div></section>}
        {(active === "Overview" || active === "Routers") && <><div className="metrics-grid"><Metric icon={Router} label="Total routers" value={data.routers.length} detail={`${online} online · 1 warning`} /><Metric icon={CircleGauge} label="Network health" value="94.2%" detail="↑ 2.8% from yesterday" tone="green" /><Metric icon={Activity} label="Aggregate traffic" value="2.40 Gbps" detail="Inbound across 3 routers" tone="violet" /><Metric icon={AlertTriangle} label="Active alarms" value="03" detail="2 high · 1 medium" tone="amber" /></div>
        {active === "Overview" && <div className="main-grid"><section className="panel traffic-panel"><div className="panel-head"><div><p className="eyebrow">BANDWIDTH TELEMETRY</p><h2>Aggregate traffic</h2></div><div className="periods"><button className="selected" data-testid="traffic-period-24h">24H</button><button data-testid="traffic-period-7d">7D</button><button data-testid="traffic-period-30d">30D</button></div></div><div className="chart-legend"><span><i className="legend-in" />Inbound <b>2.40 Gbps</b></span><span><i className="legend-out" />Outbound <b>1.18 Gbps</b></span></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data.traffic}><defs><linearGradient id="inbound" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#38bdf8" stopOpacity=".30" /><stop offset="100%" stopColor="#38bdf8" stopOpacity="0" /></linearGradient><linearGradient id="outbound" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a78bfa" stopOpacity=".2" /><stop offset="100%" stopColor="#a78bfa" stopOpacity="0" /></linearGradient></defs><XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} /><YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} width={32} /><Tooltip contentStyle={{ background: "#111827", border: "1px solid #26344b", borderRadius: 6, color: "#f8fafc" }} /><Area type="monotone" dataKey="inbound" stroke="#38bdf8" fill="url(#inbound)" strokeWidth={2} /><Area type="monotone" dataKey="outbound" stroke="#a78bfa" fill="url(#outbound)" strokeWidth={2} /></AreaChart></ResponsiveContainer></div></section><section className="panel alarm-panel"><div className="panel-head"><div><p className="eyebrow">SIGNAL CENTER</p><h2>Active alarms</h2></div><button className="text-btn" onClick={() => show("Alarms")} data-testid="view-all-alarms-button">View all <ChevronRight size={14} /></button></div><div className="alarm-list"><div className="alarm-item danger"><div className="alarm-symbol"><AlertTriangle size={16} /></div><div><b>CPU threshold exceeded</b><span>Warehouse Gateway · 83% CPU</span><small>2 minutes ago</small></div><button className="alarm-menu" data-testid="alarm-menu-cpu"><Ellipsis size={16} /></button></div><div className="alarm-item warning"><div className="alarm-symbol"><Wifi size={16} /></div><div><b>Interface status changed</b><span>East Branch · ether4 is down</span><small>18 minutes ago</small></div><button className="alarm-menu" data-testid="alarm-menu-interface"><Ellipsis size={16} /></button></div><div className="alarm-item info"><div className="alarm-symbol"><Bell size={16} /></div><div><b>Telegram notification sent</b><span>Partner · PT ABC · resolved</span><small>42 minutes ago</small></div><button className="alarm-menu" data-testid="alarm-menu-telegram"><Ellipsis size={16} /></button></div></div></section></div>}
        <section className="panel routers-panel"><div className="panel-head table-head"><div><p className="eyebrow">INVENTORY / {data.routers.length} DEVICES</p><h2>Router fleet</h2></div><div className="table-tools"><div className="search"><Search size={15} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Filter routers..." data-testid="router-search-input" /></div><select value={group} onChange={e => setGroup(e.target.value)} data-testid="router-group-filter">{data.groups.map(g => <option key={g}>{g}</option>)}</select><button className="icon-btn" data-testid="router-table-settings"><SlidersHorizontal size={16} /></button></div></div><div className="table-wrap"><table><thead><tr><th>ROUTER</th><th>GROUP</th><th>STATUS</th><th>CPU</th><th>MEMORY</th><th>TRAFFIC</th><th>UPTIME</th><th></th></tr></thead><tbody>{routers.map(r => <tr key={r.id} onClick={() => openWorkspace(r)} data-testid={`router-row-${r.id}`}><td><div className="router-name"><div className={`router-icon ${r.color}`}><Router size={15} /></div><div><b>{r.name}</b><span>{r.host} · ROS {r.version || "—"}</span></div></div></td><td><span className="group-label">{r.group}</span></td><td><Status value={r.status} /></td><td><div className="bar-value"><span>{r.cpu}%</span><i><b style={{ width: `${r.cpu}%` }} /></i></div></td><td><div className="bar-value"><span>{r.memory ? `${r.memory}%` : "—"}</span><i><b className={r.memory > 70 ? "warn" : ""} style={{ width: `${r.memory}%` }} /></i></div></td><td className="mono">{r.traffic || "—"}</td><td className="muted">{r.uptime}</td><td><button className="row-arrow" onClick={(e) => { e.stopPropagation(); openWorkspace(r); }} data-testid={`router-details-${r.id}`}><ChevronRight size={16} /></button></td></tr>)}</tbody></table>{routers.length === 0 && <div className="empty-state" data-testid="empty-router-state">No routers match this filter.</div>}</div></section>
        {active === "Overview" && <><div className="footer-note"><span><Database size={14} />Native RouterOS graph data · lightweight cache</span><span>Last sync: just now · <b>All systems operational</b></span></div>
        <div className="management-strip"><section className="panel management-panel"><div className="panel-head"><div><p className="eyebrow">NATIVE ROUTEROS API</p><h2>Direct configuration</h2></div><span className="api-lock"><ShieldCheck size={13} />Named actions only</span></div><div className="action-grid"><button onClick={() => requestResource("interfaces", "Interface list")} data-testid="api-interfaces-action"><Wifi size={15} />Interfaces</button><button onClick={() => requestResource("addresses", "IP address list")} data-testid="api-addresses-action"><Network size={15} />IP addresses</button><button onClick={() => requestResource("firewall", "Firewall filter list")} data-testid="api-firewall-action"><ShieldCheck size={15} />Firewall rules</button><button onClick={() => setNotice("Write actions require Operator or Admin confirmation")} data-testid="api-write-action"><Settings2 size={15} />Write protection</button></div></section><section className="panel management-panel"><div className="panel-head"><div><p className="eyebrow">BACKUP ENGINE</p><h2>Configuration backups</h2></div><button className="button primary compact" disabled={backupBusy} onClick={queueBackup} data-testid="backup-now-button"><Database size={14} />{backupBusy ? "Queueing..." : "Backup now"}</button></div><div className="backup-summary"><div><b>0</b><span>Stored snapshots</span></div><div><b>—</b><span>Last successful run</span></div><div><b>UTC</b><span>Schedule timezone</span></div></div><p className="backup-note" data-testid="backup-status-note">Creates encrypted <code>.backup</code> and sanitized <code>.rsc</code> files under the configured server backup path, then emails both attachments.</p></section></div></>}</>}
      </section>
    </main>
    <AddRouterModal open={addOpen} onClose={() => setAddOpen(false)} groups={data.groups} onCreated={loadOverview} onNotice={setNotice} />
    <AddGroupModal open={addGroupOpen} onClose={() => setAddGroupOpen(false)} onCreated={loadOverview} onNotice={setNotice} />
  </div>;
}
export default App;
