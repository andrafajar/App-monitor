import { useState } from "react";
import { Navigate } from "react-router-dom";
import { Loader2, LogIn, Network } from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import { errorText } from "@/lib/api";

export default function Login() {
  const { user, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError("");
    try { await login(email.trim(), password); }
    catch (err) { setError(errorText(err, "Login failed")); }
    finally { setBusy(false); }
  };
  const google = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return <div className="login-page" data-testid="login-page">
    <div className="login-card">
      <div className="brand"><div className="brand-mark"><Network size={20} /></div><div><b>NETPULSE</b><span>mikrotik control plane</span></div></div>
      <h1>Sign in</h1>
      <p className="muted">Use your NetPulse account. Access to routers is scoped by your role and device groups.</p>
      <form onSubmit={submit} className="add-form">
        <label>Email<input type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="you@company.com" data-testid="login-email" autoComplete="username" /></label>
        <label>Password<input type="password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" data-testid="login-password" autoComplete="current-password" /></label>
        {error && <div className="res-error" data-testid="login-error">{error}</div>}
        <button type="submit" className="button primary" disabled={busy} data-testid="login-submit">{busy ? <Loader2 size={14} className="spin" /> : <LogIn size={14} />}{busy ? "Signing in..." : "Sign in"}</button>
      </form>
      <div className="login-divider"><span>or</span></div>
      <button type="button" className="button secondary" onClick={google} data-testid="login-google">Continue with Google</button>
    </div>
  </div>;
}
