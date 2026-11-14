import { useId } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { brandName, useApp } from "../lib/app-context";

/** Logo "Globo con cerniera" (Manu 2026-11-14): a yellow globe with a zip across it.
 *  The teeth, slider and pull are cut out of the globe (mask), so whatever is behind shows through
 *  on the night home and dark bars. On light paper (--logo-globe/--logo-teeth set in paper.css) the globe turns
 *  ink and the teeth yellow, as on the logo board. `small` (under ~32 px) merges the teeth into one band. */
export function LogoMark({ size = 26, small = size < 32 }: { size?: number; small?: boolean }) {
  const id = `zipglobe-${useId().replace(/:/g, "")}`;
  const teeth = small
    ? [<rect key="band" x="9" y="27.5" width="30" height="9" rx="1" />]
    : [9, 15, 21, 27, 33].flatMap((x) => [
        <rect key={`t${x}`} x={x} y="27.5" width="3.6" height="4.5" rx="1" />,
        <rect key={`b${x}`} x={x + 3} y="32" width="3.6" height="4.5" rx="1" />,
      ]);
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" style={{ flex: "0 0 auto" }}>
      <defs>
        <mask id={id} maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">
          <circle cx="32" cy="32" r="27" fill="#fff" />
          <g fill="#000">
            {teeth}
            <path d="M48 32L60 28.5V35.5Z" />
            <rect x="38.5" y="26" width="10" height="12" rx="3" />
            <rect x="41" y="37" width="5" height="15" rx="2.5" />
          </g>
          {!small && <rect x="42.6" y="44" width="1.8" height="5" rx=".9" fill="#fff" />}
        </mask>
      </defs>
      <circle cx="32" cy="32" r="27" fill="var(--logo-teeth, transparent)" />
      <circle cx="32" cy="32" r="27" fill="var(--logo-globe, #FFD60A)" mask={`url(#${id})`} />
    </svg>
  );
}

export function Logo({ name }: { name: string }) {
  return (
    <>
      <LogoMark size={28} />
      <span style={{ fontFamily: "\"Bricolage Grotesque\", var(--f-display)", fontWeight: 800, fontSize: 22, letterSpacing: "-.03em" }}>
        {name}
      </span>
    </>
  );
}

export function Layout() {
  const { config, user, setUser } = useApp();
  const nav = useNavigate();
  const loc = useLocation();
  const name = brandName(config);
  // "Plan a trip" covers both ways in: your own trip and the recommended ones
  const planning = /^\/(start|ideas|trips\/new)(\/|$)/.test(loc.pathname);
  const links = [
    ["/start", "Plan a trip"],
    ["/trips", "My trips"],
    ["/trails", "Trekking"],
    ["/wardrobe", "Wardrobe"],
    ["/how-it-works", "How it works"],
  ];
  if (user?.is_admin) links.push(["/admin", "Admin"]);
  const on = (to: string, isActive: boolean) => (to === "/start" ? planning : to === "/trips" ? isActive && !planning : isActive);

  async function logout() {
    await api.logout();
    setUser(null);
    nav("/");
  }

  return (
    <>
      <header className="top">
        <div className="wrap top-in">
          <Link className="logo" to="/" aria-label={`${name} home`}><Logo name={name} /></Link>
          <nav className="nav" aria-label="Main">
            {links.map(([to, label]) => (
              <NavLink key={to} to={to} className={({ isActive }) => (on(to, isActive) ? "active" : "")}>{label}</NavLink>
            ))}
          </nav>
          <div className="acct">
            <span className="free">Free · always</span>
            {user && !user.is_guest ? (
              <>
                <NavLink to="/account">{user.display_name || user.email}</NavLink>
                <button type="button" onClick={logout}>Sign out</button>
              </>
            ) : (
              <>
                {user?.is_guest && <NavLink to="/account" title="You're planning as a guest">Guest</NavLink>}
                <NavLink to="/login" state={{ from: loc.pathname }}>Sign in</NavLink>
              </>
            )}
          </div>
        </div>
      </header>
      {/* inside a trip the phone shows the trip's own tabs (Plan, Weather, Pack) at the bottom instead */}
      {!/^\/trips\/[^/]+/.test(loc.pathname) && <nav className="mnav" aria-label="Main (mobile)">
        <NavLink to="/" end>Home</NavLink>
        {links.filter(([to]) => ["/start", "/trips", "/wardrobe"].includes(to)).map(([to, label]) => (
          <NavLink key={to} to={to} className={({ isActive }) => (on(to, isActive) ? "active" : "")}>{to === "/start" ? "Plan" : to === "/wardrobe" ? "Closet" : label}</NavLink>
        ))}
        <NavLink to={user && !user.is_guest ? "/account" : "/login"}>{user && !user.is_guest ? "Account" : "Sign in"}</NavLink>
      </nav>}
      <Outlet />
      <footer>
        <div className="wrap">
          <nav aria-label="Legal">
            <Link to="/how-it-works">How the warmth model works</Link>
            <Link to="/legal/affiliate">Affiliate disclosure</Link>
            <Link to="/legal/privacy">Privacy</Link>
            <Link to="/legal/terms">Terms</Link>
          </nav>
          <p>{config?.disclosure}</p>
          <div className="row">
            <span>Weather: Open-Meteo. Product data: sample catalog until affiliate feeds are connected.</span>
            <span className="spacer" />

          </div>
        </div>
      </footer>
    </>
  );
}
