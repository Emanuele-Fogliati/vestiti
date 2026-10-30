import { useState } from "react";
import { Illustration } from "./Illustration";
import type { GlobePlace, GlobeRoute } from "../lib/worldmap";
import { KIND_LABEL, countriesLabel, countryName } from "../lib/worldmap";
import { pickStore, usePicks } from "../lib/picks";

const INSIDE_SHOWN = 8;

/** What we know about one place on the map: its picture when we have drawn it, the places
 *  inside it (Florence: the Uffizi, Ponte Vecchio...), the routes that pass there (on the home
 *  globe) and, on the globe, a way to add it, or single places inside it, to your own trip. */
export function PlaceCard({ place, routes, onRoute, onClose, onZoom, zoomLabel, inside = [], parent = null, onPlace, pickable = false }: {
  place: GlobePlace; routes?: GlobeRoute[]; onRoute?: (r: GlobeRoute) => void;
  onClose: () => void; onZoom?: () => void; zoomLabel?: string;
  /** The places inside this city, most visited first. */
  inside?: GlobePlace[];
  /** The city this place is inside. */
  parent?: GlobePlace | null;
  onPlace?: (p: GlobePlace) => void;
  /** On the home globe: places can go into your own trip. */
  pickable?: boolean;
}) {
  const picks = usePicks();
  const [all, setAll] = useState(false);
  const country = countryName(place.country);
  const picked = picks.includes(place.id);
  const shownInside = all ? inside : inside.slice(0, INSIDE_SHOWN);
  return (
    <aside className="pcard" aria-label={place.name}>
      <button type="button" className="pcard-x" aria-label="Close" onClick={onClose}>✕</button>
      {place.art && <Illustration terrain="hills" art={{ kind: "landmark", id: place.art, label: place.artLabel ?? place.name }} />}
      <div className="pcard-in">
        <p className="kicker">
          {KIND_LABEL[place.kind]} · {parent
            ? <>{onPlace ? <button type="button" className="linkish" onClick={() => onPlace(parent)}>{parent.name}</button> : parent.name}, {country}</>
            : country}
        </p>
        <h3>{place.name}</h3>
        {pickable && (
          <div className="pcard-acts">
            <button type="button" className={`btn sm${picked ? " on" : " primary"}`} aria-pressed={picked}
              onClick={() => pickStore.toggle(place.id)}>
              {picked ? "✓ In my trip" : inside.length ? `Add all of ${place.name}` : "Add to my trip"}
            </button>
            {onZoom && <button type="button" className="btn sm" onClick={onZoom}>{zoomLabel ?? "Zoom in here"}</button>}
          </div>
        )}
        {inside.length > 0 && (
          <>
            <p className="label pcard-sub">Inside {place.name}</p>
            {pickable && <p className="small muted pcard-note">Add the whole city, or only the places you want to see.</p>}
            <ul className="pcard-inside">
              {shownInside.map((p) => {
                const on = picks.includes(p.id);
                return (
                  <li key={p.id}>
                    <button type="button" className="pcard-in-name" onClick={() => onPlace?.(p)}>
                      {p.art && <span className="pcard-dot art" aria-hidden="true" />}{p.name}
                    </button>
                    {pickable && (
                      <button type="button" className={`pcard-add${on ? " on" : ""}`} aria-pressed={on}
                        aria-label={on ? `Remove ${p.name} from my trip` : `Add ${p.name} to my trip`}
                        onClick={() => pickStore.toggle(p.id)}>{on ? "✓" : "+"}</button>
                    )}
                  </li>
                );
              })}
            </ul>
            {inside.length > INSIDE_SHOWN && (
              <button type="button" className="linkish small" onClick={() => setAll(!all)}>
                {all ? "Show fewer" : `Show all ${inside.length} places`}
              </button>
            )}
          </>
        )}
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
        {!pickable && onZoom && (
          <div className="pcard-acts">
            <button type="button" className="btn sm" onClick={onZoom}>{zoomLabel ?? "Zoom in here"}</button>
          </div>
        )}
      </div>
    </aside>
  );
}
