import { useEffect, useMemo, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import {
  Activity, AlertTriangle, Bell, Building2, ChevronDown, ChevronRight, CircleGauge, Database, Ellipsis, LayoutDashboard,
  Loader2, LogOut, Menu, Network, Pencil, Plus, RefreshCw, Router, Save, Search, Settings2, ShieldCheck, SlidersHorizontal, Trash2, UserCog, Users, Wifi, X
} from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import "@/App.css";
import { api, errorText, slug } from "@/lib/api";
import { AuthProvider, useAuth } from "@/auth/AuthContext";
import Login from "@/pages/Login";
import AuthCallback from "@/pages/AuthCallback";
import UsersPage from "@/pages/UsersPage";
import RolesPage from "@/pages/RolesPage";
import WorkspacesPage from "@/pages/WorkspacesPage";
import MySettings from "@/pages/MySettings";
import GroupsPage, { GroupSettings } from "@/pages/GroupsPage";
import NotificationsPanel from "@/pages/NotificationsPanel";
import { Modal } from "@/components/Modal";
import { Status } from "@/components/Status";
import { WorkspacePage } from "@/components/RouterWorkspace";

const EMPTY = { workspace: null, routers: [], groups: [], traffic: [], alarms: [] };
const NAV = [
  { label: "Overview", icon: LayoutDashboard, module: "overview" }, { label: "Routers", icon: Router, module: "routers" },
  { label: "Groups & Tenants", icon: Users, module: "groups" }, { label: "Alarms", icon: Bell, module: "alarms" },
  { label: "Audit log", icon: ShieldCheck, module: "audit" },
];
const ADMIN_NAV = [
  { label: "Users", icon: UserCog, module: "users" }, { label: "Roles", icon: ShieldCheck, module: "roles" }, { label: "Workspaces", icon: Building2, module: "workspaces" },
];
const SUBHEAD = { Overview: "A real-time view of your MikroTik infrastructure and active signals.", Routers: "Managed device inventory across the groups you can access.", "Groups & Tenants": "Nested device groups that scope access, Telegram alarms, and backups.", Alarms: "Threshold breaches and recovery events from every router.", "Audit log": "Every action taken on this control plane.", Settings: "Telegram channels per role.", Users: "Accounts, roles, workspaces and per-user group scope.", Roles: "Custom privilege sets per module and device groups.", Workspaces: "Isolated tenants with their own groups and routers.", "My settings": "Your MikroTik credentials and account security." };

function Metric({ icon: Icon, label, value, detail, tone = "cyan" }) {
  return <div className="metric" data-testid={`metric-${slug(label)}`}><div className={`metric-icon ${tone}`}><Icon size={17} /></div><div><p>{label}</p><strong>{value}</strong><small>{detail}</small></div></div>;
}

function AddRouterModal({ open, onClose, groups, onCreated, onNotice, editing, canEditCreds }) {
  const blank = { name: "", host: "", port: "8728", username: "", password: "", group_id: groups?.[0]?.id || "", description: "" };
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setForm(editing ? { name: editing.name, host: editing.host, port: String(editing.port || 8728), username: editing.username || "", password: "", group_id: editing.group_id || "", description: editing.description || "" } : blank); }, [open, editing]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!open) return null;
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    const body = { name: form.name.trim(), host: form.host.trim(), port: parseInt(form.port, 10) || 8728, username: form.username.trim(), group_id: form.group_id, description: form.description.trim() };
    try {
      if (editing) {
        if (form.password) body.password = form.password;
        const r = await api.put(`/routers/${editing.id}`, body);
        onNotice(`${r.data.router.name} updated · ${r.data.probe?.status === "online" ? "connection OK" : "unreachable with new settings"}`); onCreated(r.data.router);
      } else {
        body.password = form.password;
        const r = await api.post("/routers", body);
        onNotice(`${r.data.router.name} onboarded · ${r.data.probe?.status === "online" ? "online" : "offline: " + (r.data.probe?.error || "unreachable")}`); onCreated();
      }
      onClose();
    } catch (err) { onNotice(errorText(err, `${editing ? "Update" : "Add"} router failed`)); }
    finally { setBusy(false); }
  };
  const credsLocked = editing && !canEditCreds;
  return <Modal open={open} onClose={onClose} title={editing ? "Edit router" : "Add MikroTik router"} eyebrow={editing ? `EDIT · ${editing.id}` : "ONBOARDING"} hint="Stored credentials are AES-encrypted server-side and only used by you (the owner) and Super Admins; other users connect with their own MikroTik account." testid={editing ? "edit-router-modal" : "add-router-modal"}>
    <form onSubmit={submit} className="add-form">
      <label>Display name<input required minLength={2} value={form.name} onChange={e => set("name", e.target.value)} placeholder="HQ Core Router" data-testid="add-router-name" /></label>
      <label>Description<input maxLength={200} value={form.description} onChange={e => set("description", e.target.value)} placeholder="Core router at IDC rack 3 (optional)" data-testid="add-router-description" /></label>
      <label>Host / IP<input required value={form.host} onChange={e => set("host", e.target.value)} placeholder="10.10.0.1" data-testid="add-router-host" /></label>
      <div className="two-col">
        <label>API port<select value={form.port} onChange={e => set("port", e.target.value)} data-testid="add-router-port"><option value="8728">8728 · plaintext</option><option value="8729">8729 · api-ssl</option></select></label>
        <label>Group<select required value={form.group_id} onChange={e => set("group_id", e.target.value)} data-testid="add-router-group"><option value="">— select group —</option>{groups.map(g => <option key={g.id} value={g.id}>{g.path}</option>)}</select></label>
      </div>
      {!credsLocked && <>
        <label>MikroTik username (owner credential)<input required value={form.username} onChange={e => set("username", e.target.value)} placeholder="admin" autoComplete="off" data-testid="add-router-username" /></label>
        <label>Password<input type="password" required={!editing} value={form.password} onChange={e => set("password", e.target.value)} placeholder={editing ? "Leave blank to keep current password" : "Router API password"} autoComplete="new-password" data-testid="add-router-password" /></label>
      </>}
      {credsLocked && <p className="muted">Stored credentials can only be changed by the router owner or a Super Admin.</p>}
      <div className="modal-actions">
        <button type="button" className="button secondary" onClick={onClose} data-testid="add-router-cancel">Cancel</button>
        <button type="submit" className="button primary" disabled={busy} data-testid="add-router-submit">{editing ? <Save size={14} /> : <Plus size={14} />}{busy ? "Saving..." : editing ? "Save changes" : "Save router"}</button>
      </div>
    </form>
  </Modal>;
}

function AuditView() {
  const [rows, setRows] = useState(null);
  useEffect(() => { api.get("/audit").then(r => setRows(r.data.items || [])).catch(() => setRows([])); }, []);
  return <section className="panel" data-testid="audit-view"><div className="panel-head"><div><p className="eyebrow">SECURITY / IMMUTABLE</p><h2>Audit log</h2></div></div>
    {rows === null ? <div className="res-loading"><Loader2 size={14} className="spin" />Loading…</div> : <div className="table-wrap"><table><thead><tr><th>WHEN</th><th>USER</th><th>ACTION</th><th>TARGET</th><th>DETAIL</th></tr></thead><tbody>
      {rows.length === 0 && <tr><td colSpan={5} className="res-empty">No actions recorded yet.</td></tr>}
      {rows.map(r => <tr key={r.id || r.created_at}><td className="muted">{new Date(r.created_at).toLocaleString()}</td><td className="mono">{r.email}</td><td><span className="group-label">{r.action}</span></td><td className="mono">{r.target}</td><td className="muted">{r.detail}</td></tr>)}
    </tbody></table></div>}
  </section>;
}

function Shell() {
  const { user, logout, can, workspaceId, setWorkspaceId } = useAuth();
  const [data, setData] = useState(EMPTY);
  const [active, setActive] = useState("Overview");
  const [group, setGroup] = useState("");
  const [query, setQuery] = useState("");
  const [drawer, setDrawer] = useState(false);
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState(null);
  const [initialCat, setInitialCat] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [groupModal, setGroupModal] = useState(false);
  const [groupSettings, setGroupSettings] = useState(null);
  const [wsMenu, setWsMenu] = useState(false);
  const [workspaces, setWorkspaces] = useState([]);
  const [refreshing, setRefreshing] = useState(false);

  const loadOverview = async () => {
    try { const r = await api.get("/monitoring/overview"); setData({ ...EMPTY, ...r.data }); }
    catch (err) { if (err.response?.status === 403) setNotice(errorText(err)); }
  };
  const loadWorkspaces = async () => { try { const r = await api.get("/workspaces"); setWorkspaces(r.data.items || []); } catch { /* ignore */ } };
  useEffect(() => { loadOverview(); loadWorkspaces(); setSelected(null); if (active === "Workspace") setActive("Overview"); }, [workspaceId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const url = new URL(window.location.href); const rid = url.searchParams.get("router");
    if (rid && data.routers.length) { const r = data.routers.find(x => x.id === rid); if (r) { setSelected(r); setInitialCat(url.searchParams.get("cat") || ""); setActive("Workspace"); } }
  }, [data.routers.length]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!notice) return; const t = setTimeout(() => setNotice(""), 4200); return () => clearTimeout(t); }, [notice]);
  useEffect(() => { if (selected) { const fresh = data.routers.find(r => r.id === selected.id); if (fresh) setSelected(fresh); } }, [data.routers]); // eslint-disable-line react-hooks/exhaustive-deps

  const openWorkspace = (r) => { setSelected(r); setActive("Workspace"); const url = new URL(window.location.href); url.searchParams.set("router", r.id); window.history.replaceState({}, "", url.toString()); };
  const closeWorkspace = () => { setSelected(null); setActive("Overview"); const url = new URL(window.location.href); url.searchParams.delete("router"); url.searchParams.delete("cat"); window.history.replaceState({}, "", url.toString()); };
  const show = (label) => { setActive(label); setDrawer(false); };
  const openEdit = (r) => { setEditing(r); setAddOpen(true); };
  const routers = useMemo(() => data.routers.filter(r => (!group || r.group_id === group) && `${r.name} ${r.host}`.toLowerCase().includes(query.toLowerCase())), [data, group, query]);
  const online = data.routers.filter(r => r.status === "online").length;
  const refresh = async () => { setRefreshing(true); try { await api.post("/monitoring/probe-all"); } catch { /* ignore */ } await loadOverview(); setRefreshing(false); setNotice("Fleet inventory refreshed"); };
  const removeRouter = async (id, name) => {
    if (!window.confirm(`Remove ${name} from NetPulse? The router itself is not touched.`)) return;
    try { await api.delete(`/routers/${id}`); setNotice(`${name} removed`); closeWorkspace(); loadOverview(); } catch (e) { setNotice(errorText(e, "Delete failed")); }
  };
  const canWriteRouters = can("routers", "write");
  const headingActions = {
    Overview: <>{canWriteRouters && <button className="button primary" onClick={() => { setEditing(null); setAddOpen(true); }} data-testid="add-router-button"><Plus size={16} />Add router</button>}</>,
    Routers: canWriteRouters && <button className="button primary" onClick={() => { setEditing(null); setAddOpen(true); }} data-testid="add-router-button"><Plus size={16} />Add router</button>,
    "Groups & Tenants": can("groups", "write") && <button className="button primary" onClick={() => setGroupModal(true)} data-testid="add-group-button"><Plus size={16} />Add group</button>,
    Alarms: can("alarms", "write") && <button className="button primary" onClick={() => setNotice("Alarm rules editor coming next")} data-testid="new-alarm-rule-button"><Plus size={16} />New rule</button>,
  };
  const currentWs = workspaces.find(w => w.id === workspaceId);
  const noAccess = !user.workspace_ids?.length;

  return <div className="app-shell">
    <aside className={`sidebar ${drawer ? "open" : ""}`} data-testid="main-sidebar">
      <div className="brand"><div className="brand-mark"><Network size={20} /></div><div><b>NETPULSE</b><span>mikrotik control plane</span></div><button className="icon-btn mobile-close" onClick={() => setDrawer(false)} data-testid="close-sidebar-button"><X size={17} /></button></div>
      <div className="workspace"><span>WORKSPACE</span>
        <button onClick={() => setWsMenu(v => !v)} data-testid="workspace-selector">{currentWs?.name || data.workspace?.name || "—"} <ChevronDown size={14} /></button>
        {wsMenu && <div className="ws-dropdown" data-testid="workspace-dropdown">
          {workspaces.map(w => <button key={w.id} className={w.id === workspaceId ? "on" : ""} onClick={() => { setWorkspaceId(w.id); setWsMenu(false); setNotice(`Switched to ${w.name}`); }} data-testid={`workspace-option-${w.id}`}><Building2 size={13} />{w.name}<small>{w.router_count}</small></button>)}
          {can("workspaces", "read") && <button className="manage" onClick={() => { show("Workspaces"); setWsMenu(false); }} data-testid="workspace-manage"><Settings2 size={13} />Manage workspaces</button>}
        </div>}
      </div>
      <nav>{NAV.filter(n => can(n.module)).map(({ label, icon: Icon }) => <button key={label} onClick={() => show(label)} className={active === label ? "active" : ""} data-testid={`nav-${slug(label)}`}><Icon size={17} />{label}{label === "Alarms" && data.alarms.length > 0 && <em>{data.alarms.length}</em>}</button>)}</nav>
      {ADMIN_NAV.some(n => can(n.module)) && <div className="side-section"><span>ADMINISTRATION</span>{ADMIN_NAV.filter(n => can(n.module)).map(({ label, icon: Icon }) => <button key={label} onClick={() => show(label)} className={active === label ? "active" : ""} data-testid={`nav-${slug(label)}`}><Icon size={15} />{label}</button>)}</div>}
      <div className="side-section"><span>DEVICE GROUPS</span>{data.groups.map(g => <button key={g.id} style={{ paddingLeft: 14 + g.depth * 12 }} onClick={() => { setGroup(g.id); show("Routers"); }} className={group === g.id && active === "Routers" ? "active" : ""} data-testid={`group-${slug(g.name)}`}><i className="group-dot" />{g.name}<small>{data.routers.filter(r => r.group_id === g.id).length}</small></button>)}</div>
      <div className="sidebar-bottom">
        {can("notifications") && <button className={active === "Settings" ? "active" : ""} onClick={() => show("Settings")} data-testid="nav-settings"><Settings2 size={17} />Settings</button>}
        <button className={active === "My settings" ? "active" : ""} onClick={() => show("My settings")} data-testid="nav-my-settings"><UserCog size={17} />My settings</button>
        <div className="user-chip"><div className="avatar">{(user.name || user.email).slice(0, 2).toUpperCase()}</div><div><b>{user.name}</b><span>{user.is_super_admin ? "Super Admin" : user.role?.name || "No role"}</span></div><button className="icon-btn" onClick={logout} title="Sign out" data-testid="logout-button"><LogOut size={15} /></button></div>
      </div>
    </aside>
    <main className="main-area">
      <header className="topbar"><button className="icon-btn menu-btn" onClick={() => setDrawer(true)} data-testid="open-sidebar-button"><Menu size={19} /></button><div className="crumb"><span>{currentWs?.name || "Workspace"}</span><ChevronRight size={14} /><b>{active === "Workspace" && selected ? selected.name : active}</b></div><div className="top-actions"><div className="connection"><i />Live polling <span>30s</span></div><button className="icon-btn" onClick={refresh} disabled={refreshing} data-testid="refresh-monitoring-button"><RefreshCw size={17} className={refreshing ? "spin" : ""} /></button><button className="notification" onClick={() => show("Alarms")} data-testid="open-notifications-button"><Bell size={17} />{data.alarms.length > 0 && <i />}</button><div className="top-avatar">{(user.name || user.email).slice(0, 2).toUpperCase()}</div></div></header>
      <section className="content">
        {active !== "Workspace" && <div className="page-heading"><div><p className="eyebrow">{(currentWs?.name || "NETPULSE").toUpperCase()} / {new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase()}</p><h1>{active === "Overview" ? "Network overview" : active}</h1><p className="subheading">{SUBHEAD[active] || ""}</p></div><div className="heading-actions">{headingActions[active] || null}</div></div>}
        {notice && <div className="toast" data-testid="notification-toast"><Activity size={16} />{notice}</div>}
        {noAccess && active !== "My settings" && <section className="panel" data-testid="no-access-view"><div className="drawer-message"><ShieldCheck size={17} />Your account is not assigned to any workspace yet. Ask an administrator to grant access.</div></section>}
        {active === "Workspace" && selected && <WorkspacePage router={selected} initialCat={initialCat} onBack={closeWorkspace} onNotice={setNotice} onRefresh={loadOverview} onEdit={openEdit} onRemove={removeRouter} onGoSettings={() => show("My settings")} canWriteRouters={canWriteRouters} />}
        {active === "Settings" && <NotificationsPanel onNotice={setNotice} />}
        {active === "My settings" && <MySettings onNotice={setNotice} />}
        {active === "Users" && <UsersPage onNotice={setNotice} groups={data.groups} />}
        {active === "Roles" && <RolesPage onNotice={setNotice} groups={data.groups} />}
        {active === "Workspaces" && <WorkspacesPage onNotice={setNotice} onChanged={() => { loadWorkspaces(); loadOverview(); }} />}
        {active === "Groups & Tenants" && <GroupsPage groups={data.groups} routers={data.routers} onNotice={setNotice} onChanged={loadOverview} onOpenGroup={(g) => setGroupSettings(g)} modalOpen={groupModal} setModalOpen={setGroupModal} />}
        {active === "Alarms" && <section className="panel alarm-panel" data-testid="alarms-view"><div className="panel-head"><div><p className="eyebrow">SIGNAL CENTER / {data.alarms.length} RECENT</p><h2>Alarm feed</h2></div></div>
          <div className="alarm-list">{data.alarms.length === 0 && <div className="drawer-message"><Bell size={16} />No alarms dispatched yet in this workspace. Alarms are delivered to Telegram channels of roles that cover the router's group.</div>}
            {data.alarms.map(a => <div key={a.id} className={`alarm-item ${a.kind === "router-unreachable" ? "danger" : a.kind === "cpu-threshold" ? "warning" : "info"}`} data-testid={`alarm-${a.id}`}><div className="alarm-symbol">{a.kind === "interface-status" ? <Wifi size={16} /> : <AlertTriangle size={16} />}</div><div><b>{a.kind}</b><span>{a.router_name} · {a.detail}</span><small>{new Date(a.created_at).toLocaleString()} · roles: {(a.roles_notified || []).join(", ") || "none"}</small></div></div>)}</div></section>}
        {active === "Audit log" && <AuditView />}
        {!noAccess && (active === "Overview" || active === "Routers") && <>
          <div className="metrics-grid"><Metric icon={Router} label="Total routers" value={data.routers.length} detail={`${online} online · ${data.routers.length - online} offline`} /><Metric icon={CircleGauge} label="Network health" value={data.routers.length ? `${Math.round(online * 100 / data.routers.length)}%` : "—"} detail="routers reachable via API" tone="green" /><Metric icon={Users} label="Device groups" value={data.groups.length} detail={`in ${currentWs?.name || "workspace"}`} tone="violet" /><Metric icon={AlertTriangle} label="Recent alarms" value={String(data.alarms.length).padStart(2, "0")} detail="last 20 dispatched" tone="amber" /></div>
          {active === "Overview" && <div className="main-grid"><section className="panel traffic-panel"><div className="panel-head"><div><p className="eyebrow">BANDWIDTH TELEMETRY · SAMPLE</p><h2>Aggregate traffic</h2></div></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data.traffic}><defs><linearGradient id="inbound" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#38bdf8" stopOpacity=".30" /><stop offset="100%" stopColor="#38bdf8" stopOpacity="0" /></linearGradient><linearGradient id="outbound" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a78bfa" stopOpacity=".2" /><stop offset="100%" stopColor="#a78bfa" stopOpacity="0" /></linearGradient></defs><XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} /><YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} width={32} /><Tooltip contentStyle={{ background: "#111827", border: "1px solid #26344b", borderRadius: 6, color: "#f8fafc" }} /><Area type="monotone" dataKey="inbound" stroke="#38bdf8" fill="url(#inbound)" strokeWidth={2} /><Area type="monotone" dataKey="outbound" stroke="#a78bfa" fill="url(#outbound)" strokeWidth={2} /></AreaChart></ResponsiveContainer></div></section>
            <section className="panel alarm-panel"><div className="panel-head"><div><p className="eyebrow">SIGNAL CENTER</p><h2>Recent alarms</h2></div><button className="text-btn" onClick={() => show("Alarms")} data-testid="view-all-alarms-button">View all <ChevronRight size={14} /></button></div><div className="alarm-list">{data.alarms.length === 0 && <div className="drawer-message"><Bell size={16} />No alarms yet.</div>}{data.alarms.slice(0, 3).map(a => <div key={a.id} className="alarm-item info"><div className="alarm-symbol"><AlertTriangle size={16} /></div><div><b>{a.kind}</b><span>{a.router_name}</span><small>{new Date(a.created_at).toLocaleString()}</small></div></div>)}</div></section></div>}
          <section className="panel routers-panel"><div className="panel-head table-head"><div><p className="eyebrow">INVENTORY / {data.routers.length} DEVICES</p><h2>Router fleet</h2></div><div className="table-tools"><div className="search"><Search size={15} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Filter routers..." data-testid="router-search-input" /></div><select value={group} onChange={e => setGroup(e.target.value)} data-testid="router-group-filter"><option value="">All routers</option>{data.groups.map(g => <option key={g.id} value={g.id}>{g.path}</option>)}</select></div></div>
            <div className="table-wrap"><table><thead><tr><th>ROUTER</th><th>GROUP</th><th>STATUS</th><th>CPU</th><th>MEMORY</th><th>VERSION</th><th>UPTIME</th><th></th></tr></thead><tbody>
              {routers.map(r => <tr key={r.id} onClick={() => openWorkspace(r)} data-testid={`router-row-${r.id}`}><td><div className="router-name"><div className={`router-icon ${r.color || "cyan"}`}><Router size={15} /></div><div><b>{r.name}</b><span>{r.host}{r.description ? ` · ${r.description}` : ""}</span></div></div></td><td><span className="group-label">{r.group}</span></td><td><Status value={r.status} /></td><td><div className="bar-value"><span>{r.cpu}%</span><i><b style={{ width: `${r.cpu}%` }} /></i></div></td><td><div className="bar-value"><span>{r.memory ? `${r.memory}%` : "—"}</span><i><b className={r.memory > 70 ? "warn" : ""} style={{ width: `${r.memory}%` }} /></i></div></td><td className="mono">{r.version}</td><td className="muted">{r.uptime}</td>
                <td><div className="row-actions">{canWriteRouters && <button className="icon-btn" title="Edit router" onClick={(e) => { e.stopPropagation(); openEdit(r); }} data-testid={`router-edit-${r.id}`}><Pencil size={15} /></button>}{canWriteRouters && <button className="icon-btn tg-del" title="Remove" onClick={(e) => { e.stopPropagation(); removeRouter(r.id, r.name); }} data-testid={`router-delete-${r.id}`}><Trash2 size={15} /></button>}<button className="row-arrow" onClick={(e) => { e.stopPropagation(); openWorkspace(r); }} data-testid={`router-details-${r.id}`}><ChevronRight size={16} /></button></div></td></tr>)}
            </tbody></table>{routers.length === 0 && <div className="empty-state" data-testid="empty-router-state">{data.routers.length === 0 ? "No routers in this workspace yet — add one to start." : "No routers match this filter."}</div>}</div></section>
          {active === "Overview" && <div className="footer-note"><span><Database size={14} />RouterOS API · persistent sessions per user</span><span>Signed in as <b>{user.email}</b></span></div>}
        </>}
      </section>
    </main>
    <AddRouterModal open={addOpen} editing={editing} canEditCreds={!editing || user.is_super_admin || editing.created_by === user.user_id} onClose={() => { setAddOpen(false); setEditing(null); }} groups={data.groups} onCreated={(updated) => { if (updated && selected?.id === updated.id) setSelected(s => ({ ...s, ...updated })); loadOverview(); }} onNotice={setNotice} />
    {groupSettings && <GroupSettings group={data.groups.find(g => g.id === groupSettings.id) || groupSettings} groups={data.groups} onClose={() => setGroupSettings(null)} onNotice={setNotice} onChanged={loadOverview} onOpenNotifications={() => { setGroupSettings(null); show("Settings"); }} onOpenRouter={(id) => { const r = data.routers.find(x => x.id === id); if (r) { setGroupSettings(null); openWorkspace(r); } }} />}
  </div>;
}

function Gate() {
  const { user } = useAuth();
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  if (user === null) return <div className="login-page"><div className="res-loading"><Loader2 size={16} className="spin" />Checking session…</div></div>;
  if (!user) return <Navigate to="/login" replace />;
  return <Shell />;
}

export default function App() {
  return <BrowserRouter><AuthProvider><Routes><Route path="/login" element={<Login />} /><Route path="/*" element={<Gate />} /></Routes></AuthProvider></BrowserRouter>;
}
