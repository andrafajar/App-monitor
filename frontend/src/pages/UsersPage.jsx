import { useEffect, useState } from "react";
import { Pencil, Plus, ShieldCheck, Trash2, Users } from "lucide-react";
import { Modal } from "@/components/Modal";
import { api, errorText, slug } from "@/lib/api";
import { useAuth } from "@/auth/AuthContext";

const blank = { email: "", name: "", password: "", role_id: "", is_super_admin: false, disabled: false, workspace_ids: [], restrict: false, allowed_group_ids: [] };

function UserForm({ open, onClose, editing, roles, workspaces, groups, onSaved, onNotice }) {
  const { user: me } = useAuth();
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    setForm(editing ? { email: editing.email, name: editing.name, password: "", role_id: editing.role_id || "", is_super_admin: !!editing.is_super_admin, disabled: !!editing.disabled, workspace_ids: editing.workspace_ids || [], restrict: editing.allowed_group_ids != null, allowed_group_ids: editing.allowed_group_ids || [] } : blank);
  }, [open, editing]);
  if (!open) return null;
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const toggle = (k, id) => setForm(f => ({ ...f, [k]: f[k].includes(id) ? f[k].filter(x => x !== id) : [...f[k], id] }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    const body = { email: form.email.trim(), name: form.name.trim(), role_id: form.role_id || null, is_super_admin: form.is_super_admin, disabled: form.disabled, workspace_ids: form.workspace_ids, allowed_group_ids: form.restrict ? form.allowed_group_ids : null };
    if (form.password) body.password = form.password;
    try {
      if (editing) await api.put(`/users/${editing.user_id}`, body); else await api.post("/users", body);
      onNotice(editing ? `${body.name} updated` : `${body.name} created`); onSaved(); onClose();
    } catch (err) { onNotice(errorText(err, "Save failed")); }
    finally { setBusy(false); }
  };
  return <Modal open={open} onClose={onClose} title={editing ? "Edit user" : "Add user"} eyebrow="USER MANAGEMENT" hint="Users bring their own MikroTik credentials in My settings; shared routers only expose name + IP." testid="user-form" wide>
    <form onSubmit={submit} className="add-form">
      <div className="two-col">
        <label>Full name<input required value={form.name} onChange={e => set("name", e.target.value)} data-testid="user-name" /></label>
        <label>Email<input type="email" required value={form.email} onChange={e => set("email", e.target.value)} data-testid="user-email" /></label>
      </div>
      <div className="two-col">
        <label>{editing ? "New password (blank = keep)" : "Password (blank = Google sign-in only)"}<input type="password" minLength={8} value={form.password} onChange={e => set("password", e.target.value)} autoComplete="new-password" data-testid="user-password" /></label>
        <label>Role<select value={form.role_id} onChange={e => set("role_id", e.target.value)} disabled={form.is_super_admin} data-testid="user-role"><option value="">— no role —</option>{roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
      </div>
      <div className="check-row">
        {me?.is_super_admin && <label className="tg-toggle"><input type="checkbox" checked={form.is_super_admin} onChange={e => set("is_super_admin", e.target.checked)} data-testid="user-super-admin" /><span>Super Admin (full access everywhere)</span></label>}
        <label className="tg-toggle"><input type="checkbox" checked={form.disabled} onChange={e => set("disabled", e.target.checked)} data-testid="user-disabled" /><span>Disabled</span></label>
      </div>
      {!form.is_super_admin && <>
        <div className="pick-box"><span className="pick-title">Workspaces</span>
          {workspaces.map(w => <label key={w.id} className="tg-toggle"><input type="checkbox" checked={form.workspace_ids.includes(w.id)} onChange={() => toggle("workspace_ids", w.id)} data-testid={`user-ws-${w.id}`} /><span>{w.name}</span></label>)}
        </div>
        <div className="pick-box">
          <label className="tg-toggle pick-title"><input type="checkbox" checked={form.restrict} onChange={e => set("restrict", e.target.checked)} data-testid="user-restrict-groups" /><span>Restrict to specific device groups (overrides the role's groups)</span></label>
          {form.restrict && groups.map(g => <label key={g.id} className="tg-toggle" style={{ paddingLeft: 12 + g.depth * 14 }}><input type="checkbox" checked={form.allowed_group_ids.includes(g.id)} onChange={() => toggle("allowed_group_ids", g.id)} data-testid={`user-group-${g.id}`} /><span>{g.name}</span></label>)}
        </div>
      </>}
      <div className="modal-actions">
        <button type="button" className="button secondary" onClick={onClose} data-testid="user-form-cancel">Cancel</button>
        <button type="submit" className="button primary" disabled={busy} data-testid="user-form-submit">{busy ? "Saving..." : editing ? "Save user" : "Create user"}</button>
      </div>
    </form>
  </Modal>;
}

export default function UsersPage({ onNotice, groups }) {
  const { user: me, can } = useAuth();
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [workspaces, setWorkspaces] = useState([]);
  const [modal, setModal] = useState(null);
  const load = async () => {
    try {
      const [u, r, w] = await Promise.all([api.get("/users"), api.get("/roles"), api.get("/workspaces")]);
      setUsers(u.data.items || []); setRoles(r.data.items || []); setWorkspaces(w.data.items || []);
    } catch (err) { onNotice(errorText(err)); }
  };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const remove = async (u) => {
    if (!window.confirm(`Remove ${u.email}?`)) return;
    try { await api.delete(`/users/${u.user_id}`); onNotice(`${u.email} removed`); load(); } catch (err) { onNotice(errorText(err)); }
  };
  const roleName = (id) => roles.find(r => r.id === id)?.name || "—";
  return <section className="panel routers-panel" data-testid="users-view">
    <div className="panel-head table-head"><div><p className="eyebrow">ACCESS CONTROL / {users.length} USERS</p><h2>Users</h2></div>
      {can("users", "write") && <button className="button primary compact" onClick={() => setModal({})} data-testid="add-user-button"><Plus size={14} />Add user</button>}</div>
    <div className="table-wrap"><table><thead><tr><th>USER</th><th>ROLE</th><th>WORKSPACES</th><th>GROUP SCOPE</th><th>MIKROTIK CREDS</th><th>STATUS</th><th></th></tr></thead><tbody>
      {users.map(u => <tr key={u.user_id} data-testid={`user-row-${slug(u.email)}`}>
        <td><div className="router-name"><div className="router-icon cyan"><Users size={15} /></div><div><b>{u.name}</b><span>{u.email}{u.auth_provider === "google" ? " · Google" : ""}</span></div></div></td>
        <td>{u.is_super_admin ? <span className="tg-pill on"><ShieldCheck size={12} />Super Admin</span> : <span className="group-label">{roleName(u.role_id)}</span>}</td>
        <td className="mono">{u.is_super_admin ? "all" : (u.workspace_ids || []).map(id => workspaces.find(w => w.id === id)?.name || id).join(", ") || "—"}</td>
        <td className="muted">{u.is_super_admin ? "all groups" : u.allowed_group_ids == null ? "follows role" : `${u.allowed_group_ids.length} specific`}</td>
        <td>{u.has_ros_credentials ? <span className="tg-pill on">set</span> : <span className="tg-pill off">not set</span>}</td>
        <td>{u.disabled ? <span className="status status-offline"><i />Disabled</span> : <span className="status status-online"><i />Active</span>}</td>
        <td><div className="row-actions">
          {can("users", "write") && <button className="icon-btn" onClick={() => setModal(u)} data-testid={`user-edit-${slug(u.email)}`}><Pencil size={15} /></button>}
          {can("users", "write") && u.user_id !== me.user_id && <button className="icon-btn tg-del" onClick={() => remove(u)} data-testid={`user-delete-${slug(u.email)}`}><Trash2 size={15} /></button>}
        </div></td>
      </tr>)}
    </tbody></table></div>
    <UserForm open={!!modal} editing={modal?.user_id ? modal : null} onClose={() => setModal(null)} roles={roles} workspaces={workspaces} groups={groups} onSaved={load} onNotice={onNotice} />
  </section>;
}
