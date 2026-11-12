import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../lib/api";
import { blocked, blocksOf, fixes, move, place, remove, resize, type Block, type Fix } from "../lib/board";
import { addDays, daysBetween } from "../lib/format";
import type { Board, BoardLeg, BoardStop, Place, Sky, Trip } from "../lib/types";
import { PlaceSearch } from "./PlaceSearch";
import { LegIcon, SkyIcon, StopPanel } from "./StopPanel";

const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const D = (s: string) => new Date(s + "T12:00:00Z");
export const STATUS_TEXT = { idea: "Idea", flex: "Flexible", fixed: "Fixed" } as const;

export function legShort(l: BoardLeg): string {
  if (l.booked) return l.ref ? `Booked · ${l.ref}` : "Booked";
  if (l.mode === "flight") {
    const t = l.note?.match(/\b(\d\d:\d\d) →/)?.[1];
    return l.from_airport && l.to_airport ? `${l.from_airport.iata}–${l.to_airport.iata}${t ? ` ${t}` : ""}` : "Flight";
  }
  if (l.mode === "local") return "Close by";
  if (l.hours) return `${l.hours < 1 ? "<1" : `≈${Math.round(l.hours)}`} h`;
  return "How?";
}

type Msg = { text: string; kind: "ok" | "bad"; fixes?: Fix[]; onFix?: (f: Fix) => void };

/** The trip on its days: what is decided, what is booked, how you get from one place to the next
 * and the weather, with one place open below to plan its days. */
export function TripBoard({ trip, onChanged }: { trip: Trip; onChanged: () => void }) {
  const [board, setBoard] = useState<Board | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState(0);
  const [openLeg, setOpenLeg] = useState<number | null>(null); // stop index, or -1 = the flight home
  const [msg, setMsg] = useState<Msg | null>(null);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newPlace, setNewPlace] = useState<Place | null>(null);
  const [newDays, setNewDays] = useState(2);

  const load = useCallback(async () => {
    try { setBoard(await api.board(trip.id)); setErr(null); } catch (e) { setErr((e as Error).message); }
  }, [trip.id]);
  useEffect(() => { load(); }, [load, trip]);

  const stops = board?.stops ?? [];
  const start = board?.start_date ?? null;
  const blocks = useMemo(() => (board ? blocksOf(board.stops, board.start_date) : []), [board]);
  const returnBooked = !!board?.return_leg?.booked;
  const selIdx = Math.min(sel, Math.max(0, stops.length - 1));

  async function apply(next: Block[], ok: string, newStart?: string) {
    if (!board) return;
    setBusy(true);
    try {
      await api.layout(trip.id, next.map((b) => ({ id: b.id, days: b.days, status: b.status, gap_before: b.gap })), newStart);
      setMsg({ text: ok, kind: "ok" });
      onChanged();
    } catch (e) {
      setMsg({ text: (e as Error).message, kind: "bad" });
    } finally { setBusy(false); }
  }

  /** Try a change: if it would move something booked, say what and offer where to take the days. */
  function change(next: Block[], ok: string, changed: number) {
    if (!start) return;
    const why = blocked(blocks, next, start, returnBooked);
    if (!why) { apply(next, ok); return; }
    const fx = fixes(blocks, next, start, returnBooked, changed);
    setMsg({ text: why + (fx.length ? "" : " Unlock it first."), kind: "bad", fixes: fx,
      onFix: (f) => apply(f.blocks, `${f.label.replace(/^Take/, "Took").replace(/^Use/, "Used")}. Nothing booked moved.`) });
  }

  const actions = {
    resize: (i: number, d: number) => change(resize(blocks, i, d),
      `${blocks[i].name}: ${blocks[i].days + d} day${blocks[i].days + d > 1 ? "s" : ""}. The places after it moved.`, i),
    move: (i: number, dir: -1 | 1) => {
      const next = move(blocks, i, dir);
      const why = start && blocked(blocks, next, start, returnBooked);
      if (why) { setMsg({ text: why, kind: "bad" }); return; }
      setSel(i + dir);
      apply(next, `${blocks[i].name} moved ${dir < 0 ? "earlier" : "later"}.`);
    },
    remove: async (i: number) => {
      if (!start) return;
      const s = stops[i];
      if (s.status === "fixed") { setMsg({ text: `${s.name} is fixed: unlock it before removing it.`, kind: "bad" }); return; }
      setBusy(true);
      try {
        const next = remove(blocks, i, start, returnBooked);
        const closed = !blocked(blocks, blocks.filter((_, k) => k !== i), start, returnBooked);
        await api.deleteStop(trip.id, s.id);
        if (next.length) await api.layout(trip.id, next.map((b) => ({ id: b.id, days: b.days, status: b.status, gap_before: b.gap })));
        setSel(Math.max(0, i - 1));
        setMsg({ text: `${s.name} removed.${closed ? "" : " Its days stay free: something booked comes after."}`, kind: "ok" });
        onChanged();
      } catch (e) { setMsg({ text: (e as Error).message, kind: "bad" }); } finally { setBusy(false); }
    },
    status: async (i: number, status: "idea" | "flex" | "fixed", note?: string) => {
      const s = stops[i];
      try {
        await api.patchBoardStop(trip.id, s.id, { status, ...(status === "fixed" ? { fixed_note: note || s.fixed_note || null } : {}) });
        setMsg({ text: status === "fixed" ? `${s.name} is fixed: changes elsewhere can't move it.` : `${s.name}: ${STATUS_TEXT[status].toLowerCase()}.`, kind: "ok" });
        onChanged();
      } catch (e) { setMsg({ text: (e as Error).message, kind: "bad" }); }
    },
  };

  async function setStart(v: string) {
    if (!v || !board) return;
    const fixed = stops.some((s) => s.status === "fixed" || s.arrival.booked) || returnBooked;
    if (fixed && v !== start) { setMsg({ text: "Part of the trip is booked: moving the start would move it. Unlock it first.", kind: "bad" }); return; }
    await apply(blocks, "New start date: every place moved with it.", v);
  }

  async function add() {
    if (!newPlace || !board) return;
    setBusy(true);
    try {
      const at = stops.length ? selIdx + 1 : 0;
      const first = start ?? addDays(new Date().toISOString().slice(0, 10), 60);
      const ins: Block = { id: "new", name: newPlace.name, days: newDays, status: "idea", gap: 0 };
      let next = [...blocks.slice(0, at), ins, ...blocks.slice(at)];
      let where = at;
      if (start && blocked(blocks, next, start, returnBooked)) { // something booked after: add it at the end
        next = [...blocks, ins];
        where = blocks.length;
        if (blocked(blocks, next, start, returnBooked)) {
          setMsg({ text: `${newPlace.name} doesn't fit without moving something booked. Unlock it, or shorten a place first.`, kind: "bad" });
          return;
        }
      }
      const p = place(next, first)[where];
      const s = await api.addStop(trip.id, {
        name: newPlace.name, country_code: newPlace.country_code ?? null, latitude: newPlace.latitude,
        longitude: newPlace.longitude, elevation_m: newPlace.elevation_m ?? 0, start_date: p.start, end_date: p.end,
        activities: [{ type: "unknown" }], notes: null, visits: [], position: where, status: "idea",
      });
      next = next.map((b) => (b.id === "new" ? { ...b, id: s.id } : b));
      await api.layout(trip.id, next.map((b) => ({ id: b.id, days: b.days, status: b.status, gap_before: b.gap })));
      setAdding(false); setNewPlace(null); setNewDays(2); setSel(where);
      setMsg({ text: `${newPlace.name} added as an idea, ${newDays} day${newDays > 1 ? "s" : ""}.${where !== at ? " At the end: something booked comes before." : ""}`, kind: "ok" });
      onChanged();
    } catch (e) { setMsg({ text: (e as Error).message, kind: "bad" }); } finally { setBusy(false); }
  }

  if (err && !board) return <p className="err">{err}</p>;
  if (!board) return <p className="loading"><span className="spin" /> Laying out your days</p>;

  const total = board.total_days;
  const cols = stops.length ? total + 1 : 0; // + the day you fly home
  const col = (d: string) => (start ? daysBetween(start, d) + 1 : 1);
  const days = start ? Array.from({ length: cols }, (_, i) => addDays(start, i)) : [];
  const skyOn: Record<string, { sky: Sky; rain: number }> = {};
  for (const s of stops) for (const d of s.plan.days) skyOn[d.date] = { sky: d.sky, rain: d.rain_chance };
  const nFixed = stops.filter((s) => s.status === "fixed").length;
  const nBooked = stops.filter((s) => s.arrival.booked).length + (returnBooked ? 1 : 0);
  const selStop: BoardStop | undefined = stops[selIdx];

  return (
    <div className="board">
      <div className="bd-head">
        <div className="bd-when">
          <label className="label" htmlFor="bd-start">Starts</label>
          <input id="bd-start" type="date" value={start ?? ""} onChange={(e) => setStart(e.target.value)} disabled={busy || !stops.length} />
          {board.start_estimated && <span className="tag">a guess: set the real date</span>}
        </div>
        <p className="bd-sum">{stops.length ? `${total} days · ${stops.length} place${stops.length > 1 ? "s" : ""} · ${nFixed} fixed · ${nBooked} booked` : "No places yet"}</p>
        {busy && <span className="spin" aria-label="Saving" />}
      </div>
      <div className="bd-legend" aria-hidden="true">
        <span><i className="lg fixed" />Fixed: booked, won't move</span>
        <span><i className="lg flex" />Flexible: decided, days can change</span>
        <span><i className="lg idea" />Idea: maybe</span>
      </div>

      {stops.length > 0 && start && (
        <div className="bd-scroll">
          <div className="bd-grid" style={{ gridTemplateColumns: `repeat(${cols}, var(--bd-col))` }} role="list" aria-label="Your days">
            {days.map((d, i) => {
              const dt = D(d);
              const w = skyOn[d];
              return (
                <div key={d} className={`bd-day${[0, 6].includes(dt.getUTCDay()) ? " we" : ""}`} style={{ gridColumn: i + 1, gridRow: 1 }}>
                  <span>{DOW[dt.getUTCDay()]}</span><b>{dt.getUTCDate()}</b><span>{i === 0 || dt.getUTCDate() === 1 ? MON[dt.getUTCMonth()] : " "}</span>
                  {w && <span className={`bd-sky ${w.sky}`} title={w.sky === "unknown" ? `${w.rain}% of days wet (climate)` : w.sky}>
                    <SkyIcon sky={w.sky} />{w.sky === "unknown" ? <small>{w.rain}%</small> : null}</span>}
                </div>
              );
            })}
            {stops.map((s, i) => (
              <button key={s.id} type="button" role="listitem"
                className={`bd-blk ${s.status}${i === selIdx ? " sel" : ""}`}
                style={{ gridColumn: `${col(s.start_date)} / span ${s.days}`, gridRow: 2 }}
                onClick={() => { setSel(i); setOpenLeg(null); setMsg(null); }}
                aria-label={`${s.name}, ${s.days} days, ${STATUS_TEXT[s.status]}`}>
                <span className="st">{s.status === "fixed" ? `Fixed${s.fixed_note ? ` · ${s.fixed_note}` : ""}` : STATUS_TEXT[s.status]}</span>
                <span className="nm">{s.name}</span>
                <span className="mt">{s.days} day{s.days > 1 ? "s" : ""}{s.days_estimated ? " · a guess" : ""}</span>
              </button>
            ))}
            {stops.map((s, i) => (
              <div key={`l${s.id}`} className="bd-leg" style={{ gridColumn: `${col(s.start_date)} / span ${Math.min(2, s.days)}`, gridRow: 3 }}>
                <button type="button" className={s.arrival.booked ? "booked" : s.arrival.mode === "flight" ? "todo" : ""}
                  onClick={() => { setSel(i); setOpenLeg(openLeg === i ? null : i); }}
                  aria-label={`Getting to ${s.name} from ${s.arrival.from_name}`}>
                  <LegIcon mode={s.arrival.mode} />{legShort(s.arrival)}
                </button>
              </div>
            ))}
            {board.return_leg && (
              <div className="bd-leg" style={{ gridColumn: `${cols} / span 1`, gridRow: 3 }}>
                <button type="button" className={board.return_leg.booked ? "booked" : "todo"} onClick={() => setOpenLeg(openLeg === -1 ? null : -1)}
                  aria-label="Getting home">
                  <LegIcon mode={board.return_leg.mode} />{board.return_leg.booked ? "Home ✓" : "Home"}
                </button>
              </div>
            )}
            {stops.map((s) => (
              <div key={`s${s.id}`} className="bd-sleep" style={{ gridColumn: `${col(s.start_date)} / span ${s.days}`, gridRow: 4 }}>
                {s.sleep ? <>Sleep: {s.sleep}</> : <span className="muted">Sleep: add later</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {msg && (
        <div className={`bd-msg ${msg.kind}`} role="status">
          <span>{msg.text}</span>
          {msg.fixes?.map((f) => <button key={f.label} type="button" className="btn sm" onClick={() => msg.onFix?.(f)}>{f.label}</button>)}
          <button type="button" className="btn sm ghost" aria-label="Close" onClick={() => setMsg(null)}>✕</button>
        </div>
      )}

      <div className="bd-add">
        {adding || !stops.length ? (
          <div className="bd-addform">
            <div className="field"><label htmlFor="bd-new">{stops.length ? `Add a place after ${selStop?.name ?? "the last one"}` : "Where do you start?"}</label>
              <PlaceSearch id="bd-new" value={newPlace} autoFocus countries={trip.countries} onPick={setNewPlace} /></div>
            <div className="field"><label htmlFor="bd-ndays">Days</label>
              <input id="bd-ndays" type="number" min={1} max={60} value={newDays} onChange={(e) => setNewDays(Math.max(1, Math.min(60, Number(e.target.value) || 1)))} /></div>
            <button type="button" className="btn primary" disabled={!newPlace || busy} onClick={add}>Add</button>
            {stops.length > 0 && <button type="button" className="btn ghost" onClick={() => setAdding(false)}>Cancel</button>}
          </div>
        ) : <button type="button" className="btn" onClick={() => setAdding(true)}>+ Add a place</button>}
      </div>

      {openLeg !== null && (openLeg === -1 ? board.return_leg : stops[openLeg]?.arrival) && (
        <LegEditor tripId={trip.id} leg={openLeg === -1 ? board.return_leg! : stops[openLeg].arrival}
          stopId={openLeg === -1 ? null : stops[openLeg].id} prices={board.prices}
          home={board.home_airport?.iata ?? null}
          onClose={() => setOpenLeg(null)}
          onSaved={(t) => { setMsg({ text: t, kind: "ok" }); setOpenLeg(null); onChanged(); }}
          onError={(t) => setMsg({ text: t, kind: "bad" })} />
      )}

      {selStop && (
        <StopPanel key={selStop.id} trip={trip} stop={selStop} index={selIdx} count={stops.length} busy={busy}
          onResize={(d) => actions.resize(selIdx, d)} onMove={(d) => actions.move(selIdx, d)} onRemove={() => actions.remove(selIdx)}
          onStatus={(s, note) => actions.status(selIdx, s, note)}
          onChanged={onChanged} onMsg={(text, kind) => setMsg({ text, kind })} />
      )}
    </div>
  );
}

/** How you get there: the mode, whether it's booked, and for a flight the airports and the
 * search pages with route and date filled in. */
function LegEditor({ tripId, leg, stopId, prices, home, onClose, onSaved, onError }: {
  tripId: string; leg: BoardLeg; stopId: string | null; prices: boolean; home: string | null;
  onClose: () => void; onSaved: (msg: string) => void; onError: (msg: string) => void;
}) {
  const [mode, setMode] = useState(leg.mode);
  const [booked, setBooked] = useState(leg.booked);
  const [ref, setRef] = useState(leg.ref ?? "");
  const [from, setFrom] = useState(leg.from_airport?.iata ?? "");
  const [to, setTo] = useState(leg.to_airport?.iata ?? "");
  const [homeCode, setHomeCode] = useState(home ?? "");
  const [found, setFound] = useState<{ date: string; price: number | null; url: string | null }[] | null>(null);
  const isHome = leg.from_name === "Home" || leg.to_name === "Home";

  useEffect(() => {
    if (!prices || mode !== "flight" || !leg.from_airport || !leg.to_airport) return;
    api.flightPrices(leg.from_airport.iata, leg.to_airport.iata, leg.date).then((r) => setFound(r.available ? r.prices : null)).catch(() => setFound(null));
  }, [prices, mode, leg]);

  async function save() {
    try {
      const body = { mode, booked, ref: ref || null, from: mode === "flight" ? from || null : null, to: mode === "flight" ? to || null : null };
      if (isHome && homeCode !== (home ?? "")) await api.patchTrip(tripId, { home_airport: homeCode || null });
      if (stopId) await api.patchBoardStop(tripId, stopId, { arrival: body });
      else await api.patchTrip(tripId, { return_leg: body });
      onSaved(booked ? `${leg.from_name} to ${leg.to_name} booked: changes that move that day will be stopped.` : "Saved.");
    } catch (e) { onError(e instanceof ApiError ? e.message : String(e)); }
  }

  const d = D(leg.date);
  return (
    <div className="bd-legedit" role="group" aria-label={`From ${leg.from_name} to ${leg.to_name}`}>
      <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
        <h3>{leg.from_name} → {leg.to_name}</h3>
        <span className="muted small">{DOW[d.getUTCDay()]} {d.getUTCDate()} {MON[d.getUTCMonth()]}
          {leg.km ? ` · about ${leg.km.toLocaleString("en-US")} km` : ""}{leg.border ? " · border crossing" : ""}</span>
        <span className="spacer" />
        <button type="button" className="btn sm ghost" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
        {(["flight", "bus", "car", "train", "boat", "other"] as const).map((m) => (
          <button key={m} type="button" className="fchip" aria-pressed={mode === m} onClick={() => setMode(m)}><LegIcon mode={m} />{m === "other" ? "Other" : m[0].toUpperCase() + m.slice(1)}</button>
        ))}
      </div>
      {leg.guess === "road" && mode !== "flight" && leg.hours && <p className="small">About {Math.round(leg.hours)} h by road{leg.border ? ", border included" : ""}. In high season buses sell out: book a few days ahead.</p>}
      {leg.guess === "road_or_flight" && <p className="small">About {Math.round(leg.hours ?? 0)} h by road, or a short flight: compare both.</p>}
      {mode === "flight" && (
        <div className="stack" style={{ gap: 10 }}>
          {isHome && (
            <div className="field"><label>Your home airport</label>
              <AirportPick value={homeCode} onPick={setHomeCode} placeholder="e.g. Milan, MXP" /></div>
          )}
          <div className="grid2">
            <div className="field"><label>From</label><AirportPick value={from} onPick={setFrom} placeholder={leg.from_name} /></div>
            <div className="field"><label>To</label><AirportPick value={to} onPick={setTo} placeholder={leg.to_name} /></div>
          </div>
          {leg.links.length > 0 && (
            <div className="bd-links">
              <span className="label">Find flights</span>
              {leg.links.map((l) => <a key={l.label} className={`btn sm${l.airline ? " ghost" : ""}`} href={l.url} target="_blank" rel="noopener noreferrer">{l.label}</a>)}
            </div>
          )}
          {!leg.links.length && <p className="small muted">{isHome && !home ? "Set your home airport to get the flight links." : "Pick the airports to get the flight links."}</p>}
          {found && found.length > 0 && (
            <p className="small">Seen recently: {found.map((p) => `${D(p.date).getUTCDate()} ${MON[D(p.date).getUTCMonth()]} €${p.price}`).join(" · ")}. <span className="muted">Not live seats: check before you book.</span></p>
          )}
        </div>
      )}
      <div className="row" style={{ flexWrap: "wrap", gap: 10, alignItems: "center" }}>
        <label className="check"><input type="checkbox" checked={booked} onChange={(e) => setBooked(e.target.checked)} /> I booked it: lock this day</label>
        {booked && <input type="text" value={ref} onChange={(e) => setRef(e.target.value)} placeholder={mode === "flight" ? "Flight, e.g. AR 1872" : "Booking, e.g. Bus Sur 08:00"} aria-label="Booking reference" maxLength={40} />}
        <button type="button" className="btn primary sm" onClick={save}>Save</button>
      </div>
    </div>
  );
}

export function AirportPick({ value, onPick, placeholder }: { value: string; onPick: (code: string) => void; placeholder?: string }) {
  const [q, setQ] = useState(value);
  const [list, setList] = useState<{ iata: string; name: string; city: string; country: string }[]>([]);
  useEffect(() => setQ(value), [value]);
  useEffect(() => {
    if (q.trim().length < 2 || q === value) { setList([]); return; }
    const t = window.setTimeout(() => api.airports(q.trim()).then(setList).catch(() => setList([])), 250);
    return () => window.clearTimeout(t);
  }, [q, value]);
  return (
    <div style={{ position: "relative" }}>
      <input type="search" value={q} placeholder={placeholder} onChange={(e) => setQ(e.target.value)} autoComplete="off" />
      {list.length > 0 && (
        <ul className="places" role="listbox">
          {list.map((a) => (
            <li key={a.iata}><button type="button" onClick={() => { onPick(a.iata); setQ(a.iata); setList([]); }}>
              <b>{a.iata}</b> {a.city || a.name}<small>{a.country}</small></button></li>
          ))}
        </ul>
      )}
    </div>
  );
}
