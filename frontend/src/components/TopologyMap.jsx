import { useCallback, useEffect, useRef, useState } from "react";
import { Link2, LineChart, Loader2, MonitorUp, Pencil, Plus, RefreshCw, Router, Settings2, Terminal as TerminalIcon, Trash2, X } from "lucide-react";
import { api, errorText } from "@/lib/api";
import { Modal } from "@/components/Modal";

const NODE_W = 150, NODE_H = 58;
const center = (n) => ({ x: n.x + NODE_W / 2, y: n.y + NODE_H / 2 });
const rate = (l) => (l.rx_mbps || l.tx_mbps ? `${(l.rx_mbps || 0).toFixed(1)}↓ / ${(l.tx_mbps || 0).toFixed(1)}↑ Mbps` : "");

function LinkModal({ open, onClose, devices, editing, onDone, onNotice }) {
  const [form, setForm] = useState({ a_device: "", a_iface: "", b_device: "", b_iface: "", label: "" });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    setForm(editing ? { a_device: editing.a_device, a_iface: editing.a_iface, b_device: editing.b_device, b_iface: editing.b_iface, label: editing.label || "" }
      : { a_device: "", a_iface: "", b_device: "", b_iface: "", label: "" });
  }, [open, editing]);
  if (!open) return null;
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const ifacesOf = (id) => devices.find(d => d.device_id === id)?.interfaces || [];
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      if (editing) await api.put(`/topology/links/${editing.id}`, form); else await api.post("/topology/links", form);
      onNotice(editing ? "Link updated" : "Link added to the map"); onDone(); onClose();
    } catch (err) { onNotice(errorText(err, "Could not save the link")); }
    finally { setBusy(false); }
  };
  const side = (key) => <>
    <label>{key === "a" ? "Device A" : "Device B"}<select required value={form[`${key}_device`]} onChange={e => { set(`${key}_device`, e.target.value); set(`${key}_iface`, ""); }} data-testid={`link-${key}-device`}>
      <option value="">— select device —</option>
      {devices.map(d => <option key={d.device_id} value={d.device_id}>{d.interfaces.length ? d.name : `${d.name} (no SNMP scan)`}</option>)}
    </select></label>
    <label>Interface<select required value={form[`${key}_iface`]} onChange={e => set(`${key}_iface`, e.target.value)} disabled={!form[`${key}_device`]} data-testid={`link-${key}-iface`}>
      <option value="">— select interface —</option>
      {ifacesOf(form[`${key}_device`]).map(i => <option key={i.name} value={i.name}>{`${i.name} · ${i.status}`}</option>)}
    </select></label>
  </>;
  return <Modal open={open} onClose={onClose} title={editing ? "Edit link" : "Connect two interfaces"} eyebrow={editing ? `TOPOLOGY · ${editing.id}` : "TOPOLOGY · MANUAL LINK"} hint="Endpoints come from the last SNMP sweep of each device — run “Scan now” in the device SNMP tab if a list is empty." testid="topology-link-modal">
    <form onSubmit={submit} className="add-form">
      <div className="two-col">{side("a")}</div>
      <div className="two-col">{side("b")}</div>
      <label>Label (optional)<input maxLength={60} value={form.label} onChange={e => set("label", e.target.value)} placeholder="Metro-E 1 Gbps" data-testid="link-label" /></label>
      <div className="modal-actions">
        <button type="button" className="button secondary" onClick={onClose} data-testid="link-cancel">Cancel</button>
        <button type="submit" className="button primary" disabled={busy} data-testid="link-submit"><Link2 size={14} />{busy ? "Saving…" : editing ? "Save link" : "Add link"}</button>
      </div>
    </form>
  </Modal>;
}

export function TopologyMap({ data, readOnly = false, onNotice, canEdit = false, onOpenDevice }) {
  const [map, setMap] = useState(data || null);
  const [picker, setPicker] = useState(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [editingLink, setEditingLink] = useState(null);
  const [drag, setDrag] = useState(null);
  const [menu, setMenu] = useState(null);
  const canvas = useRef(null);

  const load = useCallback(async () => {
    if (readOnly) return;
    try { const r = await api.get("/topology"); setMap(r.data); } catch (e) { onNotice?.(errorText(e, "Could not load the topology")); }
  }, [readOnly, onNotice]);
  useEffect(() => { if (data) setMap(data); }, [data]);
  useEffect(() => { if (!readOnly) { load(); const t = setInterval(load, 30000); return () => clearInterval(t); } }, [load, readOnly]);
  useEffect(() => { if (!readOnly && linkOpen) api.get("/topology/interfaces").then(r => setPicker(r.data.items || [])).catch(() => setPicker([])); }, [linkOpen, readOnly]);

  const onPointerDown = (node) => (e) => {
    if (readOnly) return;
    const box = canvas.current.getBoundingClientRect();
    setMenu(null);
    setDrag({ id: node.device_id, dx: e.clientX - box.left - node.x, dy: e.clientY - box.top - node.y, moved: false, sx: e.clientX, sy: e.clientY });
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e) => {
    if (!drag) return;
    if (!drag.moved && Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy) < 4) return;
    if (!drag.moved) setDrag(d => ({ ...d, moved: true }));
    if (!canEdit) return;
    const box = canvas.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(box.width - NODE_W, e.clientX - box.left - drag.dx));
    const y = Math.max(0, Math.min(2000, e.clientY - box.top - drag.dy));
    setMap(m => ({ ...m, nodes: m.nodes.map(n => (n.device_id === drag.id ? { ...n, x, y } : n)) }));
  };
  const onPointerUp = async () => {
    if (!drag) return;
    const node = map.nodes.find(n => n.device_id === drag.id);
    const dragged = drag.moved && canEdit;
    setDrag(null);
    if (!drag.moved) { setMenu(node); return; }   // a plain click opens the device actions popup
    if (!dragged) return;
    try { await api.put(`/topology/nodes/${node.device_id}`, { x: Math.round(node.x), y: Math.round(node.y) }); }
    catch (e) { onNotice?.(errorText(e, "Could not save the position")); }
  };
  const removeLink = async (id) => {
    if (!window.confirm("Remove this link from the map?")) return;
    try { await api.delete(`/topology/links/${id}`); onNotice?.("Link removed"); load(); } catch (e) { onNotice?.(errorText(e, "Delete failed")); }
  };

  if (!map) return <div className="res-loading"><Loader2 size={14} className="spin" />Building the topology…</div>;
  const nodeById = Object.fromEntries(map.nodes.map(n => [n.device_id, n]));
  const pairIndex = {};   // several links between the same two devices are drawn side by side instead of on top of each other
  const pairTotal = {};
  map.links.forEach(l => {
    const key = [l.a_device, l.b_device].sort().join("|");
    pairIndex[l.id] = pairTotal[key] = (pairTotal[key] ?? -1) + 1;
  });
  const offsetOf = (l) => {
    const key = [l.a_device, l.b_device].sort().join("|");
    return (pairIndex[l.id] - pairTotal[key] / 2) * 22;
  };
  const height = Math.max(420, ...map.nodes.map(n => n.y + NODE_H + 60));

  const Root = readOnly ? "div" : "section";
  return <Root className={readOnly ? "topo-readonly" : "panel topo-panel"} data-testid="topology-map">
    {!readOnly && <div className="panel-head"><div><p className="eyebrow">TOPOLOGY · {map.links.length} LINKS · DRAG TO ARRANGE</p><h2>Network map</h2></div>      <div className="res-tools">
        <button className="icon-btn" onClick={load} title="Reload" data-testid="topology-reload"><RefreshCw size={15} /></button>
        {canEdit && <button className="button primary compact" onClick={() => { setEditingLink(null); setLinkOpen(true); }} data-testid="topology-add-link"><Plus size={13} />Add link</button>}
      </div></div>}
    <div className="topo-canvas" ref={canvas} style={{ height }} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerLeave={onPointerUp} data-testid="topology-canvas">
      <svg className="topo-links" width="100%" height={height}>
        {map.links.map(l => {
          const a = nodeById[l.a_device], b = nodeById[l.b_device];
          if (!a || !b) return null;
          const c1 = center(a), c2 = center(b);
          const span = Math.hypot(c2.x - c1.x, c2.y - c1.y) || 1;
          const shift = offsetOf(l);
          const nx = -((c2.y - c1.y) / span) * shift, ny = ((c2.x - c1.x) / span) * shift;
          const p1 = { x: c1.x + nx, y: c1.y + ny }, p2 = { x: c2.x + nx, y: c2.y + ny };
          return <g key={l.id} className={`topo-link ${l.status}`} onClick={() => { if (!readOnly && canEdit) { setEditingLink(l); setLinkOpen(true); } }} style={{ pointerEvents: readOnly || !canEdit ? "none" : "stroke" }} data-testid={`topo-edge-${l.id}`}>
            <line x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} />
            <text x={(p1.x + p2.x) / 2} y={(p1.y + p2.y) / 2 - 8} textAnchor="middle">{l.label || `${l.a_iface} ↔ ${l.b_iface}`}</text>
            <text x={(p1.x + p2.x) / 2} y={(p1.y + p2.y) / 2 + 12} textAnchor="middle" className="topo-rate">{rate(l)}</text>
          </g>;
        })}
      </svg>
      {map.nodes.map(n => <div key={n.device_id} className={`topo-node ${n.status} ${menu?.device_id === n.device_id ? "picked" : ""}`} style={{ left: n.x, top: n.y, width: NODE_W }} onPointerDown={onPointerDown(n)} data-testid={`topo-node-${n.device_id}`}>
        <div className="topo-node-head"><Router size={14} /><b>{n.name}</b></div>
        <span>{n.device_type} · {n.status}{n.ping_ms ? ` · ${n.ping_ms}ms` : ""}</span>
      </div>)}
      {menu && <div className="topo-menu" style={{ left: Math.min(menu.x + NODE_W + 12, 1100), top: menu.y }} data-testid={`topo-menu-${menu.device_id}`}>
        <div className="topo-menu-head"><b>{menu.name}</b><button className="icon-btn" onClick={() => setMenu(null)} data-testid="topo-menu-close"><X size={12} /></button></div>
        <button onClick={() => { onOpenDevice?.(menu.device_id, "Interface Graphs"); setMenu(null); }} data-testid="topo-menu-graphs"><LineChart size={13} />Graphs &amp; history</button>
        <button onClick={() => { onOpenDevice?.(menu.device_id, menu.device_type === "mikrotik" ? "Interfaces" : "SNMP"); setMenu(null); }} data-testid="topo-menu-manage"><Settings2 size={13} />{menu.device_type === "mikrotik" ? "Manage (RouterOS)" : "Manage SNMP"}</button>
        <button onClick={() => { onOpenDevice?.(menu.device_id, "Terminal (SSH)"); setMenu(null); }} data-testid="topo-menu-terminal"><TerminalIcon size={13} />Terminal (SSH)</button>
        <button onClick={() => { window.open(`${window.location.origin}/console/${menu.device_id}`, `netpulse-console-${menu.device_id}`, "popup=yes,noopener,width=1400,height=900"); setMenu(null); }} data-testid="topo-menu-console"><MonitorUp size={13} />Console window</button>
      </div>}
    </div>
    {!readOnly && <div className="topo-legend">
      {map.links.length === 0 && <span className="muted">No links yet — press “Add link” and pick an SNMP-scanned interface on both devices.</span>}
      {map.links.map(l => <span key={l.id} className={`tg-pill ${l.status === "up" ? "on" : "off"}`} data-testid={`topo-link-${l.id}`}>
        {nodeById[l.a_device]?.name} {l.a_iface} ↔ {nodeById[l.b_device]?.name} {l.b_iface}{l.label ? ` · ${l.label}` : ""}
        {canEdit && <button className="icon-btn" onClick={() => { setEditingLink(l); setLinkOpen(true); }} title="Edit link" data-testid={`topo-link-edit-${l.id}`}><Pencil size={12} /></button>}
        {canEdit && <button className="icon-btn" onClick={() => removeLink(l.id)} title="Remove link" data-testid={`topo-link-remove-${l.id}`}><Trash2 size={12} /></button>}
      </span>)}
    </div>}
    {!readOnly && <LinkModal open={linkOpen} onClose={() => { setLinkOpen(false); setEditingLink(null); }} devices={picker || []} editing={editingLink} onDone={load} onNotice={onNotice} />}
  </Root>;
}
