import { useEffect, useState } from "react";
import { LayoutDashboard, Loader2, Plus, Save, ScrollText, Settings2, Trash2 } from "lucide-react";
import { Modal } from "@/components/Modal";
import { api, errorText, slug } from "@/lib/api";
import { useAuth } from "@/auth/AuthContext";

export const WIDGET_LABELS = {
  metrics: "Summary metrics (devices, health, alarms)",
  traffic: "Live aggregate bandwidth chart",
  alarms: "Recent alarm feed",
  devices: "Device fleet table",
  syslog: "Latest syslog messages",
};
const BLANK = { name: "", widgets: ["metrics", "traffic", "alarms", "devices"], group_ids: [], device_ids: [], order: 0 };

function BoardModal({ open, onClose, editing, groups, devices, onSaved, onNotice }) {
  const [form, setForm] = useState(BLANK);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setForm(editing ? { ...BLANK, ...editing } : BLANK); }, [open, editing]);
  if (!open) return null;
  const toggle = (key, value) => setForm(f => ({ ...f, [key]: f[key].includes(value) ? f[key].filter(v => v !== value) : [...f[key], value] }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    const body = { name: form.name.trim(), widgets: form.widgets, group_ids: form.group_ids, device_ids: form.device_ids, order: Number(form.order) || 0 };
    try {
      if (editing) await api.put(`/dashboards/${editing.id}`, body); else await api.post("/dashboards", body);
      onNotice(`Board "${body.name}" saved`); onSaved(); onClose();
    } catch (err) { onNotice(errorText(err, "Save failed")); } finally { setBusy(false); }
  };
  return <Modal open onClose={onClose} title={editing ? "Edit board" : "New overview board"} eyebrow="CUSTOM DASHBOARD" hint="Pick the widgets and limit the board to certain groups or devices. Leave the scope empty to include everything in the workspace." testid="board-modal" wide>
    <form onSubmit={submit} className="add-form">
      <div className="two-col">
        <label>Board name<input required maxLength={40} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="Core routers" data-testid="board-name" /></label>
        <label>Tab order<input type="number" min={0} max={99} value={form.order} onChange={e => setForm(f => ({ ...f, order: e.target.value }))} data-testid="board-order" /></label>
      </div>
      <span className="pick-title">Widgets</span>
      <div className="watch-modes">
        {Object.entries(WIDGET_LABELS).map(([id, label]) => <label key={id} className={`watch-mode ${form.widgets.includes(id) ? "on" : ""}`} data-testid={`board-widget-${id}`}>
          <input type="checkbox" checked={form.widgets.includes(id)} onChange={() => toggle("widgets", id)} /><div><b>{id}</b><span className="muted">{label}</span></div></label>)}
      </div>
      <span className="pick-title">Limit to groups ({form.group_ids.length || "all"})</span>
      <div className="watch-list">
        {groups.map(g => <label key={g.id} className={`watch-item ${form.group_ids.includes(g.id) ? "on" : ""}`} data-testid={`board-group-${slug(g.name)}`}>
          <input type="checkbox" checked={form.group_ids.includes(g.id)} onChange={() => toggle("group_ids", g.id)} /><b>{g.path}</b></label>)}
      </div>
      <span className="pick-title">Or pick individual devices ({form.device_ids.length || "all"})</span>
      <div className="watch-list">
        {devices.map(d => <label key={d.id} className={`watch-item ${form.device_ids.includes(d.id) ? "on" : ""}`} data-testid={`board-device-${d.id}`}>
          <input type="checkbox" checked={form.device_ids.includes(d.id)} onChange={() => toggle("device_ids", d.id)} /><b>{d.name}</b><span className="muted">{d.group}</span></label>)}
      </div>
      <div className="modal-actions">
        <button type="button" className="button secondary" onClick={onClose} data-testid="board-cancel">Cancel</button>
        <button type="submit" className="button primary" disabled={busy} data-testid="board-submit">{busy ? <Loader2 size={14} className="spin" /> : <Save size={14} />}Save board</button>
      </div>
    </form>
  </Modal>;
}

export function SyslogWidget({ deviceIds }) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try { const r = await api.get("/syslog?limit=60"); if (alive) setRows(r.data.items || []); } catch { if (alive) setRows([]); }
    };
    load();
    const t = setInterval(load, 15000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  const list = (rows || []).filter(r => !deviceIds?.length || deviceIds.includes(r.router_id)).slice(0, 8);
  return <section className="panel" data-testid="syslog-widget">
    <div className="panel-head"><div><p className="eyebrow">SYSLOG STREAM · LAST 8</p><h2>Device logs</h2></div></div>
    <div className="alarm-list">
      {rows === null && <div className="res-loading"><Loader2 size={14} className="spin" />Loading…</div>}
      {rows !== null && list.length === 0 && <div className="drawer-message"><ScrollText size={16} />No syslog messages for this board yet.</div>}
      {list.map(r => <div key={r.id} className={`alarm-item ${r.severity <= 3 ? "danger" : r.severity <= 4 ? "warning" : "info"}`} data-testid={`syslog-widget-row-${r.id}`}>
        <div className="alarm-symbol"><ScrollText size={15} /></div>
        <div><b>{r.router_name} · {r.category}</b><span>{r.message.slice(0, 120)}</span><small>{new Date(r.created_at).toLocaleString()}</small></div>
      </div>)}
    </div>
  </section>;
}

export function DashboardTabs({ boards, activeId, onSelect, onChanged, groups, devices, onNotice }) {
  const { can } = useAuth();
  const [modal, setModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const writable = can("overview", "write");
  const remove = async (board) => {
    if (!window.confirm(`Remove board "${board.name}"?`)) return;
    try { await api.delete(`/dashboards/${board.id}`); onNotice(`Board "${board.name}" removed`); onChanged(); }
    catch (err) { onNotice(errorText(err, "Delete failed")); }
  };
  const current = boards.find(b => b.id === activeId);
  return <div className="board-tabs" data-testid="dashboard-tabs">
    {boards.map(b => <button key={b.id} className={b.id === activeId ? "active" : ""} onClick={() => onSelect(b.id)} data-testid={`board-tab-${slug(b.name)}`}><LayoutDashboard size={13} />{b.name}</button>)}
    {writable && <>
      <button className="board-add" onClick={() => { setEditing(null); setModal(true); }} data-testid="board-add"><Plus size={14} />New board</button>
      {current && <button className="board-add" onClick={() => { setEditing(current); setModal(true); }} data-testid="board-edit"><Settings2 size={14} />Customise</button>}
      {current && boards.length > 1 && <button className="board-add tg-del" onClick={() => remove(current)} data-testid="board-delete"><Trash2 size={14} /></button>}
    </>}
    <BoardModal open={modal} onClose={() => { setModal(false); setEditing(null); }} editing={editing} groups={groups} devices={devices} onSaved={onChanged} onNotice={onNotice} />
  </div>;
}
