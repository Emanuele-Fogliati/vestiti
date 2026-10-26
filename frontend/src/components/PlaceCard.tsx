import { useNavigate } from "react-router-dom";
import { Illustration } from "./Illustration";
import type { GlobePlace, GlobeRoute } from "../lib/worldmap";
import { KIND_LABEL, countriesLabel, countryName } from "../lib/worldmap";

/** What we know about one place on the map: its picture when we have drawn it, the routes
 *  that pass there (on the home globe) and a way to start your own trip from it. */
export function PlaceCard({ place, routes, onRoute, onClose, onZoom, planLink = true }: {
  place: GlobePlace; routes?: GlobeRoute[]; onRoute?: (r: GlobeRoute) => void;
  onClose: () => void; onZoom?: () => void; planLink?: boolean;
}) {
  const nav = useNavigate();
  const country = countryName(place.country);
  return (
    <aside className="pcard" aria-label={place.name}>
      <button type="button" className="pcard-x" aria-label="Close" onClick={onClose}>✕</button>
      {place.art && <Illustration terrain="hills" art={{ kind: "landmark", id: place.art, label: place.artLabel ?? place.name }} />}
      <div className="pcard-in">
        <p className="kicker">{KIND_LABEL[place.kind]} · {country}</p>
        <h3>{place.name}</h3>
        {routes && routes.length > 0 && (
          <>
            <p className="label pcard-sub">Trips that pass here</p>
            <ul className="pcard-routes">
              {routes.slice(0, 4).map((r) => (
                <li key={r.id}>
                  <button type="button" onClick={() => onRoute?.(r)}>
                    <span className="kicker">{countriesLabel(r.countries)} · {r.days} days</span>
                    <b>{r.title}</b>
                    <span className="small muted">{r.stops.map((s) => s.name).filter((n, i, a) => a.indexOf(n) === i).slice(0, 4).join(" → ")}{r.stops.length > 4 ? " …" : ""}</span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
        <div className="pcard-acts">
          {onZoom && <button type="button" className="btn sm" onClick={onZoom}>Zoom in here</button>}
          {planLink && (
            <button type="button" className={`btn sm${routes?.length ? "" : " primary"}`}
              onClick={() => nav("/trips/new", { state: { text: `${place.name}, ${country}` } })}>Start my own trip here</button>
          )}
        </div>
      </div>
    </aside>
  );
}
