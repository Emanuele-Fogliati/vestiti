import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";

export default function Auth({ mode }: { mode: "login" | "register" }) {
  const { user, setUser, toast } = useApp();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const u = mode === "login" ? await api.login(email, password) : await api.register(email, password, name || undefined);
      setUser(u);
      toast(mode === "login" ? "Welcome back." : user?.is_guest ? "Account created. Your trips are saved to it." : "Account created.");
      nav("/trips");
    } catch (e2) { setErr((e2 as Error).message); } finally { setBusy(false); }
  }

  return (
    <main className="page">
      <div className="wrap" style={{ maxWidth: 520 }}>
        <p className="kicker">{mode === "login" ? "Welcome back" : "Free account"}</p>
        <h1 style={{ fontSize: 40, marginBottom: 20 }}>{mode === "login" ? "Sign in" : "Create account"}</h1>
        {mode === "register" && user?.is_guest && <p className="banner info" style={{ marginBottom: 16 }}>Your guest trips and wardrobe move into the new account.</p>}
        <form className="form panel" onSubmit={submit}>
          {mode === "register" && (
            <div className="field"><label htmlFor="n">Name (optional)</label><input id="n" type="text" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></div>
          )}
          <div className="field"><label htmlFor="e">Email</label><input id="e" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></div>
          <div className="field"><label htmlFor="p">Password</label><input id="p" type="password" required minLength={mode === "register" ? 8 : 1} value={password}
            onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} />
            {mode === "register" && <span className="small muted">At least 8 characters.</span>}</div>
          {err && <p className="err">{err}</p>}
          <button className="btn primary" type="submit" disabled={busy}>{busy ? <span className="spin" /> : mode === "login" ? "Sign in" : "Create account"}</button>
          <p className="small">{mode === "login" ? <>No account? <Link to="/register">Create one</Link>, or just <Link to="/trips/new">start planning</Link> as a guest.</> : <>Already have one? <Link to="/login">Sign in</Link>.</>}</p>
          {mode === "login" && <p className="small muted">Forgot your password? Password reset by email is not live yet: write to support.</p>}
        </form>
      </div>
    </main>
  );
}
