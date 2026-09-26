import { useEffect, useState } from "react";
import { AlertTriangle, KeyRound, Loader2, Save, ShieldAlert, Trash2 } from "lucide-react";
import { Modal } from "@/components/Modal";
import { EDITABLE_FIELDS, REFERENCE_SOURCES, RESOURCE_KEY } from "@/lib/ros";
import { api, errorText } from "@/lib/api";
const rid = (row) => row?.[".id"] || row?.id;

const toForm = (fields, row) => Object.fromEntries(fields.map(f => {
  let v = row?.[f.key] ?? "";
  if (f.type === "yesno") v = v === true || v === "true" || v === "yes" ? "yes" : (v === "" ? "" : "no");
  return [f.key, String(v)];
}));

// Pick-lists (interfaces, bridges, pools, profiles…) are read live from the router so no name has to be typed by hand.
function useReferences(open, fields, routerId) {
  const [refs, setRefs] = useState({});
  const sources = [...new Set(fields.filter(f => f.source).map(f => f.source))].sort().join(",");
  useEffect(() => {
    if (!open || !sources) { setRefs({}); return; }
    let alive = true;
    setRefs(Object.fromEntries(sources.split(",").map(s => [s, undefined])));
    Promise.all(sources.split(",").map(async (source) => {
      const cfg = REFERENCE_SOURCES[source];
      try {
        const r = await api.get(`/routers/${routerId}/resources/${cfg.resource}`);
        const names = [...new Set((r.data.items || []).map(x => x[cfg.label]).filter(Boolean))];
        return [source, names];
      } catch { return [source, null]; }
    })).then(entries => { if (alive) setRefs(Object.fromEntries(entries)); });
    return () => { alive = false; };
  }, [open, sources, routerId]);
  return refs;
}

export function ConfigEditor({ open, onClose, tab, routerId, row, onDone, onError }) {
  const fields = EDITABLE_FIELDS[tab] || [];
  const resource = RESOURCE_KEY[tab];
  const isEdit = !!row;
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  const refs = useReferences(open, fields, routerId);
  useEffect(() => { if (open) setForm(toForm(fields, row)); }, [open, row, tab]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!open) return null;
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    const original = toForm(fields, row);
    const values = {};
    for (const f of fields) {
      const v = form[f.key] ?? "";
      if (isEdit ? v !== original[f.key] : v !== "") values[f.key] = v;
    }
    if (isEdit && Object.keys(values).length === 0) { onClose(); setBusy(false); return; }
    try {
      const body = { values, item_id: rid(row) || null };
      await api.post(`/routers/${routerId}/config/${resource}/${isEdit ? "set" : "add"}`, body);
      onDone(isEdit ? `${tab}: entry updated` : `${tab}: entry added`); onClose();
    } catch (err) { onError(err); }
    finally { setBusy(false); }
  };

  const renderField = (f) => {
    const value = form[f.key] ?? "";
    if (f.type === "yesno") return <select value={value} onChange={e => set(f.key, e.target.value)} data-testid={`cfg-${f.key}`}><option value="">— keep —</option><option value="no">no</option><option value="yes">yes</option></select>;
    if (f.type === "select") return <select value={value} onChange={e => set(f.key, e.target.value)} required={f.required && !isEdit} data-testid={`cfg-${f.key}`}><option value="">—</option>{f.options.map(o => <option key={o} value={o}>{o}</option>)}</select>;
    if (f.source) {
      const list = refs[f.source];
      if (list === undefined) return <select disabled data-testid={`cfg-${f.key}`}><option>loading from router…</option></select>;
      if (list === null) return <input value={value} onChange={e => set(f.key, e.target.value)} placeholder="type the name (list unavailable)" required={f.required && !isEdit} data-testid={`cfg-${f.key}`} />;
      const options = value && !list.includes(value) ? [value, ...list] : list;
      return <select value={value} onChange={e => set(f.key, e.target.value)} required={f.required && !isEdit} data-testid={`cfg-${f.key}`}>
        <option value="">{list.length ? "— select —" : "— none on this router —"}</option>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>;
    }
    return <input type={f.type === "password" ? "password" : "text"} value={value} onChange={e => set(f.key, e.target.value)} placeholder={f.placeholder || ""} required={f.required && !isEdit} autoComplete="off" data-testid={`cfg-${f.key}`} />;
  };

  return <Modal open={open} onClose={onClose} title={isEdit ? `Edit ${tab}` : `New ${tab}`} eyebrow={`ROUTEROS · ${resource.toUpperCase()}${rid(row) ? ` · ${rid(row)}` : ""}`} hint="Changes are sent live to the router through the RouterOS API using your MikroTik credentials. Reference fields list the objects that exist on this router." testid="config-editor">
    <form onSubmit={submit} className="add-form cfg-form">
      <div className="cfg-grid">
        {fields.map(f => <label key={f.key}>{f.key.replaceAll("-", " ")}{f.required && !isEdit && " *"}{renderField(f)}</label>)}
      </div>
      <div className="modal-actions">
        <button type="button" className="button secondary" onClick={onClose} data-testid="config-editor-cancel">Cancel</button>
        <button type="submit" className="button primary" disabled={busy} data-testid="config-editor-submit">{busy ? <Loader2 size={14} className="spin" /> : <Save size={14} />}{busy ? "Applying..." : isEdit ? "Apply changes" : "Add entry"}</button>
      </div>
    </form>
  </Modal>;
}

export function ConfirmRemove({ open, onClose, tab, routerId, row, onDone, onError }) {
  const [busy, setBusy] = useState(false);
  if (!open || !row) return null;
  const label = row.name || row.address || row["dst-address"] || row.chain || rid(row);
  const remove = async () => {
    setBusy(true);
    try { await api.post(`/routers/${routerId}/config/${RESOURCE_KEY[tab]}/remove`, { values: {}, item_id: rid(row) }); onDone(`${tab}: ${label} removed`); onClose(); }
    catch (err) { onError(err); }
    finally { setBusy(false); }
  };
  return <Modal open={open} onClose={onClose} title={`Remove ${tab.toLowerCase()} entry?`} eyebrow="DESTRUCTIVE" testid="confirm-remove">
    <p className="muted">This will run <code>remove {rid(row)}</code> on the router immediately. <b>{label}</b> cannot be recovered from NetPulse.</p>
    <div className="modal-actions">
      <button className="button secondary" onClick={onClose} data-testid="confirm-remove-cancel">Cancel</button>
      <button className="button danger" onClick={remove} disabled={busy} data-testid="confirm-remove-submit">{busy ? <Loader2 size={14} className="spin" /> : <Trash2 size={14} />}Remove</button>
    </div>
  </Modal>;
}

export function PermissionPopup({ error, onClose, onGoSettings }) {
  if (!error) return null;
  const status = error.response?.status;
  const text = errorText(error);
  const noPerm = status === 403 && /not enough permission/i.test(text);
  const needCreds = status === 428;
  return <Modal open onClose={onClose} title={noPerm ? "Not enough permission" : needCreds ? "MikroTik credentials required" : status === 401 ? "RouterOS login rejected" : "Action failed"} eyebrow={noPerm ? "ROUTEROS POLICY" : needCreds ? "MY SETTINGS" : "ERROR"} testid="permission-popup">
    <div className="perm-body">
      <div className={`alarm-symbol ${noPerm ? "warn" : ""}`}>{noPerm ? <ShieldAlert size={20} /> : needCreds ? <KeyRound size={20} /> : <AlertTriangle size={20} />}</div>
      <p data-testid="permission-popup-text">{noPerm ? "The MikroTik account you are connected with does not have write policy on this router (read-only user). Ask the router administrator to grant 'write' policy, or switch to another MikroTik account in My settings." : text}</p>
    </div>
    <div className="modal-actions">
      {(needCreds || noPerm) && <button className="button secondary" onClick={onGoSettings} data-testid="permission-popup-settings">Open My settings</button>}
      <button className="button primary" onClick={onClose} data-testid="permission-popup-ok">OK</button>
    </div>
  </Modal>;
}
