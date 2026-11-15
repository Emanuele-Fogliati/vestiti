import { useId, type ReactElement } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { brandName, useApp } from "../lib/app-context";

/** Logo "Globo con cerniera" (Manu 2026-11-14): a yellow globe with a zip across it.
 *  The teeth, slider and pull are cut out of the globe (mask), so whatever is behind shows through
 *  on the night home and dark bars. On light paper (--logo-globe/--logo-teeth set in paper.css) the globe turns
 *  ink and the teeth yellow. Few, chunky teeth so it still reads as a zip at 20-36 px (Manu: "si deve sempre capire che è una zip"). */
export function LogoMark({ size = 36 }: { size?: number }) {
  const id = `zipglobe-${useId().replace(/:/g, "")}`;
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" style={{ flex: "0 0 auto" }}>
      <defs>
        <mask id={id} maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">
          <circle cx="32" cy="32" r="28" fill="#fff" />
          <g fill="#000">
            {[6, 16, 26].map((x) => (
              <g key={x}>
                <rect x={x} y="25.5" width="6" height="6.5" rx="1.2" />
                <rect x={x + 5} y="32" width="6" height="6.5" rx="1.2" />
              </g>
            ))}
            <path d="M50 32L62 26.5V37.5Z" />
            <rect x="39.5" y="24" width="12" height="16" rx="3.5" />
            <rect x="42.5" y="38" width="6" height="17" rx="3" />
          </g>
          <rect x="44.4" y="45.5" width="2.2" height="6" rx="1.1" fill="#fff" />
        </mask>
      </defs>
      <circle cx="32" cy="32" r="28" fill="var(--logo-teeth, transparent)" />
      <circle cx="32" cy="32" r="28" fill="var(--logo-globe, #FFD60A)" mask={`url(#${id})`} />
    </svg>
  );
}

export function Logo({ name }: { name: string }) {
  return (
    <>
      <LogoMark size={36} />
      <span style={{ fontFamily: "\"Bricolage Grotesque\", var(--f-display)", fontWeight: 800, fontSize: 24, letterSpacing: "-.03em" }}>
        {name}
      </span>
    </>
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
 *  Computer: one bar on top, logo left, Explore · Trips · Treks · Closet in the middle, You on the right.
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
    ["/trails", "Treks", "treks", /^\/trails(\/|$)/.test(p)],
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
            {dock.map(([to, label, , on]) => (
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
