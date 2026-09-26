import { useCallback, useEffect, useState } from "react";
import { Activity, Loader2, Radar, Save, Stethoscope, Wifi } from "lucide-react";
import { api, errorText } from "@/lib/api";

const fmt = (v) => (v === null || v === undefined ? "—" : Number(v).toFixed(2));

export function SnmpPanel({ deviceId, deviceName, onNotice }) {
  const [state, setState] = useState(null);
  const [form, setForm] = useState({ enabled: false, community: "", port: "161" });
  const [record, setRecord] = useState({ mode: "auto", interfaces: [] });
  const [busy, setBusy] = useState("");
  const [diag, setDiag] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get(`/devices/${deviceId}/snmp`);
      setState(r.data);
      setForm({ enabled: !!r.data.config.enabled, community: "", port: String(r.data.config.port || 161) });
      setRecord({ mode: r.data.config.record_mode || "auto", interfaces: r.data.config.recorded || [] });
    } catch (e) { onNotice?.(errorText(e, "Could not read SNMP settings")); }
  }, [deviceId, onNotice]);
  useEffect(() => { load(); }, [load]);

  const save = async (e) => {
    e.preventDefault(); setBusy("save");
    try {
      const body = { enabled: form.enabled, port: parseInt(form.port, 10) || 161 };
      if (form.community) body.community = form.community;
      await api.put(`/devices/${deviceId}/snmp`, body);
      onNotice?.(`SNMP v2c ${form.enabled ? "enabled" : "disabled"} for ${deviceName}`);
      await load();
    } catch (err) { onNotice?.(errorText(err, "Saving SNMP settings failed")); }
    finally { setBusy(""); }
  };
  const scan = async () => {
    setBusy("scan");
    try {
      const r = await api.post(`/devices/${deviceId}/snmp/scan`);
      onNotice?.(r.data.ok ? `SNMP sweep done · ${r.data.snmp.interfaces?.length || 0} interfaces` : `SNMP failed: ${r.data.snmp.error}`);
      await load();
    } catch (err) { onNotice?.(errorText(err, "SNMP scan failed")); }
    finally { setBusy(""); }
  };

  const diagnose = async () => {
    setBusy("diag");
    try { const r = await api.get(`/devices/${deviceId}/snmp/diagnose`); setDiag(r.data); }
    catch (err) { onNotice?.(errorText(err, "Diagnosis failed")); }
    finally { setBusy(""); }
  };

  const saveRecord = async (patch) => {
    const next = { mode: record.mode, interfaces: record.interfaces, ...patch };
    setBusy("record");
    try {
      const r = await api.put(`/devices/${deviceId}/snmp/recorded`, next);
      setRecord({ mode: r.data.config.record_mode, interfaces: r.data.config.recorded });
      onNotice?.(next.mode === "auto" ? "Auto-scan on — newly discovered interfaces are added automatically, without duplicates" : `Recording ${r.data.config.recorded.length} selected interfaces`);
    } catch (err) { onNotice?.(errorText(err, "Could not update the recorded interfaces")); }
    finally { setBusy(""); }
  };
  const toggleIface = (name) => setRecord(r => ({ ...r, interfaces: r.interfaces.includes(name) ? r.interfaces.filter(n => n !== name) : [...r.interfaces, name] }));

  if (!state) return <div className="res-loading"><Loader2 size={14} className="spin" />Loading monitoring state…</div>;
  const snmp = state.snmp || {};
  const ifaces = snmp.interfaces || [];

  return <div className="snmp-wrap" data-testid="snmp-panel">
    <div className="snmp-stats">
      <div className="snmp-stat" data-testid="snmp-ping"><span>ICMP ping</span><b>{state.ping?.ms ? `${state.ping.ms} ms` : "no reply"}</b><small>{state.ping?.loss ?? 100}% loss · every 60s</small></div>
      <div className="snmp-stat" data-testid="snmp-cpu"><span>CPU load</span><b>{snmp.cpu ? `${snmp.cpu}%` : "—"}</b><small>hrProcessorLoad average</small></div>
      <div className="snmp-stat" data-testid="snmp-sysname"><span>System name</span><b>{snmp.sysname || "—"}</b><small>{snmp.uptime || "uptime unknown"}</small></div>
      <div className="snmp-stat" data-testid="snmp-count"><span>Interfaces</span><b>{ifaces.length}</b><small>{snmp.polled_at ? `polled ${new Date(snmp.polled_at).toLocaleTimeString()}` : "never polled"}</small></div>
    </div>

    <form className="snmp-form" onSubmit={save}>
      <label className="ssl-toggle"><input type="checkbox" checked={form.enabled} onChange={e => setForm(f => ({ ...f, enabled: e.target.checked }))} data-testid="snmp-enabled" /><span>Enable SNMP v2c polling (1 min)</span></label>
      <label>Community<input value={form.community} onChange={e => setForm(f => ({ ...f, community: e.target.value }))} placeholder={state.config.configured ? "•••••• (leave blank to keep)" : "public"} autoComplete="off" data-testid="snmp-community" /></label>
      <label>UDP port<input type="number" min={1} max={65535} value={form.port} onChange={e => setForm(f => ({ ...f, port: e.target.value }))} data-testid="snmp-port" /></label>
      <div className="snmp-actions">
        <button type="submit" className="button primary compact" disabled={busy === "save"} data-testid="snmp-save"><Save size={13} />{busy === "save" ? "Saving…" : "Save"}</button>
        <button type="button" className="button secondary compact" onClick={scan} disabled={busy === "scan"} data-testid="snmp-scan">{busy === "scan" ? <Loader2 size={13} className="spin" /> : <Radar size={13} />}Scan now</button>
        <button type="button" className="button secondary compact" onClick={diagnose} disabled={busy === "diag"} data-testid="snmp-diagnose">{busy === "diag" ? <Loader2 size={13} className="spin" /> : <Stethoscope size={13} />}Diagnose</button>
      </div>
    </form>

    {snmp.error && <div className="res-error" data-testid="snmp-error">{snmp.error}</div>}
    {diag && <div className={diag.answering ? "port-diag" : "port-blocked"} data-testid="snmp-diag">
      <b>{diag.answering ? `udp/${diag.port} answers: ${diag.detail}` : `No SNMP answer on udp/${diag.port} (ping ${diag.ping.alive ? `${diag.ping.rtt_ms} ms` : "failed"}).`}</b>
      {!diag.answering && <span>NetPulse queries from <b className="mono">{diag.from_ip}</b> — allow that IP, not your PC. {diag.hint}</span>}
    </div>}

    <div className="record-box" data-testid="snmp-record">
      <div className="record-head">
        <b>Recorded interfaces (30-day history)</b>
        <div className="record-modes">
          <label className={record.mode === "auto" ? "on" : ""}><input type="radio" name="rec-mode" checked={record.mode === "auto"} onChange={() => saveRecord({ mode: "auto" })} disabled={busy === "record"} data-testid="record-mode-auto" />Auto-scan &amp; add new</label>
          <label className={record.mode === "manual" ? "on" : ""}><input type="radio" name="rec-mode" checked={record.mode === "manual"} onChange={() => setRecord(r => ({ ...r, mode: "manual" }))} disabled={busy === "record"} data-testid="record-mode-manual" />Choose manually</label>
        </div>
      </div>
      <p className="muted">{record.mode === "auto"
        ? "Every SNMP sweep appends interfaces it has not seen before — existing entries are never duplicated or reset."
        : "Only the interfaces you tick are written to history; new interfaces found later are ignored until you add them."}</p>
      <div className="record-list">
        {ifaces.length === 0 && <span className="muted">Run “Scan now” first to discover interfaces.</span>}
        {ifaces.map(i => <label key={i.name} className={`record-chip ${record.interfaces.includes(i.name) ? "on" : ""}`} data-testid={`record-iface-${i.name}`}>
          <input type="checkbox" checked={record.interfaces.includes(i.name)} disabled={record.mode === "auto" || busy === "record"} onChange={() => toggleIface(i.name)} />
          {i.name}<small>{i.status}</small>
        </label>)}
      </div>
      {record.mode === "manual" && <div className="snmp-actions">
        <button className="button primary compact" onClick={() => saveRecord({})} disabled={busy === "record"} data-testid="record-save"><Save size={13} />Save selection ({record.interfaces.length})</button>
        <button className="button secondary compact" onClick={() => setRecord(r => ({ ...r, interfaces: ifaces.map(i => i.name) }))} data-testid="record-all">Select all scanned</button>
      </div>}
    </div>
    <div className="res-table" data-testid="snmp-table">
      <table><thead><tr><th>IDX</th><th>INTERFACE</th><th>STATUS</th><th>RX Mbps</th><th>TX Mbps</th></tr></thead><tbody>
        {ifaces.length === 0 && <tr><td colSpan={5} className="res-empty">No interfaces scanned yet — enable SNMP and press “Scan now”.</td></tr>}
        {ifaces.map(i => <tr key={i.index} data-testid={`snmp-iface-${i.index}`}>
          <td className="mono">{i.index}</td>
          <td><div className="router-name"><div className={`router-icon ${i.status === "up" ? "green" : "amber"}`}><Wifi size={13} /></div><div><b>{i.name}</b></div></div></td>
          <td><span className={`tg-pill ${i.status === "up" ? "on" : "off"}`}>{i.status}</span></td>
          <td className="mono">{fmt(i.rx_mbps)}</td><td className="mono">{fmt(i.tx_mbps)}</td>
        </tr>)}
      </tbody></table>
    </div>
    <p className="backup-note"><Activity size={13} /> Ping runs every 60 seconds and SNMP every minute from the NetPulse server; interface counters, CPU and ping history are kept for 30 days and then deleted automatically.</p>
  </div>;
}
