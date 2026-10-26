import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";

export default function Account() {
  const { user, setUser, toast } = useApp();
  const nav = useNavigate();
  const [offset, setOffset] = useState(user?.thermal_offset ?? 0);
  const [curPw, setCurPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [pwErr, setPwErr] = useState<string | null>(null);
  if (!user) return <main className="page"><div className="wrap"><p>You're not signed in. <Link to="/login">Sign in</Link> or <Link to="/trips/new">start as a guest</Link>.</p></div></main>;

  async function patch(p: Parameters<typeof api.updateMe>[0]) {
    setUser(await api.updateMe(p));
    toast("Saved. Your trips use it from now on.");
  }

  async function exportData() {
    const data = await api.exportMe();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "my-data.json";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function changePw(e: React.FormEvent) {
    e.preventDefault();
    setPwErr(null);
    try {
      setUser(await api.changePassword(newPw, curPw));
      setCurPw(""); setNewPw("");
      toast("Password saved. Other devices are signed out.");
    } catch (e2) { setPwErr((e2 as Error).message); }
  }

  async function everywhere() {
    if (!window.confirm("Sign out on every device, this one included?")) return;
    await api.logoutEverywhere();
    setUser(null);
    nav("/login");
  }

  async function del() {
    if (!window.confirm("Delete your account, trips and wardrobe? This cannot be undone.")) return;
    await api.deleteMe();
    setUser(null);
    nav("/");
  }

  return (
    <main className="page">
      <div className="wrap" style={{ maxWidth: 720 }}>
        <p className="kicker">{user.is_guest ? "Guest" : user.email}</p>
        <h1 style={{ fontSize: 40, marginBottom: 24 }}>Account</h1>
        {user.is_guest && (
          <div className="banner info" style={{ marginBottom: 20 }}>
            You're a guest: your trips live in this browser's session. <Link to="/register">Create a free account</Link> to keep them.
          </div>
        )}
        <div className="stack">
          <section className="panel form">
            <h2 style={{ fontSize: 20 }}>Fit</h2>
            <div className="field"><label>Show products cut for</label>
              <select value={user.gender_pref} onChange={(e) => patch({ gender_pref: e.target.value as "men" | "women" | "any" })}>
                <option value="any">Everyone (men's, women's and unisex)</option>
                <option value="women">Women's and unisex</option>
                <option value="men">Men's and unisex</option>
              </select></div>
            <div className="field"><label>Do you run cold or warm? ({offset > 0 ? `+${offset.toFixed(2)}` : offset.toFixed(2)} clo)</label>
              <input type="range" min={-0.3} max={0.3} step={0.05} value={offset} onChange={(e) => setOffset(Number(e.target.value))}
                onMouseUp={() => patch({ thermal_offset: offset })} onTouchEnd={() => patch({ thermal_offset: offset })} onKeyUp={() => patch({ thermal_offset: offset })} />
              <div className="row small muted"><span>I run warm</span><span className="spacer" /><span>Average</span><span className="spacer" /><span>I run cold</span></div>
            </div>
            <div className="field"><label>Your pace on the move</label>
              <select value={user.pace} onChange={(e) => patch({ pace: e.target.value as "relaxed" | "average" | "brisk" })}>
                <option value="relaxed">Slow, lots of photo stops</option>
                <option value="average">Average</option>
                <option value="brisk">Fast, I rarely stop</option>
              </select></div>
            <div className="field"><label>Evenings</label>
              <select value={user.evenings} onChange={(e) => patch({ evenings: e.target.value as "early" | "sometimes" | "late" })}>
                <option value="early">Back inside after dinner: don't buy anything for cold evenings</option>
                <option value="sometimes">Out some evenings: spend a little on them</option>
                <option value="late">Out late most evenings: cover them fully</option>
              </select></div>
          </section>
          {!user.is_guest && (
            <section className="panel form">
              <h2 style={{ fontSize: 20 }}>Sign-in</h2>
              <form className="stack" onSubmit={changePw}>
                <p className="small muted">Signed in as <b>{user.email}</b>. You can always sign in with a link sent to this email, too.</p>
                <div className="field"><label htmlFor="cpw">Current password (leave empty if you never set one)</label>
                  <input id="cpw" type="password" value={curPw} maxLength={200} onChange={(e) => setCurPw(e.target.value)} autoComplete="current-password" /></div>
                <div className="field"><label htmlFor="npw">New password</label>
                  <input id="npw" type="password" required minLength={8} maxLength={200} value={newPw} onChange={(e) => setNewPw(e.target.value)} autoComplete="new-password" />
                  <span className="small muted">At least 8 characters. Other devices are signed out when you change it.</span></div>
                {pwErr && <p className="err" role="alert">{pwErr}</p>}
                <div className="row">
                  <button className="btn" type="submit">Save password</button>
                  <span className="spacer" />
                  <button className="btn ghost" type="button" onClick={everywhere}>Sign out on all devices</button>
                </div>
              </form>
            </section>
          )}
          <section className="panel stack">
            <h2 style={{ fontSize: 20 }}>Your data</h2>
            <p className="small muted">Download everything we store about you, or delete it all. Clicks on shop links are kept anonymously for affiliate accounting.</p>
            <div className="row">
              <button className="btn" type="button" onClick={exportData}>Download my data</button>
              <button className="btn danger" type="button" onClick={del}>Delete account</button>
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
