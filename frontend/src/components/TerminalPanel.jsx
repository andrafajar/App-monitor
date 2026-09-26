import { useEffect, useRef, useState } from "react";
import { Terminal as TerminalIcon, Trash2 } from "lucide-react";
import { api, errorText } from "@/lib/api";
import { PermissionPopup } from "@/components/ConfigEditor";

const HELP = ["Type RouterOS-style commands, e.g.:", "  /ip address print", "  /interface print where type=ether", "  /ip firewall filter add chain=input action=drop comment=test", "  /ip address set *3 comment=uplink", "  /ip address remove *3", "  /interface disable *1", "Supported: print · get · add · set · remove · enable · disable. Writes need the 'RouterOS config' privilege and a MikroTik user with write policy."];

function fmtRow(row) { return Object.entries(row).map(([k, v]) => `${k}=${String(v).includes(" ") ? `"${v}"` : v}`).join(" "); }

export function TerminalPanel({ routerId, routerName, onGoSettings }) {
  const [lines, setLines] = useState(() => [{ t: "info", text: `NetPulse API terminal · ${routerName}` }, ...HELP.map(h => ({ t: "muted", text: h }))]);
  const [cmd, setCmd] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);
  const [hIdx, setHIdx] = useState(-1);
  const [permErr, setPermErr] = useState(null);
  const outRef = useRef(null);
  const inputRef = useRef(null);
  useEffect(() => { outRef.current?.scrollTo(0, outRef.current.scrollHeight); }, [lines]);

  const run = async (e) => {
    e?.preventDefault();
    const command = cmd.trim(); if (!command || busy) return;
    if (command === "clear") { setLines([]); setCmd(""); return; }
    setLines(l => [...l, { t: "cmd", text: `[${routerName}] > ${command}` }]);
    setHistory(h => [command, ...h.filter(x => x !== command)].slice(0, 50)); setHIdx(-1); setCmd(""); setBusy(true);
    try {
      const r = await api.post(`/routers/${routerId}/terminal`, { command });
      const rows = r.data.rows || [];
      const out = rows.length === 0 ? [{ t: "muted", text: r.data.write ? "ok" : "(no entries)" }]
        : rows.map((row, i) => ({ t: "row", text: `${String(i).padStart(2, " ")}  ${fmtRow(row)}` }));
      setLines(l => [...l, ...out, { t: "muted", text: `— ${rows.length} row${rows.length === 1 ? "" : "s"} · ${r.data.elapsed_ms} ms` }]);
    } catch (err) {
      const status = err.response?.status;
      if (status === 403 || status === 428 || status === 401) setPermErr(err);
      setLines(l => [...l, { t: "err", text: `error: ${errorText(err)}` }]);
    } finally { setBusy(false); inputRef.current?.focus(); }
  };
  const onKey = (e) => {
    if (e.key === "ArrowUp") { e.preventDefault(); const n = Math.min(hIdx + 1, history.length - 1); if (history[n] != null) { setHIdx(n); setCmd(history[n]); } }
    if (e.key === "ArrowDown") { e.preventDefault(); const n = hIdx - 1; setHIdx(n); setCmd(n < 0 ? "" : history[n]); }
  };
  return <div className="term" data-testid="terminal-panel">
    <div className="term-out" ref={outRef} data-testid="terminal-output">{lines.map((l, i) => <div key={i} className={`term-line ${l.t}`}>{l.text}</div>)}</div>
    <form className="term-in" onSubmit={run}>
      <TerminalIcon size={14} /><span className="term-prompt">{`[${routerName}] >`}</span>
      <input ref={inputRef} value={cmd} onChange={e => setCmd(e.target.value)} onKeyDown={onKey} placeholder="/ip address print" autoFocus spellCheck={false} disabled={busy} data-testid="terminal-input" />
      <button type="button" className="icon-btn" title="Clear" onClick={() => setLines([])} data-testid="terminal-clear"><Trash2 size={13} /></button>
      <button type="submit" className="button primary compact" disabled={busy} data-testid="terminal-run">{busy ? "…" : "Run"}</button>
    </form>
    <PermissionPopup error={permErr} onClose={() => setPermErr(null)} onGoSettings={onGoSettings} />
  </div>;
}
