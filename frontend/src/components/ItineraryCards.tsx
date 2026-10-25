import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { monthRange } from "../lib/format";
import type { ItineraryCard } from "../lib/types";
import { Illustration } from "./Illustration";

const TERR = ["alpine", "glacier", "coast", "city"] as const;

/** The ready-made itineraries as picture cards, each opening its day-by-day page. */
export function ItineraryCards({ limit }: { limit?: number }) {
  const [items, setItems] = useState<ItineraryCard[] | null>(null);
  useEffect(() => { api.itineraries().then(setItems).catch(() => setItems([])); }, []);
  if (items === null) return <p className="loading"><span className="spin" /></p>;
  if (!items.length) return null;
  return (
    <div className="tlist icards">
      {items.slice(0, limit).map((it, i) => (
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
