import { useEffect, useState } from "react";
import { Check, Loader2, Save, Send, ShieldCheck, Trash2 } from "lucide-react";
import { api, errorText, slug } from "@/lib/api";
import { useAuth } from "@/auth/AuthContext";

function RoleTelegramRow({ item, onChanged, onNotice, canWrite }) {
  const [botToken, setBotToken] = useState("");
  const [chatId, setChatId] = useState(item.chat_id || "");
  const [enabled, setEnabled] = useState(item.enabled ?? true);
  const [busy, setBusy] = useState("");
  const key = slug(item.role_name);
  const save = async () => {
    if (!botToken) { onNotice("Paste the bot token to save (tokens are never shown again)"); return; }
    setBusy("save");
    try { await api.put(`/notifications/telegram/${item.role_id}`, { bot_token: botToken, chat_id: chatId, enabled }); setBotToken(""); onNotice(`${item.role_name}: Telegram config saved`); onChanged(); }
    catch (e) { onNotice(errorText(e, "Save failed — check bot token and chat id format")); } finally { setBusy(""); }
  };
  const test = async () => {
    setBusy("test");
    try { await api.post(`/notifications/telegram/${item.role_id}/test`); onNotice(`${item.role_name}: test message delivered`); }
    catch (e) { onNotice(errorText(e, "Telegram send failed")); } finally { setBusy(""); }
  };
  const remove = async () => {
    setBusy("del");
    try { await api.delete(`/notifications/telegram/${item.role_id}`); onNotice(`${item.role_name}: Telegram config removed`); onChanged(); }
    catch (e) { onNotice(errorText(e, "Delete failed")); } finally { setBusy(""); }
  };
  return <div className="tg-row" data-testid={`tg-row-${key}`}>
    <div className="tg-head"><div><i className="group-dot" /><b>{item.role_name}</b></div>
      <div className="tg-status">{item.configured ? <span className="tg-pill on" data-testid={`tg-status-${key}`}><Check size={12} />{item.enabled ? "Enabled" : "Disabled"} · {item.token_hint}</span> : <span className="tg-pill off" data-testid={`tg-status-${key}`}>Not configured</span>}</div></div>
    {canWrite && <>
      <div className="tg-fields">
        <label>Bot token{item.configured && <em> (paste to replace)</em>}<input type="password" value={botToken} onChange={e => setBotToken(e.target.value)} placeholder="123456789:AA...zz" data-testid={`tg-token-${key}`} autoComplete="off" /></label>
        <label>Chat ID<input value={chatId} onChange={e => setChatId(e.target.value)} placeholder="-1001234567890" data-testid={`tg-chat-${key}`} /></label>
        <label className="tg-toggle"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} data-testid={`tg-enabled-${key}`} /><span>Deliver alarms</span></label>
      </div>
      <div className="tg-actions">
        <button className="button primary compact" onClick={save} disabled={busy === "save"} data-testid={`tg-save-${key}`}><Save size={13} />{busy === "save" ? "Saving..." : "Save"}</button>
        <button className="button secondary compact" onClick={test} disabled={!item.configured || busy === "test"} data-testid={`tg-test-${key}`}><Send size={13} />{busy === "test" ? "Sending..." : "Send test"}</button>
        {item.configured && <button className="tg-del" onClick={remove} disabled={busy === "del"} data-testid={`tg-delete-${key}`}><Trash2 size={13} />Remove</button>}
      </div>
    </>}
  </div>;
}

export default function NotificationsPanel({ onNotice }) {
  const { can } = useAuth();
  const [items, setItems] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const load = async () => { try { const r = await api.get("/notifications/telegram"); setItems(r.data?.items || []); } catch { setItems([]); } finally { setLoaded(true); } };
  useEffect(() => { load(); }, []);
  return <section className="panel notif-panel" data-testid="notifications-panel">
    <div className="panel-head"><div><p className="eyebrow">TELEGRAM DELIVERY · PER ROLE</p><h2>Role notification channels</h2></div><span className="api-lock"><ShieldCheck size={13} />Tokens encrypted at rest</span></div>
    <p className="notif-help">Create a bot with <b>@BotFather</b>, add it to the role's Telegram group/channel and send <b>/start</b>. Alarms for a router are delivered to every role whose device groups include that router's group.</p>
    {!loaded && <div className="res-loading"><Loader2 size={14} className="spin" />Loading Telegram configuration…</div>}
    {loaded && <div className="tg-list">{items.length === 0 && <span className="muted">Create a role first (Roles page).</span>}{items.map(it => <RoleTelegramRow key={it.role_id} item={it} onChanged={load} onNotice={onNotice} canWrite={can("notifications", "write")} />)}</div>}
  </section>;
}
