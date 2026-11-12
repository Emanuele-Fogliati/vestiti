/* Every flight leg of the trip on one page, and for each leg every flight of the day in time
   order, so an hour earlier or later is one look away (Manu, 2026-11-12). */
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../lib/api";
import {
  cheapest, checks, dayOf, duration, fastest, hhmm, minuteOfDay, money, nice, pickNote, shiftDay, total, visible,
  type FlightFilter,
} from "../lib/flights";
import type { FlightLeg, FlightOffer, FlightOrder, Passenger, Trip, TripFlights } from "../lib/types";
import { AirportPick } from "./Board";
import { LegIcon } from "./StopPanel";

interface LegState { key: string; day: string; offers: FlightOffer[] | null; loading: boolean; error: string; pick: FlightOffer | null }

const legKey = (l: FlightLeg) => `${l.stop_id ?? "home"}|${l.from_airport?.iata}|${l.to_airport?.iata}|${l.date}`;
const fresh = (l: FlightLeg): LegState => ({ key: legKey(l), day: l.date, offers: null, loading: false, error: "", pick: null });
const msg = (e: unknown) => (e instanceof ApiError ? e.message : String(e));

export function FlightsPlanner({ trip, onChanged }: { trip: Trip; onChanged: () => void }) {
  const [data, setData] = useState<TripFlights | null>(null);
  const [legs, setLegs] = useState<LegState[]>([]);
  const [adults, setAdults] = useState(1);
  const [filter, setFilter] = useState<FlightFilter>({ direct: false, sort: "time" });
  const [together, setTogether] = useState<{ offers: FlightOffer[] | null; loading: boolean; error: string }>({ offers: null, loading: false, error: "" });
  const [toast, setToast] = useState("");
  const [home, setHome] = useState(trip.home_airport ?? "");
  const [booking, setBooking] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api.tripFlights(trip.id);
      setData(d);
      // keep what was found for a leg while its airports and day stay the same
      setLegs((old) => d.legs.map((l) => {
        const key = legKey(l);
        return old.find((o) => o.key === key) ?? fresh(l);
      }));
    } catch (e) { setToast(msg(e)); }
  }, [trip.id]);
  useEffect(() => { load(); }, [load, trip]);

  const set = (i: number, patch: Partial<LegState>) => setLegs((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  async function search(i: number, day?: string) {
    const leg = data?.legs[i];
    if (!leg?.from_airport || !leg.to_airport) return;
    const d = day ?? legs[i].day;
    set(i, { day: d, loading: true, error: "" });
    try {
      const r = await api.searchFlights(leg.from_airport.iata, leg.to_airport.iata, d, adults);
      set(i, { offers: r.offers, loading: false });
    } catch (e) { set(i, { loading: false, error: msg(e), offers: null }); }
  }

  async function searchAll() {
    if (!data) return;
    await Promise.all(data.legs.map((l, i) => (l.booked ? null : search(i))));
  }

  async function save(i: number, booked: boolean) {
    const leg = data!.legs[i], p = legs[i].pick;
    if (!p) return;
    const s = p.slices[0];
    const body = { mode: "flight" as const, booked, ref: booked ? s.segments.map((g) => g.flight).join(" + ").slice(0, 40) : null,
      from: s.origin, to: s.destination, note: pickNote(p) };
    try {
      if (leg.stop_id) await api.patchBoardStop(trip.id, leg.stop_id, { arrival: body });
      else await api.patchTrip(trip.id, { return_leg: body });
      setToast(booked ? `${leg.from_name} → ${leg.to_name} booked: that day is now locked on the board.`
        : `${leg.from_name} → ${leg.to_name}: ${pickNote(p)} is on your plan, not booked yet.`);
      onChanged();
    } catch (e) { setToast(msg(e)); }
  }

  async function saveHome() {
    try { await api.patchTrip(trip.id, { home_airport: home || null }); onChanged(); } catch (e) { setToast(msg(e)); }
  }

  async function priceTogether() {
    if (!data) return;
    const slices = data.legs.map((l, i) => ({ l, i })).filter(({ l }) => !l.booked && l.from_airport && l.to_airport)
      .map(({ l, i }) => ({ origin: l.from_airport!.iata, destination: l.to_airport!.iata, date: legs[i]?.day ?? l.date }));
    setTogether({ offers: null, loading: true, error: "" });
    try {
      const r = await api.flightsTogether(slices, adults);
      setTogether({ offers: r.offers, loading: false, error: "" });
    } catch (e) { setTogether({ offers: null, loading: false, error: msg(e) }); }
  }

  const picks = legs.map((l) => l.pick);
  const allChecks = useMemo(() => (data ? checks(data.legs, picks) : []), [data, picks]);
  const sum = total(picks);
  const open = data?.legs.filter((l) => !l.booked) ?? [];
  const canTogether = !!data?.search && open.length >= 2 && open.length <= 6 && open.every((l) => l.from_airport && l.to_airport);

  if (!data) return toast ? <p className="bd-msg bad">{toast}</p> : <p className="muted">Loading flights…</p>;
  if (!data.legs.length) {
    return <p className="bd-msg">No flights in this trip yet. On the board, open the way between two places and pick <b>Flight</b>: it shows up here with every flight of its day.</p>;
  }
  const needHome = data.legs.some((l) => (l.from_name === "Home" && !l.from_airport) || (l.to_name === "Home" && !l.to_airport));

  return (
    <div className="flights">
      <div className="fl-bar">
        <label className="fl-adults">Travellers
          <select value={adults} onChange={(e) => { setAdults(Number(e.target.value)); setLegs((ls) => ls.map((l) => ({ ...l, offers: null, pick: null }))); }}>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="check"><input type="checkbox" checked={filter.direct} onChange={(e) => setFilter({ ...filter, direct: e.target.checked })} /> Direct only</label>
        <div className="seg" role="group" aria-label="Order">
          <button type="button" aria-pressed={filter.sort === "time"} onClick={() => setFilter({ ...filter, sort: "time" })}>By time</button>
          <button type="button" aria-pressed={filter.sort === "price"} onClick={() => setFilter({ ...filter, sort: "price" })}>By price</button>
        </div>
        <span className="spacer" />
        {data.search && <button type="button" className="btn primary sm" onClick={searchAll}>Show every flight, all legs</button>}
        {data.all_legs_link && <a className="btn sm" href={data.all_legs_link} target="_blank" rel="noopener noreferrer">All legs on Kayak</a>}
      </div>
      {!data.search && (
        <p className="bd-msg">Every flight of the day appears here once the flight search is switched on. For now each leg opens on its day in the flight sites below, and Kayak opens all legs at once.</p>
      )}
      {data.search && data.test && <p className="bd-msg"><b>Test mode.</b> Flights and prices come from the flight service's test data, not real seats.</p>}
      {needHome && (
        <div className="bd-msg">
          <span>Where do you fly from?</span>
          <div style={{ flex: 1, minWidth: 200 }}><AirportPick value={home} onPick={setHome} placeholder="Your home airport, e.g. Milan, MXP" /></div>
          <button type="button" className="btn sm primary" onClick={saveHome} disabled={!home}>Save</button>
        </div>
      )}
      {toast && <p className="bd-msg" role="status"><span>{toast}</span><button type="button" className="btn sm ghost" onClick={() => setToast("")} aria-label="Close">✕</button></p>}

      <ol className="fl-legs">
        {data.legs.map((leg, i) => (
          <LegCard key={`${leg.stop_id}-${i}`} n={i + 1} leg={leg} st={legs[i] ?? fresh(leg)}
            filter={filter} search={data.search} canBook={data.book} checks={allChecks[i] ?? []}
            onDay={(d) => search(i, d)} onSearch={() => search(i)} onPick={(o) => set(i, { pick: o })}
            onKeep={() => save(i, false)} onBooked={() => save(i, true)} onBook={() => setBooking(i)} />
        ))}
      </ol>

      {(sum || canTogether) && (
        <div className="fl-sum">
          {sum && <p><b>Your picks: {money(sum.amount, sum.currency)}</b> for {sum.count} of {open.length} leg{open.length > 1 ? "s" : ""}, bought one by one{adults > 1 ? `, ${adults} travellers` : ""}.</p>}
          {canTogether && (
            <div className="stack" style={{ gap: 8 }}>
              <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
                <button type="button" className="btn sm" onClick={priceTogether} disabled={together.loading}>{together.loading ? "Pricing…" : "Price all legs as one ticket"}</button>
                <span className="small muted">One ticket costs more or less, but if a flight is late the airline puts you on the next one.</span>
              </div>
              {together.error && <p className="small warnline">{together.error}</p>}
              {together.offers && !together.offers.length && <p className="small">No airline sells all these legs on one ticket.</p>}
              {together.offers && together.offers.length > 0 && (
                <ul className="fl-together">
                  {together.offers.slice(0, 3).map((o) => (
                    <li key={o.id}>
                      <b>{money(o.price, o.currency)}</b>
                      {sum && sum.currency === o.currency && sum.count === open.length && (
                        <span className={`tag ${o.price < sum.amount ? "fl-good" : ""}`}>{o.price < sum.amount ? `${money(sum.amount - o.price, o.currency)} less` : `${money(o.price - sum.amount, o.currency)} more`} than your picks</span>
                      )}
                      <span className="small">{o.airline}</span>
                      <span className="small muted">{o.slices.map((s) => `${s.origin}→${s.destination} ${dayOf(s.departs).slice(8)}/${dayOf(s.departs).slice(5, 7)} ${hhmm(s.departs)}`).join(" · ")}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {booking !== null && legs[booking]?.pick && (
        <BookForm tripId={trip.id} leg={data.legs[booking]} offer={legs[booking].pick!} adults={adults} test={data.test}
          onClose={() => setBooking(null)}
          onDone={(o) => { setBooking(null); setToast(`Booked${o.test ? " (test, no real ticket)" : ""}: reference ${o.booking_reference ?? o.order_id}. The day is locked on the board.`); onChanged(); }} />
      )}
    </div>
  );
}

function LegCard({ n, leg, st, filter, search, canBook, checks: cks, onDay, onSearch, onPick, onKeep, onBooked, onBook }: {
  n: number; leg: FlightLeg; st: LegState; filter: FlightFilter; search: boolean; canBook: boolean;
  checks: { level: string; text: string }[];
  onDay: (d: string) => void; onSearch: () => void; onPick: (o: FlightOffer | null) => void;
  onKeep: () => void; onBooked: () => void; onBook: () => void;
}) {
  const [all, setAll] = useState(false);
  const shown = st.offers ? visible(st.offers, filter) : [];
  const cheap = st.offers ? cheapest(st.offers) : null;
  const fast = st.offers ? fastest(st.offers) : null;
  const codes = leg.from_airport && leg.to_airport ? `${leg.from_airport.iata} → ${leg.to_airport.iata}` : "";
  const off = st.day !== leg.date;
  const LIMIT = 24;
  const rows = all ? shown : shown.slice(0, LIMIT);

  return (
    <li className={`fl-leg${leg.booked ? " booked" : ""}`}>
      <div className="fl-head">
        <span className="fl-n">{n}</span>
        <div className="fl-title">
          <h3><LegIcon mode="flight" /> {leg.from_name} → {leg.to_name}</h3>
          <span className="small muted">{nice(leg.date)}{codes ? ` · ${codes}` : ""}</span>
        </div>
        <span className="spacer" />
        {leg.booked && <span className="tag fl-good">Booked{leg.ref ? ` · ${leg.ref}` : ""}</span>}
        {!leg.booked && leg.note && <span className="tag">On your plan: {leg.note}</span>}
      </div>
      {leg.booked ? (
        leg.note ? <p className="small">{leg.note}</p> : null
      ) : !leg.from_airport || !leg.to_airport ? (
        <p className="small muted">Pick the airports for this leg on the board to see its flights.</p>
      ) : (
        <>
          <div className="fl-day">
            <button type="button" className="btn sm ghost" onClick={() => onDay(shiftDay(st.day, -1))} disabled={!search} aria-label="Day before">← Day before</button>
            <b className={off ? "warnline" : ""}>{nice(st.day)}</b>
            <button type="button" className="btn sm ghost" onClick={() => onDay(shiftDay(st.day, 1))} disabled={!search} aria-label="Day after">Day after →</button>
            {off && <button type="button" className="link small" onClick={() => onDay(leg.date)}>Back to {nice(leg.date)}</button>}
            <span className="spacer" />
            {search && !st.offers && !st.loading && <button type="button" className="btn sm primary" onClick={onSearch}>Show every flight</button>}
            {st.loading && <span className="small muted"><span className="spin" /> Asking the airlines… up to 20 seconds</span>}
          </div>
          {st.error && <p className="small warnline">{st.error}</p>}
          {st.offers && (
            st.offers.length === 0 ? <p className="small">No flights on {nice(st.day)} between these airports. Try the day before or after, or another airport.</p> : (
              <>
                <DayStrip offers={shown} pick={st.pick} cheap={cheap} onPick={onPick} />
                <p className="small muted">{st.offers.length} flight{st.offers.length > 1 ? "s" : ""} on {nice(st.day)}{shown.length !== st.offers.length ? `, ${shown.length} direct` : ""}. {filter.sort === "time" ? "In departure order." : "Cheapest first."}</p>
                <div className="fl-table" role="radiogroup" aria-label={`Flights ${leg.from_name} to ${leg.to_name}`}>
                  {rows.map((o) => <OfferRow key={o.id} o={o} on={st.pick?.id === o.id} cheap={o.id === cheap?.id} fast={o.id === fast?.id && fast?.id !== cheap?.id} onPick={() => onPick(st.pick?.id === o.id ? null : o)} />)}
                </div>
                {shown.length > LIMIT && <button type="button" className="link small" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${shown.length}`}</button>}
              </>
            )
          )}
          {st.pick && (
            <div className="fl-pick">
              <p className="small"><b>Your pick:</b> {nice(dayOf(st.pick.slices[0].departs))} · {pickNote(st.pick)} · {st.pick.slices[0].segments[0]?.airline ?? st.pick.airline} · <b>{money(st.pick.price, st.pick.currency)}</b>
                {" "}<button type="button" className="link small" onClick={() => onPick(null)}>Clear</button></p>
              {cks.map((c, k) => <p key={k} className={`small ${c.level === "bad" ? "warnline" : c.level === "warn" ? "warnline" : "okline"}`}>{c.level === "bad" ? "✕ " : "! "}{c.text}</p>)}
              {!cks.length && <p className="okline">Fits your days.</p>}
              <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                <button type="button" className="btn sm" onClick={onKeep}>Put it on my plan</button>
                <button type="button" className="btn sm ghost" onClick={onBooked}>I booked it elsewhere</button>
                {canBook && <button type="button" className="btn sm primary" onClick={onBook}>Book it here (test)</button>}
              </div>
            </div>
          )}
          {leg.links.length > 0 && (
            <div className="bd-links">
              <span className="label">{search ? "Or on" : "Find flights"}</span>
              {leg.links.map((l) => <a key={l.label} className={`btn sm${l.airline ? " ghost" : ""}`} href={l.url} target="_blank" rel="noopener noreferrer">{l.label}</a>)}
            </div>
          )}
        </>
      )}
    </li>
  );
}

/** The day at a glance: one mark per flight at its departure hour. */
function DayStrip({ offers, pick, cheap, onPick }: { offers: FlightOffer[]; pick: FlightOffer | null; cheap: FlightOffer | null; onPick: (o: FlightOffer) => void }) {
  return (
    <div className="fl-strip" aria-hidden="true">
      {[0, 6, 12, 18, 24].map((h) => <span key={h} className="fl-hour" style={{ left: `${(h / 24) * 100}%` }}>{String(h).padStart(2, "0")}</span>)}
      {offers.map((o) => (
        <button key={o.id} type="button" tabIndex={-1} title={`${hhmm(o.slices[0].departs)} · ${money(o.price, o.currency)}`}
          className={`fl-tick${o.id === pick?.id ? " on" : ""}${o.id === cheap?.id ? " cheap" : ""}${o.slices[0].stops ? " stop" : ""}`}
          style={{ left: `${(minuteOfDay(o.slices[0].departs) / 1440) * 100}%` }} onClick={() => onPick(o)} />
      ))}
    </div>
  );
}

function OfferRow({ o, on, cheap, fast, onPick }: { o: FlightOffer; on: boolean; cheap: boolean; fast: boolean; onPick: () => void }) {
  const s = o.slices[0];
  const plus = dayOf(s.arrives) > dayOf(s.departs);
  const via = s.segments.slice(0, -1).map((g) => g.to).join(", ");
  return (
    <button type="button" role="radio" aria-checked={on} className={`fl-row${on ? " on" : ""}`} onClick={onPick}>
      <span className="fl-time"><b>{hhmm(s.departs)}</b> → {hhmm(s.arrives)}{plus && <sup>+1</sup>}</span>
      <span className="fl-dur">{duration(s.minutes)}<br /><small>{s.stops ? `${s.stops} stop · ${via}` : "Direct"}</small></span>
      <span className="fl-air">{s.segments[0]?.airline ?? o.airline}<br /><small>{s.segments.map((g) => g.flight).join(" + ")}</small></span>
      <span className="fl-cond small">
        {o.bags != null && <span>{o.bags ? `${o.bags} bag` : "No bag"}</span>}
        {o.changeable != null && <span>{o.changeable ? "Changeable" : "No changes"}</span>}
      </span>
      <span className="fl-price"><b>{money(o.price, o.currency)}</b>{cheap && <span className="tag fl-good">Cheapest</span>}{fast && <span className="tag">Fastest</span>}</span>
    </button>
  );
}

const EMPTY: Passenger = { title: "mr", given_name: "", family_name: "", gender: "m", born_on: "", email: "", phone_number: "" };

function BookForm({ tripId, leg, offer, adults, test, onClose, onDone }: {
  tripId: string; leg: FlightLeg; offer: FlightOffer; adults: number; test: boolean;
  onClose: () => void; onDone: (o: FlightOrder) => void;
}) {
  const [ps, setPs] = useState<Passenger[]>(() => Array.from({ length: Math.max(adults, offer.passenger_ids.length) }, () => ({ ...EMPTY })));
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const up = (i: number, p: Partial<Passenger>) => setPs((a) => a.map((x, j) => (j === i ? { ...x, ...p } : x)));

  async function go(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try { onDone(await api.bookFlight(tripId, offer.id, leg.stop_id, ps)); } catch (x) { setErr(msg(x)); } finally { setBusy(false); }
  }
  const s = offer.slices[0];
  return (
    <form className="bd-legedit fl-book" onSubmit={go}>
      <div className="row" style={{ gap: 8 }}>
        <h3>Book {leg.from_name} → {leg.to_name}</h3><span className="spacer" />
        <button type="button" className="btn sm ghost" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <p className="small">{nice(dayOf(s.departs))} · {pickNote(offer)} · <b>{money(offer.price, offer.currency)}</b></p>
      {test && <p className="bd-msg"><b>Test booking.</b> No money moves and no real ticket is issued.</p>}
      {ps.map((p, i) => (
        <fieldset key={i} className="stack" style={{ gap: 8, border: 0, padding: 0, margin: 0 }}>
          <legend className="label">Traveller {i + 1}, as on the passport</legend>
          <div className="grid2">
            <div className="field"><label>First name</label><input required value={p.given_name} onChange={(e) => up(i, { given_name: e.target.value })} /></div>
            <div className="field"><label>Last name</label><input required value={p.family_name} onChange={(e) => up(i, { family_name: e.target.value })} /></div>
            <div className="field"><label>Title</label>
              <select value={p.title} onChange={(e) => up(i, { title: e.target.value as Passenger["title"] })}>
                <option value="mr">Mr</option><option value="ms">Ms</option><option value="mrs">Mrs</option><option value="miss">Miss</option><option value="dr">Dr</option>
              </select></div>
            <div className="field"><label>Gender on passport</label>
              <select value={p.gender} onChange={(e) => up(i, { gender: e.target.value as "m" | "f" })}><option value="m">M</option><option value="f">F</option></select></div>
            <div className="field"><label>Born on</label><input required type="date" value={p.born_on} onChange={(e) => up(i, { born_on: e.target.value })} /></div>
            <div className="field"><label>Email</label><input required type="email" value={p.email} onChange={(e) => up(i, { email: e.target.value })} /></div>
            <div className="field"><label>Phone, with country code</label><input required value={p.phone_number} placeholder="+393331234567" pattern="\+[1-9][0-9]{6,14}" onChange={(e) => up(i, { phone_number: e.target.value.replace(/[\s-]/g, "") })} /></div>
          </div>
        </fieldset>
      ))}
      {err && <p className="warnline small">{err}</p>}
      <div className="row" style={{ gap: 10 }}>
        <button type="submit" className="btn primary" disabled={busy}>{busy ? "Booking…" : `Book for ${money(offer.price, offer.currency)}`}</button>
        <span className="small muted">The price is checked again before booking.</span>
      </div>
    </form>
  );
}
