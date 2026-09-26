import { useEffect, useState } from "react";
import { Loader2, Plus, RefreshCw, Save, ScrollText, Send, Trash2 } from "lucide-react";
import { Modal } from "@/components/Modal";
import { api, errorText, slug } from "@/lib/api";
import { useAuth } from "@/auth/AuthContext";

const BLANK_RULE = { name: "", category: "any", pattern: "", severity_max: 7, enabled: true, throttle_minutes: 15 };
const TONE = { "auth-failure": "danger", firewall: "warning", link: "warning", system: "info", dhcp: "info", ppp: "info", wireless: "info", "auth-success": "info", other: "info" };

function RuleModal({ open, onClose, editing, meta, onSaved, onNotice }) {
  const [form, setForm] = useState(BLANK_RULE);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setForm(editing ? { ...BLANK_RULE, ...editing } : BLANK_RULE); }, [open, editing]);
  if (!open) return null;
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    const body = { name: form.name.trim(), category: form.category, pattern: form.pattern.trim(), severity_max: Number(form.severity_max), enabled: form.enabled, throttle_minutes: Number(form.throttle_minutes) };
    try {
      if (editing) await api.put(`/syslog/rules/${editing.id}`, body); else await api.post("/syslog/rules", body);
      onNotice(`Syslog rule "${body.name}" saved`); onSaved(); onClose();
    } catch (err) { onNotice(errorText(err, "Save failed")); } finally { setBusy(false); }
  };
  return <Modal open onClose={onClose} title={editing ? "Edit syslog alarm rule" : "New syslog alarm rule"} eyebrow="SYSLOG → TELEGRAM" hint="Matching messages are delivered to the Telegram channel of every role that covers the sending device's group." testid="syslog-rule-modal">
    <form onSubmit={submit} className="add-form">
      <label>Rule name<input required minLength={2} value={form.name} onChange={e => set("name", e.target.value)} placeholder="SSH login failure" data-testid="rule-name" /></label>
      <div className="two-col">
        <label>Category<select value={form.category} onChange={e => set("category", e.target.value)} data-testid="rule-category"><option value="any">any category</option>{(meta.categories || []).map(c => <option key={c} value={c}>{c}</option>)}</select></label>
        <label>Max severity<select value={form.severity_max} onChange={e => set("severity_max", e.target.value)} data-testid="rule-severity">{(meta.severities || []).map((s, i) => <option key={s} value={i}>{`${i} · ${s} and worse`}</option>)}</select></label>
      </div>
      <label>Extra text / regex (optional)<input value={form.pattern} onChange={e => set("pattern", e.target.value)} placeholder="via ssh|winbox" data-testid="rule-pattern" /></label>
      <div className="two-col">
        <label>Re-notify after (minutes)<input type="number" min={1} max={1440} value={form.throttle_minutes} onChange={e => set("throttle_minutes", e.target.value)} data-testid="rule-throttle" /></label>
        <label className="tg-toggle"><input type="checkbox" checked={form.enabled} onChange={e => set("enabled", e.target.checked)} data-testid="rule-enabled" /><span>Rule active</span></label>
      </div>
      <div className="modal-actions">
        <button type="button" className="button secondary" onClick={onClose} data-testid="rule-cancel">Cancel</button>
        <button type="submit" className="button primary" disabled={busy} data-testid="rule-submit">{busy ? <Loader2 size={14} className="spin" /> : <Save size={14} />}Save rule</button>
      </div>
    </form>
  </Modal>;
}

export default function SyslogPage({ onNotice, devices, modalOpen, setModalOpen }) {
  const { can } = useAuth();
  const [status, setStatus] = useState(null);
  const [rows, setRows] = useState(null);
  const [counts, setCounts] = useState({});
  const [rules, setRules] = useState([]);
  const [meta, setMeta] = useState({});
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [device, setDevice] = useState("");
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState("");
  const writable = can("syslog", "write");

  const load = async () => {
    try {
      const params = new URLSearchParams({ limit: "200" });
      if (query) params.set("q", query);
      if (category) params.set("category", category);
      if (device) params.set("router_id", device);
      const [logs, st] = await Promise.all([api.get(`/syslog?${params}`), api.get("/syslog/status")]);
      setRows(logs.data.items || []); setCounts(logs.data.by_category || {}); setStatus(st.data);
    } catch (err) { onNotice(errorText(err, "Could not load syslog")); setRows([]); }
  };
  const loadRules = async () => { try { const r = await api.get("/syslog/rules"); setRules(r.data.items || []); setMeta({ categories: r.data.categories, severities: r.data.severities }); } catch { /* ignore */ } };
  useEffect(() => { load(); loadRules(); }, [query, category, device]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const t = setInterval(load, 12000); return () => clearInterval(t); }, [query, category, device]); // eslint-disable-line react-hooks/exhaustive-deps

  const inject = async () => {
    setBusy("test");
    try { const r = await api.post("/syslog/test-message"); onNotice(`Test message injected as ${r.data.source_ip}`); load(); }
    catch (err) { onNotice(errorText(err, "Inject failed")); } finally { setBusy(""); }
  };
  const removeRule = async (rule) => {
    try { await api.delete(`/syslog/rules/${rule.id}`); onNotice(`Rule "${rule.name}" removed`); loadRules(); }
    catch (err) { onNotice(errorText(err, "Delete failed")); }
  };
  const clearAll = async () => {
    if (!window.confirm("Delete every stored syslog message in this workspace?")) return;
    try { const r = await api.delete("/syslog"); onNotice(`${r.data.deleted} messages deleted`); load(); }
    catch (err) { onNotice(errorText(err, "Clear failed")); }
  };

  return <>
    <section className="panel" data-testid="syslog-view">
      <div className="panel-head table-head">
        <div><p className="eyebrow">SYSLOG COLLECTOR · {status?.listening ? `UDP ${status.port} LISTENING` : "NOT LISTENING"} · {status?.retention_days || 30}-DAY RETENTION</p><h2>Device log stream</h2></div>
        <div className="table-tools">
          <div className="search"><ScrollText size={15} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search message..." data-testid="syslog-search" /></div>
          <select value={category} onChange={e => setCategory(e.target.value)} data-testid="syslog-category-filter"><option value="">All categories</option>{(status?.categories || []).map(c => <option key={c} value={c}>{counts[c] ? `${c} (${counts[c]})` : c}</option>)}</select>
          <select value={device} onChange={e => setDevice(e.target.value)} data-testid="syslog-device-filter"><option value="">All devices</option>{(devices || []).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
          <button className="icon-btn" onClick={load} title="Reload" data-testid="syslog-reload"><RefreshCw size={15} /></button>
          {writable && <button className="button secondary compact" onClick={inject} disabled={busy === "test"} data-testid="syslog-inject"><Send size={13} />Inject test</button>}
          {writable && <button className="button secondary compact tg-del" onClick={clearAll} data-testid="syslog-clear"><Trash2 size={13} />Clear</button>}
        </div>
      </div>
      <p className="notif-help" data-testid="syslog-setup-hint">Point a device here with <code>/system logging action add name=netpulse target=remote remote={window.location.hostname} remote-port={status?.port || 514}</code> then <code>/system logging add topics=info,error,critical,warning action=netpulse</code>. {status?.listening ? "" : `Collector not bound: ${status?.error || "port unavailable"} — in the self-hosted Docker install port 514/udp is published.`}</p>
      {rows === null ? <div className="res-loading"><Loader2 size={14} className="spin" />Loading messages…</div>
        : <div className="table-wrap"><table><thead><tr><th>TIME</th><th>DEVICE</th><th>SEVERITY</th><th>CATEGORY</th><th>TOPICS</th><th>MESSAGE</th></tr></thead><tbody>
          {rows.length === 0 && <tr><td colSpan={6} className="res-empty">No syslog messages stored yet — configure a device to send logs here, or use “Inject test”.</td></tr>}
          {rows.map((r, i) => <tr key={r.id} data-testid={`syslog-row-${i}`}>
            <td className="muted mono">{new Date(r.created_at).toLocaleString()}</td>
            <td><b>{r.router_name}</b><span className="muted mono"> {r.source_ip}</span></td>
            <td><span className={`tg-pill ${r.severity <= 3 ? "off" : "on"}`}>{r.severity_name}</span></td>
            <td><span className={`alarm-chip ${TONE[r.category] || "info"}`}>{r.category}</span></td>
            <td className="mono muted">{r.tag || "—"}</td>
            <td className="syslog-msg">{r.message}</td>
          </tr>)}
        </tbody></table></div>}
    </section>
    <section className="panel" data-testid="syslog-rules">
      <div className="panel-head table-head"><div><p className="eyebrow">ALARM RULES / {rules.length} ACTIVE PATTERNS</p><h2>Syslog alarms → Telegram</h2></div>
        {writable && <button className="button primary compact" onClick={() => { setEditing(null); setModalOpen(true); }} data-testid="syslog-add-rule"><Plus size={14} />Add rule</button>}</div>
      <div className="table-wrap"><table><thead><tr><th>RULE</th><th>CATEGORY</th><th>PATTERN</th><th>MAX SEVERITY</th><th>THROTTLE</th><th>STATE</th><th></th></tr></thead><tbody>
        {rules.length === 0 && <tr><td colSpan={7} className="res-empty">No rules yet — add one to get a Telegram message when a matching log arrives.</td></tr>}
        {rules.map(r => <tr key={r.id} data-testid={`syslog-rule-${slug(r.name)}`}>
          <td><b>{r.name}</b></td><td><span className="group-label">{r.category}</span></td><td className="mono muted">{r.pattern || "—"}</td>
          <td className="muted">{r.severity_max} · {(meta.severities || [])[r.severity_max]}</td><td className="muted">{r.throttle_minutes}m</td>
          <td>{r.enabled ? <span className="tg-pill on">active</span> : <span className="tg-pill off">paused</span>}</td>
          <td><div className="row-actions">{writable && <><button className="icon-btn" title="Edit" onClick={() => { setEditing(r); setModalOpen(true); }} data-testid={`syslog-rule-edit-${slug(r.name)}`}><Save size={14} /></button>
            <button className="icon-btn tg-del" title="Remove" onClick={() => removeRule(r)} data-testid={`syslog-rule-delete-${slug(r.name)}`}><Trash2 size={14} /></button></>}</div></td>
        </tr>)}
      </tbody></table></div>
    </section>
    <RuleModal open={modalOpen} onClose={() => { setModalOpen(false); setEditing(null); }} editing={editing} meta={meta} onSaved={loadRules} onNotice={onNotice} />
  </>;
}
