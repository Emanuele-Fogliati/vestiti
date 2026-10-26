import { Link, useNavigate } from "react-router-dom";
import { Illustration } from "./Illustration";
import type { GlobeData, GlobePlace } from "../lib/worldmap";
import { KIND_LABEL, countryName } from "../lib/worldmap";

/** What we know about one place on the map: its picture when we have drawn it, the itineraries
 *  that stop there and a way to plan a trip to it. Never how many organised trips go there. */
export function PlaceCard({ place, data, onClose, onZoom, planLink = true }: {
  place: GlobePlace; data: GlobeData; onClose: () => void; onZoom?: () => void; planLink?: boolean;
}) {
  const nav = useNavigate();
  const country = countryName(place.country);
  const its = place.itineraries.map((i) => data.itineraries[i]).filter(Boolean);
  return (
    <aside className="pcard" aria-label={place.name}>
      <button type="button" className="pcard-x" aria-label="Close" onClick={onClose}>✕</button>
      {place.art && <Illustration terrain="hills" art={{ kind: "landmark", id: place.art, label: place.artLabel ?? place.name }} />}
      <div className="pcard-in">
        <p className="kicker">{KIND_LABEL[place.kind]} · {country}</p>
        <h3>{place.name}</h3>
        <div className="pcard-acts">
          {its.map((it) => <Link key={it.slug} className="btn sm primary" to={`/ideas/${it.slug}`}>{it.title}</Link>)}
          {onZoom && <button type="button" className="btn sm" onClick={onZoom}>Zoom in here</button>}
          {planLink && (
            <button type="button" className={`btn sm${its.length ? "" : " primary"}`}
              onClick={() => nav("/trips/new", { state: { text: `${place.name}, ${country}` } })}>Plan a trip here</button>
          )}
        </div>
      </div>
    </aside>
  );
}
