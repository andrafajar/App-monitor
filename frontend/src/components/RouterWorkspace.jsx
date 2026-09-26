import { useEffect, useState } from "react";
import { ChevronLeft, ExternalLink, Eye, EyeOff, LineChart, Loader2, MonitorUp, Pencil, Plus, Power, RefreshCw, Router, Settings2, Trash2 } from "lucide-react";
import { api, errorText } from "@/lib/api";
import { EDITABLE_FIELDS, PANEL_TABS, RESOURCE_COLUMNS, RESOURCE_KEY, SENSITIVE_TABS, SINGLE_OBJECT, WINBOX_MENU } from "@/lib/ros";
import { ConfigEditor, ConfirmRemove, PermissionPopup } from "@/components/ConfigEditor";
import { Status } from "@/components/Status";
const rid = (row) => row?.[".id"] || row?.id;
const slugify = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
import { BackupsPanel } from "@/components/BackupsPanel";
import { TerminalPanel } from "@/components/TerminalPanel";
import { TrafficPanel } from "@/components/TrafficPanel";
import { SshTerminal } from "@/components/SshTerminal";
import { SnmpPanel } from "@/components/SnmpPanel";
import { InterfaceGraphs } from "@/components/InterfaceGraphs";
import { AlarmWatchPanel } from "@/components/AlarmWatchPanel";

const VENDOR_LABEL = { mikrotik: "MikroTik", huawei: "Huawei", juniper: "Juniper", cisco: "Cisco", other: "Other vendor" };
// Non-MikroTik vendors are monitored (ping + SNMP) and reached over SSH/Telnet; RouterOS menus stay MikroTik-only.
const GENERIC_MENU = [{ section: "MONITORING", items: ["SNMP", "Interface Graphs", "Alarm Watch"] }, { section: "ACCESS", items: ["Terminal (SSH)", "Terminal (Telnet)"] }];

export function ResourceTable({ tab, routerId, revealSecret, onRevealToggle, onNotice, onGoSettings, reloadKey }) {
  const resourceKey = RESOURCE_KEY[tab];
  const columns = RESOURCE_COLUMNS[tab] || [];
  const [state, setState] = useState({ loading: true, error: "", items: [], writable: [] });
  const [editor, setEditor] = useState(null); // {row} or {row:null} for add
  const [removing, setRemoving] = useState(null);
  const [permErr, setPermErr] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!resourceKey || !routerId) return;
    const controller = new AbortController();
    setState(s => ({ ...s, loading: true, error: "" }));
    const params = SENSITIVE_TABS.has(tab) && revealSecret ? "?reveal=true" : "";
    api.get(`/routers/${routerId}/resources/${resourceKey}${params}`, { signal: controller.signal })
      .then(r => setState({ loading: false, error: "", items: r.data?.items || [], writable: r.data?.writable || [] }))
      .catch(err => {
        if (err.name === "CanceledError") return;
        if (err.response?.status === 428) setPermErr(err);
        setState({ loading: false, error: errorText(err, "RouterOS API is unreachable. Verify credentials, port, and allow-list."), items: [], writable: [] });
      });
    return () => controller.abort();
  }, [resourceKey, routerId, revealSecret, tick, reloadKey]);

  const done = (msg) => { onNotice(msg); setTick(t => t + 1); };
  const fail = (err) => { setPermErr(err); };
  const canAdd = state.writable.includes("add") && EDITABLE_FIELDS[tab];
  const canSet = state.writable.includes("set") && EDITABLE_FIELDS[tab];
  const canRemove = state.writable.includes("remove");

  if (state.loading) return <div className="res-loading" data-testid={`${resourceKey}-loading`}><Loader2 size={14} className="spin" />Loading {tab.toLowerCase()} from RouterOS API…</div>;
  if (state.error) return <><div className="res-error" data-testid={`${resourceKey}-error`}>{state.error}</div><PermissionPopup error={permErr} onClose={() => setPermErr(null)} onGoSettings={onGoSettings} /></>;

  const modals = <>
    <ConfigEditor open={!!editor} onClose={() => setEditor(null)} tab={tab} routerId={routerId} row={editor?.row || null} onDone={done} onError={fail} />
    <ConfirmRemove open={!!removing} onClose={() => setRemoving(null)} tab={tab} routerId={routerId} row={removing} onDone={done} onError={fail} />
    <PermissionPopup error={permErr} onClose={() => setPermErr(null)} onGoSettings={onGoSettings} />
  </>;

  if (SINGLE_OBJECT.has(tab)) {
    const c = state.items?.[0] || {};
    return <>
      <div className="res-toolbar"><b>{tab}</b>{canSet && <button className="button secondary compact" onClick={() => setEditor({ row: c })} data-testid={`${resourceKey}-edit`}><Pencil size={13} />Edit</button>}</div>
      <div className="clock-grid" data-testid={`${resourceKey}-panel`}>
        {columns.map(col => <div key={col}><span>{col.replaceAll("-", " ")}</span><b data-testid={`clock-${col}`}>{c[col] ?? "—"}</b></div>)}
      </div>
      {modals}
    </>;
  }

  return <>
    <div className="res-toolbar">
      <b data-testid={`${resourceKey}-count`}>{state.items.length} {tab.toLowerCase()}</b>
      <div className="res-tools">
        {SENSITIVE_TABS.has(tab) && <button className={`reveal-btn ${revealSecret ? "on" : ""}`} onClick={onRevealToggle} data-testid={`${resourceKey}-reveal-toggle`}>{revealSecret ? <><EyeOff size={13} />Hide passwords</> : <><Eye size={13} />Reveal passwords</>}</button>}
        <button className="icon-btn" onClick={() => setTick(t => t + 1)} title="Reload" data-testid={`${resourceKey}-reload`}><RefreshCw size={14} /></button>
        {canAdd && <button className="button primary compact" onClick={() => setEditor({ row: null })} data-testid={`${resourceKey}-add`}><Plus size={13} />Add</button>}
      </div>
    </div>
    <div className="res-table" data-testid={`${resourceKey}-table`}>
      <table><thead><tr>{columns.map(c => <th key={c}>{c.replaceAll("-", " ").toUpperCase()}</th>)}{(canSet || canRemove) && <th className="th-actions"></th>}</tr></thead>
      <tbody>
        {state.items.length === 0 && <tr><td colSpan={columns.length + 1} className="res-empty">No entries returned by RouterOS.</td></tr>}
        {state.items.map((row, i) => <tr key={rid(row) || i} data-testid={`${resourceKey}-row-${i}`} className={row.disabled === "true" ? "row-disabled" : ""}>
          {columns.map(c => <td key={c}>{row[c] ?? "—"}</td>)}
          {(canSet || canRemove) && <td className="td-actions"><div className="row-actions">
            {canSet && rid(row) && <button className="icon-btn" title="Edit" onClick={() => setEditor({ row })} data-testid={`${resourceKey}-edit-${i}`}><Pencil size={14} /></button>}
            {canRemove && rid(row) && row.dynamic !== "true" && <button className="icon-btn tg-del" title="Remove" onClick={() => setRemoving(row)} data-testid={`${resourceKey}-remove-${i}`}><Trash2 size={14} /></button>}
          </div></td>}
        </tr>)}
      </tbody></table>
    </div>
    {modals}
  </>;
}

export function WorkspacePage({ router, onBack, onNotice, onRefresh, onRemove, onEdit, onGoSettings, canWriteRouters, initialCat }) {
  const vendor = router.device_type || "mikrotik";
  const isRos = vendor === "mikrotik";
  const menu = isRos ? [...WINBOX_MENU, { section: "MONITORING", items: ["SNMP", "Interface Graphs"] }] : GENERIC_MENU;
  const [cat, setCat] = useState(initialCat && (RESOURCE_KEY[initialCat] || PANEL_TABS.includes(initialCat) || initialCat === "Interface Graphs") ? initialCat : "Interface Graphs");
  const [revealSecret, setRevealSecret] = useState(false);
  const [conn, setConn] = useState({ connected: false, connected_at: 0 });
  const [busy, setBusy] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  useEffect(() => { if (!SENSITIVE_TABS.has(cat)) setRevealSecret(false); }, [cat]);

  const loadConn = async () => { try { const r = await api.get(`/routers/${router.id}/connection`); setConn(r.data || { connected: false }); } catch { setConn({ connected: false }); } };
  useEffect(() => { loadConn(); const t = setInterval(loadConn, 15000); return () => clearInterval(t); }, [router.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const test = async () => {
    setBusy("test"); onNotice(`Testing connection to ${router.name}…`);
    try {
      const r = await api.post(`/routers/${router.id}/test-connection`);
      onNotice(r.data?.status === "online" ? `${router.name} · CPU ${r.data?.cpu ?? 0}% · uptime ${r.data?.uptime || "—"}` : `${router.name} is unreachable: ${r.data?.error || "connection refused"}`);
      onRefresh(); loadConn();
    } catch (e) { onNotice(errorText(e, "Connection test failed")); }
    finally { setBusy(""); }
  };
  const disconnect = async () => {
    setBusy("disc");
    try { await api.post(`/routers/${router.id}/disconnect`); onNotice(`${router.name}: session closed`); loadConn(); }
    catch (e) { onNotice("Disconnect failed"); }
    finally { setBusy(""); }
  };
  const reconnect = async () => { setBusy("re"); setReloadKey(k => k + 1); setTimeout(() => { loadConn(); setBusy(""); }, 1200); };
  const openTab = () => window.open(`${window.location.origin}/?router=${router.id}&cat=${encodeURIComponent(cat)}`, "_blank", "noopener");
  const openConsole = () => window.open(`${window.location.origin}/console/${router.id}?cat=${encodeURIComponent(cat)}`, `netpulse-console-${router.id}`,
    "popup=yes,noopener,width=1400,height=900,left=120,top=60,toolbar=no,menubar=no,location=no,status=no");
  const connLabel = conn.connected ? `Session up · ${Math.max(0, Math.round((Date.now() / 1000 - conn.connected_at) / 60))}m` : "No session";

  return <section className="workspace-page" data-testid={`workspace-${router.id}`}>
    <header className="ws-topbar">
      <div className="ws-title">
        {onBack && <button className="icon-btn" onClick={onBack} data-testid="ws-back-button"><ChevronLeft size={18} /></button>}
        <div className={`router-icon ${router.color || "cyan"}`}><Router size={17} /></div>
        <div className="ws-title-text">
          <b data-testid="ws-router-name">{router.name}</b>
          <span className="mono" data-testid="ws-router-meta">{router.host} · {VENDOR_LABEL[vendor] || vendor}{isRos ? ` · api ${router.port || 8728} · ROS ${router.version || "—"}` : ` · ${router.snmp_enabled ? "SNMP v2c" : "ping only"}${router.ping_ms ? ` · ${router.ping_ms}ms` : ""}`}{router.description ? ` · ${router.description}` : ""}</span>
        </div>
        <Status value={router.status} />
      </div>
      <div className="ws-conn"><span className={`ws-dot ${conn.connected ? "on" : "off"}`} />{connLabel}</div>
      <div className="ws-actions">
        {cat === "Interface Graphs"
          ? <button className="button primary compact" onClick={() => setCat(isRos ? "Interfaces" : "SNMP")} data-testid="ws-manage">{isRos ? <><Settings2 size={13} />Manage (RouterOS)</> : <><Settings2 size={13} />Manage SNMP</>}</button>
          : <button className="button secondary compact" onClick={() => setCat("Interface Graphs")} data-testid="ws-graphs"><LineChart size={13} />Graphs</button>}
        <button className="button secondary compact" onClick={test} disabled={busy === "test"} data-testid="ws-test-connection"><RefreshCw size={13} className={busy === "test" ? "spin" : ""} />Test</button>
        {conn.connected
          ? <button className="button secondary compact" onClick={disconnect} disabled={busy === "disc"} data-testid="ws-disconnect"><Power size={13} />Disconnect</button>
          : <button className="button secondary compact" onClick={reconnect} disabled={busy === "re"} data-testid="ws-reconnect"><Power size={13} />Reconnect</button>}
        {onBack && <button className="button secondary compact" onClick={openConsole} title="Open this device in its own window" data-testid="ws-open-console"><MonitorUp size={13} />Console window</button>}
        <button className="button secondary compact" onClick={openTab} data-testid="ws-open-new-tab"><ExternalLink size={13} />New tab</button>
        {canWriteRouters && onEdit && <button className="button secondary compact" onClick={() => onEdit(router)} data-testid="ws-edit-router"><Pencil size={13} />Edit</button>}
        {canWriteRouters && onRemove && <button className="button secondary compact tg-del" onClick={() => onRemove(router.id, router.name)} data-testid="ws-remove-router"><Trash2 size={13} />Remove</button>}
      </div>
    </header>
    <div className="ws-body">
      <aside className="ws-menu" data-testid="ws-menu">
        {menu.map(section => <div key={section.section} className="ws-menu-section">
          <span className="ws-menu-title">{section.section}</span>
          {section.items.map(item => <button key={item} className={cat === item ? "active" : ""} onClick={() => setCat(item)} data-testid={`ws-menu-${RESOURCE_KEY[item] || slugify(item)}`}>{item.replace(/^(PPP|System|Hotspot) /, "")}</button>)}
        </div>)}
      </aside>
      <div className="ws-main" data-testid="ws-main">
        <div className="ws-cat-head"><p className="eyebrow">{cat === "SNMP" ? "SNMP V2C · PING & INTERFACE POLLING" : cat === "Interface Graphs" ? "SNMP HISTORY · 30 DAYS" : cat === "Backups" ? "OBJECT STORAGE · SNAPSHOTS & SCHEDULE" : cat === "Terminal (API)" ? "ROUTEROS API · COMMAND BRIDGE" : cat === "Terminal (SSH)" ? "ROUTEROS SHELL · SSH" : cat === "Terminal (Telnet)" ? "ROUTEROS SHELL · TELNET" : cat === "Traffic" ? "ROUTEROS API · LIVE BANDWIDTH" : "ROUTEROS API"} · {cat.toUpperCase()}</p><h2 data-testid="ws-cat-title">{cat}</h2></div>
        {cat === "SNMP" ? <SnmpPanel deviceId={router.id} deviceName={router.name} onNotice={onNotice} />
          : cat === "Interface Graphs" ? <InterfaceGraphs deviceId={router.id} deviceType={vendor} onNotice={onNotice} />
          : cat === "Backups" ? <BackupsPanel routerId={router.id} onNotice={onNotice} onGoSettings={onGoSettings} />
          : cat === "Traffic" ? <TrafficPanel routerId={router.id} onGoSettings={onGoSettings} />
          : cat === "Terminal (SSH)" ? <SshTerminal routerId={router.id} routerName={router.name} proto="ssh" port={router.ssh_port} />
          : cat === "Terminal (Telnet)" ? <SshTerminal routerId={router.id} routerName={router.name} proto="telnet" port={router.telnet_port} />
          : cat === "Alarm Watch" ? <AlarmWatchPanel routerId={router.id} routerName={router.name} onNotice={onNotice} />
          : cat === "Terminal (API)" ? <TerminalPanel routerId={router.id} routerName={router.name} onGoSettings={onGoSettings} />
          : <ResourceTable key={`${router.id}-${cat}`} tab={cat} routerId={router.id} revealSecret={revealSecret} onRevealToggle={() => setRevealSecret(v => !v)} onNotice={onNotice} onGoSettings={onGoSettings} reloadKey={reloadKey} />}
      </div>
    </div>
  </section>;
}
