import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { Place } from "../lib/types";

export function placeLabel(p: Place) {
  return [p.name, p.admin, p.country].filter(Boolean).join(", ");
}

export function PlaceSearch({ value, onPick, id, autoFocus }: {
  value: Place | null; onPick: (p: Place) => void; id?: string; autoFocus?: boolean;
}) {
  const [q, setQ] = useState(value ? placeLabel(value) : "");
  const [results, setResults] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => { if (value) setQ(placeLabel(value)); }, [value]);

  function onChange(v: string) {
    setQ(v);
    window.clearTimeout(timer.current);
    if (v.trim().length < 2) { setResults([]); return; }
    timer.current = window.setTimeout(async () => {
      setBusy(true);
      try {
        const r = await api.geocode(v.trim());
        setResults(r.results);
        setOpen(true);
      } finally { setBusy(false); }
    }, 280);
  }

  return (
    <div style={{ position: "relative" }}>
      <input id={id} type="search" value={q} autoFocus={autoFocus} autoComplete="off"
        placeholder="Town, park or region" onChange={(e) => onChange(e.target.value)}
        onFocus={() => results.length && setOpen(true)} aria-autocomplete="list" />
      {busy && <span className="spin" style={{ position: "absolute", right: 12, top: 13 }} />}
      {open && results.length > 0 && (
        <ul className="places" role="listbox">
          {results.map((p, i) => (
            <li key={i}>
              <button type="button" onClick={() => { onPick(p); setOpen(false); setQ(placeLabel(p)); }}>
                {placeLabel(p)}<small>{Math.round(p.elevation_m)} m</small>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
