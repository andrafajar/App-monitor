import { useEffect, useRef, useState } from "react";
import { Loader2, Plug, Radar, RefreshCw } from "lucide-react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { api, API, TOKEN_KEY } from "@/lib/api";

const WS_BASE = API.replace(/^http/, "ws");

export function SshTerminal({ routerId, routerName, proto = "ssh", port }) {
  const holder = useRef(null);
  const [state, setState] = useState("connecting");
  const [attempt, setAttempt] = useState(0);
  const [diag, setDiag] = useState(null);
  const [checking, setChecking] = useState(false);
  const shownPort = port || (proto === "telnet" ? 23 : 22);

  const checkPorts = async () => {
    setChecking(true);
    try { const r = await api.get(`/routers/${routerId}/port-check`); setDiag(r.data); }
    catch { setDiag({ error: "Port check failed" }); } finally { setChecking(false); }
  };

  useEffect(() => {
    const host = holder.current;
    const term = new Terminal({ fontSize: 13, fontFamily: "'DM Mono', 'SFMono-Regular', Menlo, monospace", cursorBlink: true, scrollback: 4000, allowProposedApi: true,
      theme: { background: "#080d16", foreground: "#dbe7f3", cursor: "#38bdf8", selectionBackground: "#1e3a5f" } });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(host);
    let live = true;
    const safeFit = () => {
      if (!live || !host || host.clientHeight < 40) return null;
      try { fit.fit(); return { cols: term.cols, rows: term.rows }; } catch { return null; }
    };
    const fitTimer = setTimeout(safeFit, 120);

    const token = localStorage.getItem(TOKEN_KEY) || "";
    const socket = new WebSocket(`${WS_BASE}/routers/${routerId}/ssh?proto=${proto}&token=${encodeURIComponent(token)}&cols=${term.cols}&rows=${term.rows}`);
    socket.binaryType = "arraybuffer";
    socket.onopen = () => setState("dialing");
    socket.onmessage = (event) => {
      if (!live) return;
      if (typeof event.data === "string") {
        if (event.data.startsWith("\u0000")) { const ctrl = JSON.parse(event.data.slice(1)); setState(ctrl.type === "ready" ? "open" : "failed"); return; }
        term.write(event.data);
      } else term.write(new Uint8Array(event.data));
    };
    socket.onerror = () => setState("error");
    socket.onclose = () => setState(s => (s === "open" || s === "dialing" ? "closed" : s));

    const keys = term.onData(data => { if (socket.readyState === WebSocket.OPEN) socket.send(data); });
    let raf = 0;
    const resize = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const size = safeFit();
        if (size && socket.readyState === WebSocket.OPEN) socket.send(`\u0000${JSON.stringify({ type: "resize", ...size })}`);
      });
    };
    window.addEventListener("resize", resize);
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    term.focus();

    return () => {
      live = false;
      clearTimeout(fitTimer); cancelAnimationFrame(raf);
      observer.disconnect();
      window.removeEventListener("resize", resize);
      keys.dispose();
      socket.onmessage = null; socket.onclose = null; socket.onerror = null; socket.onopen = null;
      try { socket.close(); } catch { /* already closed */ }
      setTimeout(() => { try { term.dispose(); } catch { /* disposed */ } }, 0);
    };
  }, [routerId, proto, attempt]);

  useEffect(() => { if (state === "failed" || state === "error") checkPorts(); }, [state]); // eslint-disable-line react-hooks/exhaustive-deps

  const blocked = diag?.ports?.find(p => p.service === proto && p.state !== "open");

  const label = proto === "telnet" ? "Telnet" : "SSH";
  const shown = { open: `${label} session live · ${routerName}:${shownPort}`, connecting: `Opening ${label} session…`, dialing: `Dialing ${label} ${shownPort}…`,
    failed: `${label} could not connect — see the message below`, closed: "Session closed", error: "Connection error" }[state] || state;

  return <div className="ssh-wrap" data-testid={`shell-terminal-${proto}`}>
    <div className="res-toolbar">
      <b data-testid="ssh-state">{shown}</b>
      <div className="res-tools">
        <span className={`ws-dot ${state === "open" ? "on" : "off"}`} />
        <button className="button secondary compact" onClick={checkPorts} disabled={checking} data-testid="ssh-port-check">{checking ? <Loader2 size={13} className="spin" /> : <Radar size={13} />}Check ports</button>
        {state === "connecting" || state === "dialing" ? <Loader2 size={14} className="spin" /> : <button className="button secondary compact" onClick={() => { setState("connecting"); setDiag(null); setAttempt(a => a + 1); }} data-testid="ssh-reconnect">{state === "open" ? <><RefreshCw size={13} />Restart</> : <><Plug size={13} />Reconnect</>}</button>}
      </div>
    </div>
    <div className="ssh-host" ref={holder} data-testid="ssh-screen" />
    {blocked && <div className="port-blocked" data-testid="ssh-blocked-hint">
      <b>{label} port {blocked.port} is {blocked.state === "refused" ? "closed" : "blocked"} for NetPulse.</b>
      <span>The server dials from <b className="mono">{diag.from_ip}</b> — your own PC being able to connect does not help. On the device allow that IP:
        {" "}<code>/ip service set {proto} address={diag.from_ip}/32 port={blocked.port} disabled=no</code> and add a matching accept rule in <code>/ip firewall filter</code> (chain=input dst-port={blocked.port}).</span>
    </div>}
    {diag && <div className="port-diag" data-testid="ssh-port-diag">
      {diag.error ? <span>{diag.error}</span> : <>
        <span>NetPulse dials <b className="mono">{diag.host}</b> from <b className="mono">{diag.from_ip}</b> — that IP (not your PC) must be allowed in <code>/ip firewall filter</code> and in <code>/ip service</code> “Available From”.</span>
        <div className="port-pills">{diag.ports.map(p => <span key={p.service} className={`tg-pill ${p.state === "open" ? "on" : "off"}`} data-testid={`port-${p.service}`}>{p.service} {p.port} · {p.state}</span>)}</div>
      </>}
    </div>}
    <p className="backup-note">A genuine RouterOS shell over {label} using your own MikroTik credentials — prompt, <code>?</code> help, Tab completion and colours behave like Winbox' New Terminal. Ports are set per router in <b>Edit router</b>.</p>
  </div>;
}
