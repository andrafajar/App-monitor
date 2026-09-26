import { useEffect, useState } from "react";
import { ChevronRight, CornerDownRight, Pencil, Plus, Trash2, Users } from "lucide-react";
import { Modal } from "@/components/Modal";
import { api, errorText, slug } from "@/lib/api";
import { useAuth } from "@/auth/AuthContext";

export function GroupForm({ open, onClose, editing, groups, onSaved, onNotice, defaultParent }) {
  const [name, setName] = useState("");
  const [parent, setParent] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setName(editing?.name || ""); setParent(editing ? (editing.parent_id || "") : (defaultParent || "")); } }, [open, editing, defaultParent]);
  if (!open) return null;
  const descendants = new Set();
  if (editing) { let frontier = [editing.id]; while (frontier.length) { const n = frontier.pop(); descendants.add(n); frontier.push(...groups.filter(g => g.parent_id === n).map(g => g.id)); } }
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      const body = { name: name.trim(), parent_id: parent || null };
      if (editing) await api.put(`/groups/${editing.id}`, body); else await api.post("/groups", body);
      onNotice(editing ? `Group renamed to "${body.name}"` : `Group "${body.name}" created`); onSaved(); onClose();
    } catch (err) { onNotice(errorText(err, "Save failed")); }
    finally { setBusy(false); }
  };
  return <Modal open={open} onClose={onClose} title={editing ? "Edit group" : "Add group"} eyebrow="DEVICE GROUPS" hint="Groups can be nested (parent → child). Access is granted per group explicitly — no inheritance." testid="add-group-modal">
    <form onSubmit={submit} className="add-form">
      <label>Group name<input required minLength={2} maxLength={60} value={name} onChange={e => setName(e.target.value)} placeholder="Region West" data-testid="add-group-name" /></label>
      <label>Parent group<select value={parent} onChange={e => setParent(e.target.value)} data-testid="add-group-parent"><option value="">— top level —</option>{groups.filter(g => !descendants.has(g.id)).map(g => <option key={g.id} value={g.id}>{"  ".repeat(g.depth)}{g.path}</option>)}</select></label>
      <div className="modal-actions">
        <button type="button" className="button secondary" onClick={onClose} data-testid="add-group-cancel">Cancel</button>
        <button type="submit" className="button primary" disabled={busy} data-testid="add-group-submit"><Plus size={14} />{busy ? "Saving..." : editing ? "Save group" : "Create group"}</button>
      </div>
    </form>
  </Modal>;
}

export function GroupSettings({ group, groups, onClose, onNotice, onChanged, onOpenNotifications, onOpenRouter }) {
  const { can } = useAuth();
  const [info, setInfo] = useState(null);
  const [name, setName] = useState(group?.name || "");
  const [parent, setParent] = useState(group?.parent_id || "");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!group) return; setName(group.name); setParent(group.parent_id || ""); api.get(`/groups/${group.id}/access`).then(r => setInfo(r.data)).catch(err => onNotice(errorText(err))); }, [group]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!group) return null;
  const descendants = new Set(); let frontier = [group.id]; while (frontier.length) { const n = frontier.pop(); descendants.add(n); frontier.push(...groups.filter(g => g.parent_id === n).map(g => g.id)); }
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    try { await api.put(`/groups/${group.id}`, { name: name.trim(), parent_id: parent || null }); onNotice("Group settings saved"); onChanged(); }
    catch (err) { onNotice(errorText(err, "Save failed")); } finally { setBusy(false); }
  };
  return <Modal open onClose={onClose} title={group.name} eyebrow={`GROUP SETTINGS · ${group.path}`} testid="group-settings" wide>
    <div className="gs-grid">
      <form onSubmit={save} className="add-form">
        <label>Group name<input required minLength={2} maxLength={60} value={name} onChange={e => setName(e.target.value)} disabled={!can("groups", "write")} data-testid="group-settings-name" /></label>
        <label>Parent group<select value={parent} onChange={e => setParent(e.target.value)} disabled={!can("groups", "write")} data-testid="group-settings-parent"><option value="">— top level —</option>{groups.filter(g => !descendants.has(g.id)).map(g => <option key={g.id} value={g.id}>{g.path}</option>)}</select></label>
        {can("groups", "write") && <div className="modal-actions"><button type="submit" className="button primary" disabled={busy} data-testid="group-settings-save">{busy ? "Saving..." : "Save"}</button></div>}
      </form>
      <div className="gs-side">
        <div className="gs-block"><span className="pick-title">Routers in this group ({info?.routers?.length ?? "…"})</span>
          {info?.routers?.length === 0 && <span className="muted">No routers yet.</span>}
          {info?.routers?.map(r => <button key={r.id} className="gs-item" onClick={() => onOpenRouter(r.id)} data-testid={`group-router-${r.id}`}><b>{r.name}</b><span className="mono">{r.host}</span></button>)}
        </div>
        <div className="gs-block"><span className="pick-title">Roles with access · Telegram</span>
          {info?.roles?.length === 0 && <span className="muted">No role grants this group yet. Edit a role to add it.</span>}
          {info?.roles?.map(r => <div key={r.id} className="gs-item static" data-testid={`group-role-${r.id}`}><b>{r.name}</b>{r.telegram_configured ? <span className={`tg-pill ${r.telegram_enabled ? "on" : "off"}`}>{r.telegram_enabled ? "Telegram on" : "Telegram off"}</span> : <span className="tg-pill off">no Telegram</span>}</div>)}
          {can("notifications", "read") && <button type="button" className="text-btn" onClick={onOpenNotifications} data-testid="group-settings-notifications">Configure Telegram per role <ChevronRight size={14} /></button>}
        </div>
        <div className="gs-block"><span className="pick-title">Users who can see this group ({info?.users?.length ?? "…"})</span>
          {info?.users?.map(u => <div key={u.user_id} className="gs-item static"><b>{u.name}</b><span className="mono">{u.email}</span></div>)}
        </div>
      </div>
    </div>
  </Modal>;
}

export default function GroupsPage({ groups, routers, onNotice, onChanged, onOpenGroup, modalOpen, setModalOpen }) {
  const { can } = useAuth();
  const [editing, setEditing] = useState(null);
  const [parentFor, setParentFor] = useState("");
  const remove = async (g) => {
    try { await api.delete(`/groups/${g.id}`); onNotice(`Group "${g.name}" removed`); onChanged(); }
    catch (err) { onNotice(errorText(err, "Delete group failed")); }
  };
  const count = (g) => routers.filter(r => r.group_id === g.id).length;
  return <section className="panel routers-panel" data-testid="groups-view">
    <div className="panel-head table-head"><div><p className="eyebrow">DEVICE GROUPS / {groups.length} GROUPS</p><h2>Groups & tenants</h2></div></div>
    <div className="table-wrap"><table><thead><tr><th>GROUP</th><th>ROUTERS</th><th>PATH</th><th></th></tr></thead><tbody>
      {groups.length === 0 && <tr><td colSpan={4} className="res-empty">No groups you can access in this workspace.</td></tr>}
      {groups.map(g => <tr key={g.id} data-testid={`groups-row-${slug(g.name)}`} onClick={() => onOpenGroup(g)}>
        <td><div className="router-name" style={{ paddingLeft: g.depth * 22 }}>{g.depth > 0 && <CornerDownRight size={13} className="muted" />}<div className="router-icon cyan"><Users size={15} /></div><div><b>{g.name}</b><span>{count(g)} device{count(g) !== 1 ? "s" : ""}{g.depth > 0 ? " · child group" : ""}</span></div></div></td>
        <td className="mono">{count(g)}</td>
        <td className="muted">{g.path}</td>
        <td><div className="row-actions" onClick={e => e.stopPropagation()}>
          {can("groups", "write") && <button className="icon-btn" title="Add child group" onClick={() => { setEditing(null); setParentFor(g.id); setModalOpen(true); }} data-testid={`groups-add-child-${slug(g.name)}`}><Plus size={15} /></button>}
          {can("groups", "write") && <button className="icon-btn" title="Edit" onClick={() => { setEditing(g); setModalOpen(true); }} data-testid={`groups-edit-${slug(g.name)}`}><Pencil size={15} /></button>}
          {can("groups", "write") && count(g) === 0 && !groups.some(x => x.parent_id === g.id) && <button className="icon-btn tg-del" title="Remove group" onClick={() => remove(g)} data-testid={`groups-delete-${slug(g.name)}`}><Trash2 size={15} /></button>}
          <button className="row-arrow" onClick={() => onOpenGroup(g)} data-testid={`groups-open-${slug(g.name)}`}><ChevronRight size={16} /></button>
        </div></td>
      </tr>)}
    </tbody></table></div>
    <GroupForm open={modalOpen} onClose={() => { setModalOpen(false); setEditing(null); setParentFor(""); }} editing={editing} groups={groups} defaultParent={parentFor} onSaved={onChanged} onNotice={onNotice} />
  </section>;
}
