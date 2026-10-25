import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { monthRange } from "../lib/format";
import type { ItineraryCard } from "../lib/types";
import { Illustration } from "./Illustration";

const TERR = ["alpine", "glacier", "coast", "city"] as const;

export function useItineraries() {
  const [items, setItems] = useState<ItineraryCard[] | null>(null);
  useEffect(() => { api.itineraries().then(setItems).catch(() => setItems([])); }, []);
  return items;
}

/** The recommended trips as picture cards, each opening its day-by-day page. */
export function ItineraryCards({ limit, filter, items: given, empty }: {
  limit?: number; filter?: (it: ItineraryCard) => boolean; items?: ItineraryCard[] | null; empty?: React.ReactNode;
}) {
  const fetched = useItineraries();
  const items = given !== undefined ? given : fetched;
  if (items === null) return <p className="loading"><span className="spin" /></p>;
  const shown = (filter ? items.filter(filter) : items).slice(0, limit);
  if (!shown.length) return <>{empty ?? null}</>;
  return (
    <div className="tlist icards">
      {shown.map((it, i) => (
        <Link className="tcard" to={`/ideas/${it.slug}`} key={it.slug}>
          <Illustration terrain={TERR[i % TERR.length]} art={it.art} />
          <div className="b">
            <span className="label">{it.days} days · best {monthRange(it.best_months)}</span>
            <h3>{it.title}</h3>
            <span className="small">{it.places.map((p) => p.replace(/ \(.*\)$/, "")).join(" → ")}</span>
          </div>
        </Link>
      ))}
    </div>
  );
}
