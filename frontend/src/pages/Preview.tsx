import { useEffect, useState } from "react";
import { api } from "../lib/api";

const PAGES: [string, string][] = [
  ["/", "Home"], ["/start", "Where to?"], ["/ideas", "Ideas"], ["/trips", "My trips"], ["/wardrobe", "Closet"], ["/trails", "Trekking"],
];

/** The same page as a phone and as a computer, side by side. Both frames are this app,
 *  so they share your session: change something in one, reload the other.
 *  `/phone` (only="phone") shows just the phone, as big as the screen allows: the app to use
 *  as on a phone, on the computer (Manu 2026-11-15). */
export default function Preview({ only }: { only?: "phone" } = {}) {
  const [pages, setPages] = useState(PAGES);
  const [path, setPath] = useState("/");
  const [n, setN] = useState(0);
  const [k, setK] = useState(1);
  useEffect(() => {
    if (!only) return;
    const fit = () => setK(Math.min(1.25, Math.max(0.5, (window.innerHeight - 110) / 868)));
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [only]);

  useEffect(() => {
    api.trips().then((ts) => {
      if (ts.length) setPages([...PAGES, ...ts.slice(0, 4).flatMap((t) => [
        [`/trips/${t.id}`, `${t.name} · plan`], [`/trips/${t.id}#bag`, `${t.name} · pack`]] as [string, string][])]);
    }).catch(() => undefined);
  }, []);

  if (only === "phone") return (
    <main className="pv pv-only">
      <header className="pv-bar">
        <b>Phone</b>
        <select value={path} onChange={(e) => { setPath(e.target.value); setN(n + 1); }} aria-label="Page">
          {pages.map(([p, l]) => <option key={p} value={p}>{l}</option>)}
        </select>
        <button type="button" className="btn sm" onClick={() => setN(n + 1)}>Back to this page</button>
        <a className="btn sm" href="/preview">Phone and computer</a>
      </header>
      <div className="pv-stage">
        <div className="pv-phone-box" style={{ width: 414 * k, height: 868 * k }}>
          <iframe key={`o${n}${path}`} src={path} title="Phone" width={390} height={844} style={{ transform: `scale(${k})` }} />
        </div>
      </div>
    </main>
  );

  return (
    <main className="pv">
      <header className="pv-bar">
        <b>Preview</b>
        <select value={path} onChange={(e) => setPath(e.target.value)} aria-label="Page">
          {pages.map(([p, l]) => <option key={p} value={p}>{l}</option>)}
        </select>
        <input value={path} onChange={(e) => setPath(e.target.value)} aria-label="Address" />
        <button type="button" className="btn sm" onClick={() => setN(n + 1)}>Reload both</button>
      </header>
      <div className="pv-stage">
        <figure className="pv-phone">
          <iframe key={`p${n}${path}`} src={path} title="Phone" width={390} height={844} />
          <figcaption>Phone · 390 × 844</figcaption>
        </figure>
        <figure className="pv-desk">
          <div className="pv-desk-in"><iframe key={`d${n}${path}`} src={path} title="Computer" width={1366} height={860} /></div>
          <figcaption>Computer · 1366 × 860</figcaption>
        </figure>
      </div>
    </main>
  );
}
