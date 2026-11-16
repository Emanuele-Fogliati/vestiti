import type { ReactElement } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { ArtCard } from "./ArtCard";
import { brandName, useApp } from "../lib/app-context";

/** Logo "Maglietta con la zip", Ponte ad arco (Manu 2026-11-15): a black T-shirt that is itself the T of
 *  Thruwear, with a yellow zip closed up to the collar. The teeth run the whole way down, the slider sits at the
 *  neck with a little arch on top, and the pull hangs from the arch a bit sideways ("il ciondolino storto").
 *  Colours: --logo-tee (shirt and outlines) and --logo-zip (zip), black and yellow by default.
 *  Manu's rule: it must always read as a zip. */
const TEETH = Array.from({ length: 11 }, (_, i) => ({ x: i % 2 === 0 ? 28.92 : 30.68, y: 20 + 3 * i }));
const ARCH = "M29.2 16.6V15.2Q29.2 13 32 13Q34.8 13 34.8 15.2V16.6";

export function LogoMark({ size = 36 }: { size?: number }) {
  const tee = "var(--logo-tee, #111111)";
  const zip = "var(--logo-zip, #FFD60A)";
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" style={{ flex: "0 0 auto" }}>
      <path d="M8 9H23Q32 17 41 9H56Q60 9 60 13V22Q60 25 57 25H46V57Q46 60 43 60H21Q18 60 18 57V25H7Q4 25 4 22V13Q4 9 8 9Z" fill={tee} />
      <g fill={zip} stroke={tee} strokeWidth="0.5">
        {TEETH.map((t) => <rect key={t.y} x={t.x} y={t.y} width="4.4" height="3.4" rx="1.02" />)}
      </g>
      <rect x="29" y="55.5" width="6" height="2.6" rx="0.8" fill={zip} />
      <path d="M27.2 12.5H36.8Q38 12.5 38 13.7L35.5 20Q35.5 21 34.5 21H29.5Q28.5 21 28.5 20L26 13.7Q26 12.5 27.2 12.5Z" fill={zip} stroke={tee} strokeWidth="0.5" />
      <path d="M29.36 17.18L32 20.2L34.64 17.18" fill="none" stroke={tee} strokeWidth="0.6" strokeLinecap="round" strokeLinejoin="round" />
      <g transform="rotate(-16 32 15)">
        <path d="M30.53 14.6H33.47L34.3 22.7A2.3 2.3 0 0 1 29.7 22.7Z" fill={zip} stroke={tee} strokeWidth="1.2" strokeLinejoin="round" />
        <rect x="31.22" y="19.38" width="1.56" height="3.95" rx="0.78" fill={tee} />
      </g>
      <path d={ARCH} fill="none" stroke={tee} strokeWidth="2.6" strokeLinecap="round" />
      <path d={ARCH} fill="none" stroke={zip} strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}

/** The shirt is the T: "[T]hruwear". A name that does not start with T gets the shirt in front of it. */
export function Logo({ name }: { name: string }) {
  const isT = /^t/i.test(name);
  return (
    <span className={`brand-lock${isT ? " is-t" : ""}`}>
      <LogoMark size={40} />
      <span className="brand-word">{isT ? name.slice(1) : name}</span>
    </span>
  );
}

const ICONS: Record<string, ReactElement> = {
  globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3.2 3.6 3.2 14.4 0 18M12 3c-3.2 3.6-3.2 14.4 0 18" /></>,
  trips: <><rect x="5" y="7" width="14" height="13" rx="3" /><path d="M9 7V4h6v3" /></>,
  treks: <path d="M3 19l6-11 4 6 2.5-3.5L21 19z" />,
  closet: <path d="M10 6a2 2 0 1 1 3 1.7c-.6.4-1 .9-1 1.6V10L3 17h18l-9-7" />,
  me: <><circle cx="12" cy="8" r="4" /><path d="M4 21c1-4 4.5-6 8-6s7 2 8 6" /></>,
};
const Ico = ({ n }: { n: string }) => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[n]}</svg>
);

/** Every page, Editoriale (Manu 2026-11-15).
 *  Computer: one bar on top, logo left (it goes home: Explore is not in the menu, Manu 2026-11-16),
 *  Trips · Walks · Closet in the middle, You on the right.
 *  Phone: nothing on top (no logo, no You: "c'è più spazio per tutto il resto"); one tab bar at the bottom
 *  with You as the fifth tab. Planning a trip lives under Trips; How it works and sign in live under You. */
export function Layout() {
  const { config, user } = useApp();
  const loc = useLocation();
  const name = brandName(config);
  const p = loc.pathname;
  const tripsOn = /^\/(start|ideas|trips)(\/|$)/.test(p);
  const signedIn = !!user && !user.is_guest;
  const dock: [string, string, string, boolean][] = [
    ["/", "Explore", "globe", p === "/"],
    ["/trips", "Trips", "trips", tripsOn],
    ["/trails", "Walks", "treks", /^\/trails(\/|$)/.test(p)],
    ["/wardrobe", "Closet", "closet", /^\/wardrobe(\/|$)/.test(p)],
  ];
  const meOn = /^\/(account|login|register|how-it-works)(\/|$)/.test(p);
  const meTo = signedIn || user?.is_guest ? "/account" : "/login";
  const meState = signedIn ? undefined : { from: p };

  return (
    <>
      <header className="top">
        <div className="wrap top-in">
          <Link className="logo" to="/" aria-label={`${name} home`}><Logo name={name} /></Link>
          <nav className="tnav" aria-label="Main">
            {dock.filter(([to]) => to !== "/").map(([to, label, , on]) => (
              <Link key={to} to={to} className={on ? "active" : ""} aria-current={on ? "page" : undefined}>{label}</Link>
            ))}
          </nav>
          <div className="acct">
            {user?.is_admin && <Link className="admin" to="/admin">Admin</Link>}
            <Link className={`me${meOn ? " active" : ""}`} to={meTo} state={meState}
              aria-label={signedIn ? `You: ${user!.display_name || user!.email}` : "You: sign in, how it works"} title={signedIn ? (user!.display_name || user!.email || undefined) : "You"}>
              <Ico n="me" />
            </Link>
          </div>
        </div>
      </header>
      <Outlet />
      <ArtCard />
      <nav className="dock" aria-label="Main">
        {dock.map(([to, label, icon, on]) => (
          <Link key={to} to={to} className={on ? "active" : ""} aria-current={on ? "page" : undefined}><Ico n={icon} />{label}</Link>
        ))}
        <Link to={meTo} state={meState} className={`dock-me${meOn ? " active" : ""}`} aria-current={meOn ? "page" : undefined}><Ico n="me" />You</Link>
      </nav>
      <footer>
        <div className="wrap">
          <nav aria-label="Legal">
            <Link to="/how-it-works">How it works</Link>
            <Link to="/legal/affiliate">Affiliate disclosure</Link>
            <Link to="/legal/privacy">Privacy</Link>
            <Link to="/legal/terms">Terms</Link>
          </nav>
          <p>{config?.disclosure}</p>
          <div className="row">
            <span>Weather: Open-Meteo. Product data: sample catalog until affiliate feeds are connected.</span>
          </div>
        </div>
      </footer>
    </>
  );
}
