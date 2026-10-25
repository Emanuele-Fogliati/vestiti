import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";

type Stats = {
  users: number; guests: number; trips: number; products_active: number; clicks_30d: number;
  clicks_by_network: { network: string; kind: string; tracked: boolean; count: number }[];
  top_products_30d: { brand: string; name: string; clicks: number }[];
  affiliates: { network: string; configured: boolean }[];
};

export default function Admin() {
  const { user, toast } = useApp();
  const [stats, setStats] = useState<Stats | null>(null);
  const [feeds, setFeeds] = useState<{ networks: string[]; imports: Record<string, unknown>[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    api.adminStats().then((s) => setStats(s as unknown as Stats)).catch((e) => setErr(e.message));
    api.adminFeeds().then(setFeeds).catch(() => undefined);
  };
  useEffect(load, []);

  if (!user?.is_admin) return <main className="page"><div className="wrap"><p>Admins only.</p></div></main>;

  async function upload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api.adminImport(new FormData(e.currentTarget));
      toast(`Imported: ${r.created} new, ${r.updated} updated, ${r.skipped} skipped.`);
      load();
    } catch (e2) { setErr((e2 as Error).message); } finally { setBusy(false); }
  }

  return (
    <main className="page">
      <div className="wrap stack">
        <div className="page-head"><div><p className="kicker">Operations</p><h1>Admin</h1></div></div>
        {err && <p className="err">{err}</p>}
        {stats && (
          <>
            <div className="kpis">
              <div className="kpi"><span className="label">Accounts</span><b>{stats.users}</b></div>
              <div className="kpi"><span className="label">Guests</span><b>{stats.guests}</b></div>
              <div className="kpi"><span className="label">Trips</span><b>{stats.trips}</b></div>
              <div className="kpi"><span className="label">Active products</span><b>{stats.products_active}</b></div>
              <div className="kpi"><span className="label">Shop clicks, 30 d</span><b>{stats.clicks_30d}</b></div>
            </div>
            <div className="cols">
              <section className="panel">
                <h2 style={{ fontSize: 18, marginBottom: 10 }}>Clicks by network</h2>
                <table className="simple"><thead><tr><th>Network</th><th>Kind</th><th>Tracked</th><th>Clicks</th></tr></thead>
                  <tbody>{stats.clicks_by_network.map((c, i) => <tr key={i}><td>{c.network}</td><td>{c.kind}</td><td>{c.tracked ? "yes" : "NO: no commission"}</td><td>{c.count}</td></tr>)}</tbody></table>
                <h2 style={{ fontSize: 18, margin: "20px 0 10px" }}>Top products, 30 d</h2>
                <table className="simple"><tbody>{stats.top_products_30d.map((p, i) => <tr key={i}><td>{p.brand} {p.name}</td><td>{p.clicks}</td></tr>)}</tbody></table>
              </section>
              <section className="panel">
                <h2 style={{ fontSize: 18, marginBottom: 10 }}>Affiliate networks</h2>
                <table className="simple"><tbody>{stats.affiliates.map((a) => <tr key={a.network}><td>{a.network}</td><td>{a.configured ? "configured" : "not configured (links untracked)"}</td></tr>)}</tbody></table>
              </section>
            </div>
          </>
        )}
        <section className="panel">
          <h2 style={{ fontSize: 18, marginBottom: 10 }}>Import a product feed</h2>
          <form className="form" onSubmit={upload}>
            <div className="grid3">
              <div className="field"><label>Network</label>
                <select name="network">{(feeds?.networks ?? ["awin", "impact", "cj", "amazon", "generic", "json"]).map((n) => <option key={n}>{n}</option>)}</select></div>
              <div className="field"><label>File (CSV, TSV, gz or JSON)</label><input type="file" name="file" required /></div>
              <label className="check" style={{ alignSelf: "end" }}><input type="checkbox" name="deactivate_missing" value="true" defaultChecked /> Deactivate products missing from this feed</label>
            </div>
            <div><button className="btn primary" type="submit" disabled={busy}>{busy ? <span className="spin" /> : "Import"}</button></div>
          </form>
          {feeds && (
            <table className="simple" style={{ marginTop: 16 }}>
              <thead><tr><th>When</th><th>Network</th><th>File</th><th>Rows</th><th>New</th><th>Updated</th><th>Skipped</th><th>Off</th></tr></thead>
              <tbody>{feeds.imports.map((f) => (
                <tr key={String(f.id)}><td>{String(f.started_at).slice(0, 16).replace("T", " ")}</td><td>{String(f.network)}</td><td>{String(f.filename)}</td>
                  <td>{String(f.rows)}</td><td>{String(f.created)}</td><td>{String(f.updated)}</td><td>{String(f.skipped)}</td><td>{String(f.deactivated)}</td></tr>
              ))}</tbody>
            </table>
          )}
        </section>
      </div>
    </main>
  );
}
