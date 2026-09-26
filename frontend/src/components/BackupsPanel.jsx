import { useEffect, useState } from "react";
import { Database, Download, Loader2, Trash2 } from "lucide-react";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/auth/AuthContext";
import { PermissionPopup } from "@/components/ConfigEditor";

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
    {items === null ? <div className="res-loading"><Loader2 size={14} className="spin" />Loading backups…</div>
      : <div className="res-table" data-testid="backups-table"><table><thead><tr><th>FILE</th><th>SIZE</th><th>SECTIONS</th><th>BY</th><th>CREATED</th><th></th></tr></thead><tbody>
        {items.length === 0 && <tr><td colSpan={6} className="res-empty">No snapshots yet.</td></tr>}
        {items.map((b, i) => <tr key={b.id} data-testid={`backup-row-${i}`}><td className="mono">{b.filename}</td><td className="mono">{(b.size / 1024).toFixed(1)} KB</td><td className="muted">{(b.sections || []).length}</td><td className="muted">{b.created_by_email}</td><td className="muted">{new Date(b.created_at).toLocaleString()}</td>
          <td><div className="row-actions"><button className="icon-btn" title="Download" onClick={() => download(b)} data-testid={`backup-download-${i}`}><Download size={14} /></button>{can("backups", "write") && <button className="icon-btn tg-del" title="Delete" onClick={() => remove(b)} disabled={busy === b.id} data-testid={`backup-delete-${i}`}><Trash2 size={14} /></button>}</div></td></tr>)}
      </tbody></table></div>}
    <PermissionPopup error={permErr} onClose={() => setPermErr(null)} onGoSettings={onGoSettings} />
  </>;
}
