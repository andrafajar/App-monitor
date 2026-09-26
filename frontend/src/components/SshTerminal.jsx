import { useEffect, useRef, useState } from "react";
import { Loader2, Plug, RefreshCw } from "lucide-react";
import { Terminal } from "xterm";
import { FitAddon } from "xterm-addon-fit";
import "xterm/css/xterm.css";
import { API, TOKEN_KEY } from "@/lib/api";

const WS_BASE = API.replace(/^http/, "ws");

export function SshTerminal({ routerId, routerName, sshPort }) {
  const holder = useRef(null);
  const termRef = useRef(null);
  const socketRef = useRef(null);
  const [state, setState] = useState("connecting");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const term = new Terminal({ fontSize: 13, fontFamily: "'JetBrains Mono', 'SFMono-Regular', Menlo, monospace", cursorBlink: true, convertEol: false, scrollback: 4000,
      theme: { background: "#080d16", foreground: "#dbe7f3", cursor: "#38bdf8", selectionBackground: "#1e3a5f" } });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(holder.current);
    setTimeout(() => { try { fit.fit(); } catch { /* not measured yet */ } }, 30);
    termRef.current = term;

    const token = localStorage.getItem(TOKEN_KEY) || "";
    const socket = new WebSocket(`${WS_BASE}/routers/${routerId}/ssh?token=${encodeURIComponent(token)}&cols=${term.cols}&rows=${term.rows}`);
    socket.binaryType = "arraybuffer";
    socketRef.current = socket;
    socket.onopen = () => setState("open");
    socket.onmessage = (event) => {
      if (typeof event.data === "string") term.write(event.data);
      else term.write(new Uint8Array(event.data));
    };
    socket.onerror = () => setState("error");
    socket.onclose = () => setState("closed");

    const keys = term.onData(data => { if (socket.readyState === WebSocket.OPEN) socket.send(data); });
    const resize = () => {
      try { fit.fit(); } catch { return; }
      if (socket.readyState === WebSocket.OPEN) socket.send(`\u0000${JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows })}`);
    };
    window.addEventListener("resize", resize);
    const observer = new ResizeObserver(resize);
    observer.observe(holder.current);

    return () => {
      window.removeEventListener("resize", resize); observer.disconnect(); keys.dispose();
      try { socket.close(); } catch { /* already closed */ }
      term.dispose();
    };
  }, [routerId, attempt]);

  return <div className="ssh-wrap" data-testid="ssh-terminal">
    <div className="res-toolbar">
      <b data-testid="ssh-state">{state === "open" ? `SSH session · ${routerName}:${sshPort || 22}` : state === "connecting" ? "Opening SSH session…" : state === "closed" ? "Session closed" : "Connection error"}</b>
      <div className="res-tools">
        <span className={`ws-dot ${state === "open" ? "on" : "off"}`} />
        {state === "connecting" ? <Loader2 size={14} className="spin" /> : <button className="button secondary compact" onClick={() => { setState("connecting"); setAttempt(a => a + 1); }} data-testid="ssh-reconnect">{state === "open" ? <><RefreshCw size={13} />Restart</> : <><Plug size={13} />Reconnect</>}</button>}
      </div>
    </div>
    <div className="ssh-host" ref={holder} data-testid="ssh-screen" />
    <p className="backup-note">A genuine RouterOS shell over SSH (port {sshPort || 22}) using your own MikroTik credentials — prompt, <code>?</code> help, Tab completion and colours all behave exactly like Winbox' New Terminal. If SSH is blocked, use <b>Terminal (API)</b> instead.</p>
  </div>;
}
