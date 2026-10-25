import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { api, type LinkSent } from "../lib/api";
import { useApp } from "../lib/app-context";

/** Where to go after signing in: the page that sent the traveller here, else their trips. */
function useNext() {
  const loc = useLocation();
  const from = (loc.state as { from?: string } | null)?.from;
  return from && from.startsWith("/") && !from.startsWith("//") ? from : "/trips";
}

/** Shown after "email me a link". On a local machine with no mail server the API hands the
 *  link back, so it can be opened right here. */
function LinkSentNote({ sent }: { sent: LinkSent }) {
  return (
    <div className="banner ok" role="status">
      <p>{sent.detail} Check your inbox (and the spam folder).</p>
      {sent.dev_link && (
        <p className="small" style={{ marginTop: 8 }}>
          Local test mode, no email server set up: <Link to={sent.dev_link}>open the link here</Link>.
        </p>
      )}
    </div>
  );
}

export default function Auth({ mode }: { mode: "login" | "register" }) {
  const { user, setUser, toast } = useApp();
  const nav = useNavigate();
  const next = useNext();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<LinkSent | null>(null);
  const guestHasWork = !!user?.is_guest;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const u = mode === "login" ? await api.login(email, password) : await api.register(email, password, name || undefined);
      setUser(u);
      toast(mode === "login" ? (guestHasWork ? "Welcome back. The trips you planned as a guest are in your account." : "Welcome back.")
        : guestHasWork ? "Account created. Your trips are saved to it." : "Account created.");
      nav(next);
    } catch (e2) { setErr((e2 as Error).message); } finally { setBusy(false); }
  }

  async function emailMeALink() {
    if (!email) { setErr("Write your email first."); return; }
    setBusy(true); setErr(null);
    try { setSent(await api.emailLink(email)); } catch (e2) { setErr((e2 as Error).message); } finally { setBusy(false); }
  }

  return (
    <main className="page">
      <div className="wrap" style={{ maxWidth: 520 }}>
        <p className="kicker">{mode === "login" ? "Welcome back" : "Free account"}</p>
        <h1 style={{ fontSize: 40, marginBottom: 12 }}>{mode === "login" ? "Sign in" : "Create account"}</h1>
        <p className="muted" style={{ marginBottom: 20 }}>
          {mode === "login" ? "Your trips, kits and wardrobe on any device." : "Keep your trips, kits and wardrobe on any device. Free, always."}
        </p>
        {guestHasWork && (
          <p className="banner info" style={{ marginBottom: 16 }}>
            {mode === "register" ? "The trips and wardrobe you made as a guest move into the new account."
              : "Signing in keeps what you planned as a guest: it moves into your account."}
          </p>
        )}
        <form className="form panel" onSubmit={submit}>
          {mode === "register" && (
            <div className="field"><label htmlFor="n">Name (optional)</label><input id="n" type="text" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} autoComplete="name" /></div>
          )}
          <div className="field"><label htmlFor="e">Email</label><input id="e" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></div>
          <div className="field">
            <div className="row"><label htmlFor="p">Password</label><span className="spacer" />
              {mode === "login" && <Link className="small" to="/forgot-password" state={{ email }}>Forgot it?</Link>}</div>
            <input id="p" type="password" required minLength={mode === "register" ? 8 : 1} maxLength={200} value={password}
              onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} />
            {mode === "register" && <span className="small muted">At least 8 characters.</span>}
          </div>
          {err && <p className="err" role="alert">{err}</p>}
          <button className="btn primary" type="submit" disabled={busy}>{busy ? <span className="spin" /> : mode === "login" ? "Sign in" : "Create account"}</button>
          <div className="or"><span>or</span></div>
          {sent ? <LinkSentNote sent={sent} /> : (
            <button className="btn" type="button" disabled={busy} onClick={emailMeALink}>
              {mode === "login" ? "Email me a sign-in link, no password" : "Sign up with just a link to my email"}
            </button>
          )}
          <p className="small">{mode === "login"
            ? <>No account? <Link to="/register" state={{ from: next }}>Create one</Link>, or just <Link to="/start">start planning</Link> as a guest.</>
            : <>Already have one? <Link to="/login" state={{ from: next }}>Sign in</Link>.</>}</p>
        </form>
      </div>
    </main>
  );
}

export function ForgotPassword() {
  const loc = useLocation();
  const [email, setEmail] = useState((loc.state as { email?: string } | null)?.email ?? "");
  const [sent, setSent] = useState<LinkSent | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { setSent(await api.forgotPassword(email)); } catch (e2) { setErr((e2 as Error).message); } finally { setBusy(false); }
  }

  return (
    <main className="page">
      <div className="wrap" style={{ maxWidth: 520 }}>
        <p className="kicker">Password</p>
        <h1 style={{ fontSize: 40, marginBottom: 20 }}>Forgot your password?</h1>
        <form className="form panel" onSubmit={submit}>
          <p className="small muted">We email you a link to choose a new one. It works once, for an hour.</p>
          <div className="field"><label htmlFor="fe">Email</label><input id="fe" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></div>
          {err && <p className="err" role="alert">{err}</p>}
          {sent ? <LinkSentNote sent={sent} /> : <button className="btn primary" type="submit" disabled={busy}>{busy ? <span className="spin" /> : "Email me a reset link"}</button>}
          <p className="small"><Link to="/login">Back to sign in</Link></p>
        </form>
      </div>
    </main>
  );
}

export function ResetPassword() {
  const { setUser, toast } = useApp();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== again) { setErr("The two passwords are not the same."); return; }
    setBusy(true); setErr(null);
    try {
      setUser(await api.resetPassword(token, password));
      toast("New password saved. You're signed in, and signed out everywhere else.");
      nav("/trips");
    } catch (e2) { setErr((e2 as Error).message); } finally { setBusy(false); }
  }

  return (
    <main className="page">
      <div className="wrap" style={{ maxWidth: 520 }}>
        <p className="kicker">Password</p>
        <h1 style={{ fontSize: 40, marginBottom: 20 }}>Choose a new password</h1>
        {!token ? <p className="err">This page needs the link from the email. <Link to="/forgot-password">Ask for a new one</Link>.</p> : (
          <form className="form panel" onSubmit={submit}>
            <div className="field"><label htmlFor="np">New password</label><input id="np" type="password" required minLength={8} maxLength={200} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
              <span className="small muted">At least 8 characters.</span></div>
            <div className="field"><label htmlFor="np2">Again</label><input id="np2" type="password" required minLength={8} maxLength={200} value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" /></div>
            {err && <p className="err" role="alert">{err} {err.includes("expired") && <Link to="/forgot-password">Ask for a new link</Link>}</p>}
            <button className="btn primary" type="submit" disabled={busy}>{busy ? <span className="spin" /> : "Save and sign in"}</button>
          </form>
        )}
      </div>
    </main>
  );
}

/** Opened from the sign-in email. The token is sent with a POST from here (not used by a
 *  plain GET), so mail scanners that preview links do not burn it. */
export function EmailLinkLanding() {
  const { setUser, toast } = useApp();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [err, setErr] = useState<string | null>(null);
  const once = useRef(false);

  useEffect(() => {
    if (once.current) return;
    once.current = true;
    if (!token) { setErr("This page needs the link from the email."); return; }
    api.verifyEmailLink(token)
      .then((u) => { setUser(u); toast("You're signed in."); nav("/trips", { replace: true }); })
      .catch((e) => setErr((e as Error).message));
  }, [token, setUser, toast, nav]);

  return (
    <main className="page">
      <div className="wrap" style={{ maxWidth: 520 }}>
        <h1 style={{ fontSize: 40, marginBottom: 20 }}>Signing you in</h1>
        {err ? <p className="err">{err} <Link to="/login">Back to sign in</Link></p> : <p className="loading"><span className="spin" /></p>}
      </div>
    </main>
  );
}
