import { useEffect, useState } from "react";
import { Pencil, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { Modal } from "@/components/Modal";
import { api, errorText, slug } from "@/lib/api";
import { MODULE_LABELS } from "@/lib/ros";
import { useAuth } from "@/auth/AuthContext";

function RoleForm({ open, onClose, editing, modules, groups, onSaved, onNotice }) {
  const [form, setForm] = useState({ name: "", description: "", privileges: {}, group_ids: [] });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    setForm(editing ? { name: editing.name, description: editing.description || "", privileges: { ...editing.privileges }, group_ids: editing.group_ids || [] } : { name: "", description: "", privileges: Object.fromEntries(modules.map(m => [m, "none"])), group_ids: [] });
  }, [open, editing, modules]);
  if (!open) return null;
  const setPriv = (m, lvl) => setForm(f => ({ ...f, privileges: { ...f.privileges, [m]: lvl } }));
  const toggleGroup = (id) => setForm(f => ({ ...f, group_ids: f.group_ids.includes(id) ? f.group_ids.filter(x => x !== id) : [...f.group_ids, id] }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      if (editing) await api.put(`/roles/${editing.id}`, form); else await api.post("/roles", form);
      onNotice(editing ? `Role ${form.name} updated` : `Role ${form.name} created`); onSaved(); onClose();
    } catch (err) { onNotice(errorText(err, "Save failed")); }
    finally { setBusy(false); }
  };
  return <Modal open={open} onClose={onClose} title={editing ? `Edit role · ${editing.name}` : "Create role"} eyebrow="ROLE PRIVILEGES" hint="Pick what this role can see or change per module, then choose the device groups it may access (no inheritance — pick each group explicitly)." testid="role-form" wide>
    <form onSubmit={submit} className="add-form">
      <div className="two-col">
        <label>Role name<input required minLength={2} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} data-testid="role-name" /></label>
        <label>Description<input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} data-testid="role-description" /></label>
      </div>
      <div className="priv-grid" data-testid="role-privileges">
        {modules.map(m => <div key={m} className="priv-row"><span>{MODULE_LABELS[m] || m}</span>
          <div className="seg">{["none", "read", "write"].map(l => <button type="button" key={l} className={form.privileges[m] === l ? "on" : ""} onClick={() => setPriv(m, l)} data-testid={`priv-${m}-${l}`}>{l}</button>)}</div>
        </div>)}
      </div>
      <div className="pick-box"><span className="pick-title">Device groups this role can access</span>
        {groups.length === 0 && <span className="muted">No groups in this workspace yet.</span>}
        {groups.map(g => <label key={g.id} className="tg-toggle" style={{ paddingLeft: 12 + g.depth * 14 }}><input type="checkbox" checked={form.group_ids.includes(g.id)} onChange={() => toggleGroup(g.id)} data-testid={`role-group-${g.id}`} /><span>{g.name}</span><small className="muted"> · {g.router_count} router{g.router_count === 1 ? "" : "s"}</small></label>)}
      </div>
      <div className="modal-actions">
        <button type="button" className="button secondary" onClick={onClose} data-testid="role-form-cancel">Cancel</button>
        <button type="submit" className="button primary" disabled={busy} data-testid="role-form-submit">{busy ? "Saving..." : editing ? "Save role" : "Create role"}</button>
      </div>
    </form>
  </Modal>;
}

export default function RolesPage({ onNotice, groups }) {
  const { can } = useAuth();
  const [roles, setRoles] = useState([]);
  const [modules, setModules] = useState([]);
  const [modal, setModal] = useState(null);
  const load = async () => { try { const r = await api.get("/roles"); setRoles(r.data.items || []); setModules(r.data.modules || []); } catch (err) { onNotice(errorText(err)); } };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const remove = async (r) => {
    if (!window.confirm(`Remove role ${r.name}?`)) return;
    try { await api.delete(`/roles/${r.id}`); onNotice(`Role ${r.name} removed`); load(); } catch (err) { onNotice(errorText(err)); }
  };
  const summary = (p) => { const w = Object.values(p || {}).filter(v => v === "write").length; const r = Object.values(p || {}).filter(v => v === "read").length; return `${w} write · ${r} read`; };
  return <section className="panel routers-panel" data-testid="roles-view">
    <div className="panel-head table-head"><div><p className="eyebrow">ACCESS CONTROL / {roles.length} ROLES</p><h2>Roles & privileges</h2></div>
      {can("roles", "write") && <button className="button primary compact" onClick={() => setModal({})} data-testid="add-role-button"><Plus size={14} />Create role</button>}</div>
    <div className="table-wrap"><table><thead><tr><th>ROLE</th><th>PRIVILEGES</th><th>GROUPS</th><th>USERS</th><th>TELEGRAM</th><th></th></tr></thead><tbody>
      <tr data-testid="role-row-super-admin"><td><div className="router-name"><div className="router-icon amber"><ShieldCheck size={15} /></div><div><b>Super Admin</b><span>Built-in · everything, every workspace</span></div></div></td><td className="muted">all modules · write</td><td className="muted">all</td><td className="mono">—</td><td className="muted">—</td><td></td></tr>
      {roles.map(r => <tr key={r.id} data-testid={`role-row-${slug(r.name)}`}>
        <td><div className="router-name"><div className="router-icon cyan"><ShieldCheck size={15} /></div><div><b>{r.name}</b><span>{r.description || (r.builtin ? "Built-in" : "Custom role")}</span></div></div></td>
        <td className="muted">{summary(r.privileges)}</td>
        <td className="mono">{(r.group_ids || []).length}</td>
        <td className="mono">{r.user_count}</td>
        <td className="muted">Configure in Settings › Notifications</td>
        <td><div className="row-actions">
          {can("roles", "write") && <button className="icon-btn" onClick={() => setModal(r)} data-testid={`role-edit-${slug(r.name)}`}><Pencil size={15} /></button>}
          {can("roles", "write") && !r.builtin && <button className="icon-btn tg-del" onClick={() => remove(r)} data-testid={`role-delete-${slug(r.name)}`}><Trash2 size={15} /></button>}
        </div></td>
      </tr>)}
    </tbody></table></div>
    <RoleForm open={!!modal} editing={modal?.id ? modal : null} onClose={() => setModal(null)} modules={modules} groups={groups} onSaved={load} onNotice={onNotice} />
  </section>;
}
