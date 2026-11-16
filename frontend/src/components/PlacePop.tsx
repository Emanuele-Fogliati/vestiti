import { Illustration } from "./Illustration";
import { KIND_LABEL, countryName, type GlobePlace } from "../lib/worldmap";

/** A place tapped on the map that is not on the trip (Manu 2026-11-16: "se ci sono dei paletti
 *  sulla mappa che non sono sul viaggio, cliccandoci vedo il posto. A quel punto lì sì che mi
 *  serve il pop-up"): its drawing, its name and one button to put it in the trip. The only card
 *  that opens beside the panel on the trip pages. */
export function PlacePop({ place, slot, busy, floating, onAdd, onClose }: {
  place: GlobePlace; slot: number; busy?: boolean; floating: boolean;
  onAdd: () => void; onClose: () => void;
}) {
  return (
    <div className={floating ? "mf-float mf-card mf-placepop" : "mf-card in mf-placepop"} role="dialog" aria-label={place.name}>
      <button type="button" className="mf-x" onClick={onClose} aria-label="Close">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
      </button>
      {place.art && <div className="mf-art"><Illustration art={{ kind: "landmark", id: place.art, label: place.name }} /></div>}
      <div className="mf-card-in">
        <div>
          <span className="mf-k">{KIND_LABEL[place.kind]} · {countryName(place.country)}</span>
          <h3>{place.name}</h3>
        </div>
        <button type="button" className="mf-btn go wide" disabled={busy} onClick={onAdd}>
          {busy ? <span className="spin" /> : `Add as stop ${slot + 1}`}
        </button>
      </div>
    </div>
  );
}
