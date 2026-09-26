import { useEffect, useState } from "react";
import { Loader2, Save, Zap } from "lucide-react";
import { Modal } from "@/components/Modal";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/auth/AuthContext";

const DEFAULTS = { enabled: true, cpu_threshold: 80, notify_unreachable: true, notify_interface: true, throttle_minutes: 60 };

export default function AlarmSettings({ open, onClose, onNotice }) {
  const { can } = useAuth();
  const [form, setForm] = useState(DEFAULTS);
  const [meta, setMeta] = useState({});
  const [busy, setBusy] = useState("");
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  useEffect(() => {
    if (!open) return;
    api.get("/alarms/settings").then(r => { setForm({ ...DEFAULTS, ...r.data.settings }); setMeta({ last_scan_at: r.data.last_scan_at, last_scan_result: r.data.last_scan_result }); }).catch(err => onNotice(errorText(err)));
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!open) return null;

  const save = async (e) => {
    e.preventDefault(); setBusy("save");
    try { await api.put("/alarms/settings", form); onNotice("Alarm engine settings saved"); onClose(); }
    catch (err) { onNotice(errorText(err, "Save failed")); } finally { setBusy(""); }
  };

  return <Modal open onClose={onClose} title="Automatic alarm engine" eyebrow="ALARM RULES · WORKSPACE" hint="A background checker runs every 15 minutes, probes each router and delivers matching alarms to the Telegram channel of every role that covers the router's group." testid="alarm-settings">
    <form onSubmit={save} className="add-form">
      <label className="tg-toggle"><input type="checkbox" checked={form.enabled} onChange={e => set("enabled", e.target.checked)} data-testid="alarm-enabled" /><span>Run the automatic checker for this workspace</span></label>
      <label>CPU threshold (%)<input type="number" min={20} max={100} value={form.cpu_threshold} onChange={e => set("cpu_threshold", parseInt(e.target.value, 10) || 80)} data-testid="alarm-cpu-threshold" /></label>
      <label className="tg-toggle"><input type="checkbox" checked={form.notify_unreachable} onChange={e => set("notify_unreachable", e.target.checked)} data-testid="alarm-unreachable" /><span>Alarm when a router stops answering the RouterOS API</span></label>
      <label className="tg-toggle"><input type="checkbox" checked={form.notify_interface} onChange={e => set("notify_interface", e.target.checked)} data-testid="alarm-interface" /><span>Alarm when an interface goes up or down</span></label>
      <label>Re-notify after (minutes)<input type="number" min={5} max={1440} value={form.throttle_minutes} onChange={e => set("throttle_minutes", parseInt(e.target.value, 10) || 60)} data-testid="alarm-throttle" /></label>
      <p className="backup-note" data-testid="alarm-last-scan"><Zap size={12} /> Last scan: {meta.last_scan_at ? `${new Date(meta.last_scan_at).toLocaleString()} · ${meta.last_scan_result || ""}` : "not run yet"}</p>
      <div className="modal-actions">
        <button type="button" className="button secondary" onClick={onClose} data-testid="alarm-settings-cancel">Close</button>
        {can("alarms", "write") && <button type="submit" className="button primary" disabled={busy === "save"} data-testid="alarm-settings-save">{busy === "save" ? <Loader2 size={14} className="spin" /> : <Save size={14} />}Save rules</button>}
      </div>
    </form>
  </Modal>;
}
