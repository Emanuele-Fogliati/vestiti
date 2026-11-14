import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { brandName, useApp } from "../lib/app-context";

export function Logo({ name }: { name: string }) {
  return (
    <>
      <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="11" fill="var(--accent)" />
        <path d="M4.5 16.5L9.5 10l3 3.5 3-4.5 4 7.5Z" fill="var(--top-bg)" />
      </svg>
      <span style={{ fontFamily: "var(--f-display)", fontStretch: "var(--d-stretch)", fontWeight: 900, fontSize: 22, letterSpacing: "-.02em" }}>
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
