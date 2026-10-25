import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Illustration } from "../components/Illustration";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { dayMonth } from "../lib/format";
import type { TripSummary } from "../lib/types";

const TERR = ["alpine", "coast", "glacier", "city", "hills", "snow"] as const;

export default function Trips() {
  const { user, loading } = useApp();
  const [trips, setTrips] = useState<TripSummary[] | null>(null);

  useEffect(() => {
    if (loading) return;
    if (!user) { setTrips([]); return; }
    api.trips().then(setTrips).catch(() => setTrips([]));
  }, [user, loading]);

  return (
    <main className="page">
      <div className="wrap">
        <div className="page-head">
          <div><p className="kicker">Your trips</p><h1>My trips</h1></div>
          <Link className="btn primary" to="/trips/new">+ New trip</Link>
        </div>
        {user?.is_guest && (
          <div className="banner info" style={{ marginBottom: 20 }}>
            You're planning as a guest. <Link to="/register">Create a free account</Link> to keep these trips on any device.
          </div>
        )}
        {trips === null ? <p className="loading"><span className="spin" /></p> : trips.length === 0 ? (
          <div className="empty"><p>No trips yet.</p><p style={{ marginTop: 12 }}><Link className="btn primary" to="/trips/new">Plan your first trip</Link></p></div>
        ) : (
          <div className="tlist">
            {trips.map((t, i) => (
              <Link className="tcard" to={`/trips/${t.id}`} key={t.id}>
                <Illustration terrain={TERR[i % TERR.length]} />
                <div className="b">
                  <h3>{t.name}</h3>
                  <span className="small muted">{t.start_date ? `${dayMonth(t.start_date)} – ${dayMonth(t.end_date!)}` : "No dates"} · {t.stop_count} stops</span>
                  <span className="small">{t.places.join(" → ")}</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
