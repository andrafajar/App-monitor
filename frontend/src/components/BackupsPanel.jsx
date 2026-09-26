import { useEffect, useState } from "react";
import { CalendarClock, Database, Download, Loader2, Save, Trash2 } from "lucide-react";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/auth/AuthContext";
import { PermissionPopup } from "@/components/ConfigEditor";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const BLANK = { frequency: "daily", hour: 2, minute: 0, weekday: 0, enabled: true, keep: 10 };

function ScheduleForm({ routerId, onNotice }) {
  const [form, setForm] = useState(BLANK);
  const [saved, setSaved] = useState(null);
  const [busy, setBusy] = useState("");
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const load = async () => {
    try {
      const r = await api.get(`/routers/${routerId}/backup-schedule`);
      setSaved(r.data.schedule || null);
      if (r.data.schedule) setForm({ ...BLANK, ...r.data.schedule });
    } catch { setSaved(null); }
  };
  useEffect(() => { load(); }, [routerId]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = async () => {
    setBusy("save");
    try {
      const r = await api.post(`/routers/${routerId}/backup-schedule`, { frequency: form.frequency, hour: Number(form.hour), minute: Number(form.minute), weekday: Number(form.weekday), enabled: form.enabled, keep: Number(form.keep) });
      setSaved(r.data.schedule); onNotice(`Schedule saved · next run ${new Date(r.data.schedule.next_run_at).toLocaleString()}`);
    } catch (err) { onNotice(errorText(err, "Could not save schedule")); } finally { setBusy(""); }
  };
  const remove = async () => {
    setBusy("del");
    try { await api.delete(`/routers/${routerId}/backup-schedule`); setSaved(null); setForm(BLANK); onNotice("Schedule removed"); }
    catch (err) { onNotice(errorText(err, "Delete failed")); } finally { setBusy(""); }
  };
  return <div className="tg-row" data-testid="backup-schedule">
    <div className="tg-head"><div><CalendarClock size={14} /><b>Scheduled snapshots</b></div>
      <div className="tg-status">{saved ? <span className="tg-pill on" data-testid="backup-schedule-status">{saved.enabled ? "Active" : "Paused"} · next {saved.next_run_at ? new Date(saved.next_run_at).toLocaleString() : "—"}</span> : <span className="tg-pill off" data-testid="backup-schedule-status">No schedule</span>}</div></div>
    <div className="tg-fields">
      <label>Frequency<select value={form.frequency} onChange={e => set("frequency", e.target.value)} data-testid="schedule-frequency"><option value="daily">Daily</option><option value="weekly">Weekly</option></select></label>
      {form.frequency === "weekly" && <label>Day<select value={form.weekday} onChange={e => set("weekday", e.target.value)} data-testid="schedule-weekday">{WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}</select></label>}
      <label>Hour (UTC)<select value={form.hour} onChange={e => set("hour", e.target.value)} data-testid="schedule-hour">{Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}</select></label>
      <label>Minute<select value={form.minute} onChange={e => set("minute", e.target.value)} data-testid="schedule-minute">{[0, 15, 30, 45].map(m => <option key={m} value={m}>{String(m).padStart(2, "0")}</option>)}</select></label>
      <label>Keep last<input type="number" min={1} max={100} value={form.keep} onChange={e => set("keep", e.target.value)} data-testid="schedule-keep" /></label>
      <label className="tg-toggle"><input type="checkbox" checked={form.enabled} onChange={e => set("enabled", e.target.checked)} data-testid="schedule-enabled" /><span>Run automatically</span></label>
    </div>
    <div className="tg-actions">
      <button className="button primary compact" onClick={save} disabled={busy === "save"} data-testid="schedule-save">{busy === "save" ? <Loader2 size={13} className="spin" /> : <Save size={13} />}Save schedule</button>
      {saved && <button className="tg-del" onClick={remove} disabled={busy === "del"} data-testid="schedule-delete"><Trash2 size={13} />Remove</button>}
      {saved?.last_run_at && <span className="muted" data-testid="schedule-last-run">Last run {new Date(saved.last_run_at).toLocaleString()} · {saved.last_status}</span>}
    </div>
  </div>;
}

export function BackupsPanel({ routerId, onNotice, onGoSettings }) {
  const { can } = useAuth();
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState("");
  const [permErr, setPermErr] = useState(null);
  const load = async () => { try { const r = await api.get(`/routers/${routerId}/backups`); setItems(r.data.items || []); } catch (err) { onNotice(errorText(err)); setItems([]); } };
  useEffect(() => { load(); }, [routerId]); // eslint-disable-line react-hooks/exhaustive-deps
  const run = async () => {
    setBusy("run");
    try { const r = await api.post(`/routers/${routerId}/backup-now`); onNotice(`Backup saved · ${r.data.backup.filename} (${r.data.backup.sections.length} sections)`); load(); }
    catch (err) { if ([403, 428, 401].includes(err.response?.status)) setPermErr(err); else onNotice(errorText(err, "Backup failed")); }
    finally { setBusy(""); }
  };
  const download = async (b) => {
    try {
      const r = await api.get(`/backups/${b.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = url; a.download = b.filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (err) { onNotice(errorText(err, "Download failed")); }
  };
  const remove = async (b) => {
    setBusy(b.id);
    try { await api.delete(`/backups/${b.id}`); onNotice(`${b.filename} deleted`); load(); } catch (err) { onNotice(errorText(err)); } finally { setBusy(""); }
  };
  return <>
    <div className="res-toolbar"><b data-testid="backups-count">{items ? `${items.length} snapshot${items.length === 1 ? "" : "s"}` : "…"}</b>
      {can("backups", "write") && <button className="button primary compact" onClick={run} disabled={busy === "run"} data-testid="backup-now-button">{busy === "run" ? <Loader2 size={13} className="spin" /> : <Database size={13} />}{busy === "run" ? "Exporting..." : "Backup now (.rsc)"}</button>}</div>
    <p className="backup-note" data-testid="backup-status-note">Creates a <code>.rsc</code> configuration snapshot through the RouterOS API (identity, clock, interfaces, IP, firewall, NAT, routes, PPP, queues — PPP passwords redacted) and stores it in encrypted object storage.</p>
    {can("backups", "write") && <ScheduleForm routerId={routerId} onNotice={onNotice} />}
    {items === null ? <div className="res-loading"><Loader2 size={14} className="spin" />Loading backups…</div>
      : <div className="res-table" data-testid="backups-table"><table><thead><tr><th>FILE</th><th>SIZE</th><th>SECTIONS</th><th>BY</th><th>CREATED</th><th></th></tr></thead><tbody>
        {items.length === 0 && <tr><td colSpan={6} className="res-empty">No snapshots yet.</td></tr>}
        {items.map((b, i) => <tr key={b.id} data-testid={`backup-row-${i}`}><td className="mono">{b.filename}</td><td className="mono">{(b.size / 1024).toFixed(1)} KB</td><td className="muted">{(b.sections || []).length}</td><td className="muted">{b.scheduled ? "scheduler" : b.created_by_email}</td><td className="muted">{new Date(b.created_at).toLocaleString()}</td>
          <td><div className="row-actions"><button className="icon-btn" title="Download" onClick={() => download(b)} data-testid={`backup-download-${i}`}><Download size={14} /></button>{can("backups", "write") && <button className="icon-btn tg-del" title="Delete" onClick={() => remove(b)} disabled={busy === b.id} data-testid={`backup-delete-${i}`}><Trash2 size={14} /></button>}</div></td></tr>)}
      </tbody></table></div>}
    <PermissionPopup error={permErr} onClose={() => setPermErr(null)} onGoSettings={onGoSettings} />
  </>;
}
