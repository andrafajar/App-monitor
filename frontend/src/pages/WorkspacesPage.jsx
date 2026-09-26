import { useEffect, useState } from "react";
import { Building2, Check, Copy, Monitor, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { Modal } from "@/components/Modal";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/auth/AuthContext";

function PublicDisplay({ wsId, onNotice }) {
  const [cfg, setCfg] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = async () => { try { const r = await api.get(`/workspaces/${wsId}/public-display`); setCfg(r.data.display); } catch { setCfg({ enabled: false }); } };
  useEffect(() => { load(); }, [wsId]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = async (patch) => {
    setBusy(true);
    try { const r = await api.put(`/workspaces/${wsId}/public-display`, { enabled: cfg?.enabled ?? false, show_ips: cfg?.show_ips ?? false, title: cfg?.title || "", rotate: false, ...patch }); setCfg(r.data.display); onNotice(patch.rotate ? "Display link rotated" : "Display settings saved"); }
    catch (err) { onNotice(errorText(err, "Save failed")); } finally { setBusy(false); }
  };
  if (!cfg) return null;
  const url = cfg.path ? `${window.location.origin}${cfg.path}` : "";
  return <div className="tg-row" data-testid={`public-display-${wsId}`}>
    <div className="tg-head"><div><Monitor size={14} /><b>Public NOC display (no login)</b></div>
      <div className="tg-status">{cfg.enabled ? <span className="tg-pill on" data-testid={`display-state-${wsId}`}>Published</span> : <span className="tg-pill off" data-testid={`display-state-${wsId}`}>Disabled</span>}</div></div>
    <div className="tg-fields">
      <label className="tg-toggle"><input type="checkbox" checked={cfg.enabled} onChange={e => save({ enabled: e.target.checked })} disabled={busy} data-testid={`display-enable-${wsId}`} /><span>Publish read-only board</span></label>
      <label className="tg-toggle"><input type="checkbox" checked={cfg.show_ips} onChange={e => save({ show_ips: e.target.checked })} disabled={busy} data-testid={`display-showips-${wsId}`} /><span>Show device IP addresses</span></label>
      <label>Board title<input value={cfg.title || ""} onChange={e => setCfg(c => ({ ...c, title: e.target.value }))} onBlur={() => save({ title: cfg.title || "" })} placeholder="NOC – Central Operations" data-testid={`display-title-${wsId}`} /></label>
    </div>
    {cfg.path && <div className="tg-actions">
      <code className="mono" data-testid={`display-url-${wsId}`}>{url}</code>
      <button className="button secondary compact" onClick={() => { navigator.clipboard?.writeText(url); onNotice("Display link copied"); }} data-testid={`display-copy-${wsId}`}><Copy size={13} />Copy link</button>
      <a className="button secondary compact" href={cfg.path} target="_blank" rel="noreferrer" data-testid={`display-open-${wsId}`}><Monitor size={13} />Open board</a>
      <button className="tg-del" onClick={() => save({ rotate: true })} disabled={busy} data-testid={`display-rotate-${wsId}`}><RefreshCw size={13} />Rotate link</button>
    </div>}
  </div>;
}

export default function WorkspacesPage({ onNotice, onChanged }) {
  const { can, workspaceId, setWorkspaceId, refresh } = useAuth();
  const [items, setItems] = useState([]);
  const [modal, setModal] = useState(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const load = async () => { try { const r = await api.get("/workspaces"); setItems(r.data.items || []); } catch (err) { onNotice(errorText(err)); } };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const open = (w) => { setModal(w || {}); setName(w?.name || ""); };
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      if (modal?.id) await api.put(`/workspaces/${modal.id}`, { name: name.trim() }); else await api.post("/workspaces", { name: name.trim() });
      onNotice(modal?.id ? "Workspace renamed" : `Workspace "${name.trim()}" created`); setModal(null); await refresh(); load(); onChanged?.();
    } catch (err) { onNotice(errorText(err, "Save failed")); }
    finally { setBusy(false); }
  };
  const remove = async (w) => {
    if (!window.confirm(`Remove workspace ${w.name}? Groups inside will be deleted.`)) return;
    try { await api.delete(`/workspaces/${w.id}`); onNotice(`${w.name} removed`); if (workspaceId === w.id) setWorkspaceId("ws-default"); await refresh(); load(); onChanged?.(); }
    catch (err) { onNotice(errorText(err)); }
  };
  return <section className="panel routers-panel" data-testid="workspaces-view">
    <div className="panel-head table-head"><div><p className="eyebrow">TENANCY / {items.length} WORKSPACES</p><h2>Workspaces</h2></div>
      {can("workspaces", "write") && <button className="button primary compact" onClick={() => open(null)} data-testid="add-workspace-button"><Plus size={14} />New workspace</button>}</div>
    <p className="notif-help">Each workspace is an isolated tenant with its own device groups and routers. Switch the active workspace from the sidebar selector.</p>
    <div className="table-wrap"><table><thead><tr><th>WORKSPACE</th><th>ROUTERS</th><th>ACTIVE</th><th></th></tr></thead><tbody>
      {items.map(w => <tr key={w.id} data-testid={`workspace-row-${w.id}`}>
        <td><div className="router-name"><div className="router-icon violet"><Building2 size={15} /></div><div><b>{w.name}</b><span className="mono">{w.id}</span></div></div></td>
        <td className="mono">{w.router_count}</td>
        <td>{workspaceId === w.id ? <span className="tg-pill on"><Check size={12} />current</span> : <button className="text-btn" onClick={() => { setWorkspaceId(w.id); onChanged?.(); onNotice(`Switched to ${w.name}`); }} data-testid={`workspace-switch-${w.id}`}>Switch</button>}</td>
        <td><div className="row-actions">
          {can("workspaces", "write") && <button className="icon-btn" onClick={() => open(w)} data-testid={`workspace-edit-${w.id}`}><Pencil size={15} /></button>}
          {can("workspaces", "write") && w.id !== "ws-default" && <button className="icon-btn tg-del" onClick={() => remove(w)} data-testid={`workspace-delete-${w.id}`}><Trash2 size={15} /></button>}
        </div></td>
      </tr>)}
    </tbody></table></div>
    {can("workspaces", "write") && items.map(w => <PublicDisplay key={w.id} wsId={w.id} onNotice={onNotice} />)}
    <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.id ? "Rename workspace" : "New workspace"} eyebrow="WORKSPACE" testid="workspace-form">
      <form onSubmit={submit} className="add-form">
        <label>Workspace name<input required minLength={2} maxLength={60} value={name} onChange={e => setName(e.target.value)} placeholder="Branch Operations" data-testid="workspace-name" /></label>
        <div className="modal-actions"><button type="button" className="button secondary" onClick={() => setModal(null)} data-testid="workspace-form-cancel">Cancel</button><button type="submit" className="button primary" disabled={busy} data-testid="workspace-form-submit">{busy ? "Saving..." : "Save"}</button></div>
      </form>
    </Modal>
  </section>;
}
