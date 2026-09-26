import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import { errorText } from "@/lib/api";

export default function AuthCallback() {
  const location = useLocation();
  const navigate = useNavigate();
  const { exchangeSession } = useAuth();
  const processed = useRef(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;
    const params = new URLSearchParams(location.hash.replace(/^#/, ""));
    const sessionId = params.get("session_id");
    if (!sessionId) { navigate("/login", { replace: true }); return; }
    exchangeSession(sessionId)
      .then(() => { window.history.replaceState({}, "", location.pathname); navigate("/", { replace: true }); })
      .catch(err => setError(errorText(err, "Google sign-in failed")));
  }, [location, navigate, exchangeSession]);

  return <div className="login-page" data-testid="auth-callback">
    <div className="login-card">
      {error ? <><div className="res-error">{error}</div><button className="button secondary" onClick={() => navigate("/login", { replace: true })} data-testid="auth-callback-back">Back to sign in</button></>
        : <div className="res-loading"><Loader2 size={14} className="spin" />Completing Google sign-in…</div>}
    </div>
  </div>;
}
