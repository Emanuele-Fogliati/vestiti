import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";

/** New trip (Manu 2026-11-16): straight into the map, where you add the stops yourself, like
 *  Google Maps. The trip is a draft until you press Save. `?q=` (from the home search) is the
 *  first place to look up. */
export default function NewTrip() {
  const { ensureUser } = useApp();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [err, setErr] = useState<string | null>(null);
  const once = useRef(false);

  useEffect(() => {
    if (once.current) return;
    once.current = true;
    (async () => {
      try {
        await ensureUser();
        const t = await api.createTrip("New trip");
        nav(`/trips/${t.id}`, { replace: true, state: { add: params.get("q") ?? "" } });
      } catch (e) { setErr((e as Error).message); }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main className="page auth-mf">
      <div className="wrap">{err ? <p className="err">{err} <Link to="/trips">Back to Trips</Link></p> : <div className="loading"><span className="spin" /></div>}</div>
    </main>
  );
}
