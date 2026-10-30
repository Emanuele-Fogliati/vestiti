import { countryName } from "../lib/format";
import type { Place } from "../lib/types";

/** Where a place is, always with its country: "Aguas Calientes, Guerrero, Mexico". */
export function whereLabel(p: { name: string; admin?: string | null; country?: string | null; country_code?: string | null }) {
  return [p.name, p.admin, p.country || countryName(p.country_code)].filter(Boolean).join(", ");
}

/** The map match may be the wrong place (another country, thousands of km from the other stops,
 * the wrong altitude). Never shown as if it were right: the traveller says yes or picks another. */
export function PlaceQuestion({ place, issues, alternatives = [], onYes, onPick, onSearch }: {
  place: { name: string; admin?: string | null; country?: string | null; country_code?: string | null };
  issues: string[];
  alternatives?: Place[];
  onYes: () => void;
  onPick?: (p: Place) => void;
  onSearch?: () => void;
}) {
  return (
    <div className="banner warn placeq" role="alert" onClick={(e) => e.stopPropagation()}>
      <b>Is this the place? {whereLabel(place)}</b>
      {issues.length > 0 && <p className="small" style={{ margin: "4px 0 8px" }}>{issues.join(" ")}</p>}
      <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
        <button type="button" className="btn sm" onClick={onYes}>Yes, it's right</button>
        {onPick && alternatives.slice(0, 3).map((p, i) => (
          <button type="button" className="btn sm ghost" key={i} onClick={() => onPick(p)}>No, {whereLabel(p)}</button>
        ))}
        {onSearch && <button type="button" className="link small" onClick={onSearch}>Search for it</button>}
      </div>
    </div>
  );
}
