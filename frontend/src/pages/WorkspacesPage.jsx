import { useEffect, useState } from "react";
import { Building2, Check, Pencil, Plus, Trash2 } from "lucide-react";
import { Modal } from "@/components/Modal";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/auth/AuthContext";

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
    <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.id ? "Rename workspace" : "New workspace"} eyebrow="WORKSPACE" testid="workspace-form">
      <form onSubmit={submit} className="add-form">
        <label>Workspace name<input required minLength={2} maxLength={60} value={name} onChange={e => setName(e.target.value)} placeholder="Branch Operations" data-testid="workspace-name" /></label>
        <div className="modal-actions"><button type="button" className="button secondary" onClick={() => setModal(null)} data-testid="workspace-form-cancel">Cancel</button><button type="submit" className="button primary" disabled={busy} data-testid="workspace-form-submit">{busy ? "Saving..." : "Save"}</button></div>
      </form>
    </Modal>
  </section>;
}
