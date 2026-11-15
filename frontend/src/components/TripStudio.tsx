import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { blocked, blocksOf, move, place, remove, resize, type Block } from "../lib/board";
import { addDays, dayMonth, money } from "../lib/format";
import { km, type GlobePlace } from "../lib/worldmap";
import type { Board, BoardLeg, Item, KitLine, LegMode, Place, Plans, Stop, Strategy, Tier, Trip } from "../lib/types";
import { BagIcon, BuyBar, ProductRow, totalOf, type BuyPick } from "./BuyBar";
import { Garment } from "./Garment";
import { Illustration } from "./Illustration";
import { TripMap } from "./Maps";
import { legShort } from "./Board";
import { LegIcon } from "./StopPanel";

/** The trip page, map first (Manu 2026-11-15, "la mappa prima di tutto"): the map fills the screen;
 *  on the left the stops as rows with the drawing of each place and black icons of the pieces still
 *  to get there; a stop opens its card beside the panel (weather, what you wear); at the bottom the
 *  pieces to get for the whole trip with Cheaper / Better and the total. On the phone: the map on
 *  top and the same content below it, each stop opening in place. */
export function TripStudio({ trip, plans, strategy, tier, sel, setSel, onChanged, onPlans, head, tabs, onBag, onAsk, onFlights, onBoard }: {
  trip: Trip; plans: Plans | null; strategy: Strategy | null; tier: Tier;
  sel: number | null; setSel: (i: number | null) => void;
  /** the stops changed: reload the trip (and its kit) */
  onChanged: () => Promise<void> | void;
  /** a product was picked: reload the kit only */
  onPlans: () => void;
  head: ReactNode; tabs: ReactNode; onBag: () => void; onAsk: (text?: string) => void;
  /** the flights, and the full board (booked, fixed, the plan of each day), in sheets */
  onFlights: () => void; onBoard: () => void;
}) {
  const { toast } = useApp();
  const [board, setBoard] = useState<Board | null>(null);
  const [msg, setMsg] = useState<{ text: string; bad?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [insAt, setInsAt] = useState<number | null>(null);
  const [offer, setOffer] = useState<GlobePlace | null>(null);
  const [drag, setDrag] = useState<number | null>(null);
  const [desk, setDesk] = useState(() => typeof matchMedia === "undefined" || matchMedia("(min-width: 900px)").matches);
  const addRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const mq = matchMedia("(min-width: 900px)");
    const f = () => setDesk(mq.matches);
    mq.addEventListener("change", f);
    return () => mq.removeEventListener("change", f);
  }, []);

  const loadBoard = useCallback(() => api.board(trip.id).then(setBoard).catch(() => undefined), [trip.id]);
  useEffect(() => { loadBoard(); }, [loadBoard, trip]);
  useEffect(() => { if (!msg) return; const t = setTimeout(() => setMsg(null), 6000); return () => clearTimeout(t); }, [msg]);

  const stops = useMemo(() => [...trip.stops].sort((a, b) => a.position - b.position), [trip]);
  const bstops = board?.stops ?? [];
  const start = board?.start_date ?? null;
  const blocks = useMemo(() => (board ? blocksOf(board.stops, board.start_date) : []), [board]);
  const returnBooked = !!board?.return_leg?.booked;

  // ---- the clothes: what is to get, where, and the cheaper / better product of the same piece
  const tp = plans && !plans.empty ? plans.tiers[tier] : null;
  const lines = tp?.items ?? [];
  const toGet = lines.filter((l) => l.kind === "product" && l.item);
  const alt = (t: Tier, slot: string) => plans?.tiers[t]?.items.find((x) => x.slot === slot && x.kind === "product")?.item ?? null;
  const picks: BuyPick[] = toGet.map((l) => ({ slot: l.slot, label: short(l), item: l.item!, cheaper: alt("cheap", l.slot), better: alt("premium", l.slot) }));
  // a stop's icons: the pieces to get that this place asks for and the others don't (what every
  // stop needs is in the bar below, the same everywhere: icons of it on each row say nothing)
  const everywhere = (l: KitLine) => stops.length > 1 && (l.where ?? []).every((u) => u !== "none");
  const getAt = (i: number) => toGet.filter((l) => at(l, i) && !everywhere(l)).slice(0, 4);
  const wearAt = (i: number) => lines.filter((l) => l.kind !== "none" && at(l, i));

  // ---- the weather of each stop, over its pin
  const wx = (i: number) => {
    const d = strategy?.stages[i]?.days ?? [];
    if (!d.length) return null;
    const lo = Math.round(Math.min(...d.map((x) => x.tmin))), hi = Math.round(Math.max(...d.map((x) => x.tmax)));
    const wet = d.filter((x) => x.precip_prob >= 50 || x.precip_mm >= 2).length;
    return { lo, hi, wet, n: d.length };
  };
  const tags = stops.map((_, i) => { const w = wx(i); return w ? `${w.lo}–${w.hi}°${w.wet ? " · rain" : ""}` : null; });

  async function pick(slot: string, item: Item) {
    try {
      await api.select(trip.id, { tier, slot, choice: "product", product_id: item.id });
      toast(`${item.brand} ${item.name}: in the bag.`);
      onPlans();
    } catch (e) { toast((e as Error).message); }
  }

  // ---- changes to the stops: the board's rules (nothing booked may move), then the server
  async function apply(next: Block[], ok: string) {
    if (!start) return;
    const why = blocked(blocks, next, start, returnBooked);
    if (why) { setMsg({ text: why, bad: true }); return; }
    setBusy(true);
    try {
      await api.layout(trip.id, next.map((b) => ({ id: b.id, days: b.days, status: b.status, gap_before: b.gap })));
      setMsg({ text: ok });
      await onChanged();
    } catch (e) { setMsg({ text: (e as Error).message, bad: true }); } finally { setBusy(false); }
  }
  const days = (i: number, d: number) => {
    const b = blocks[i];
    if (!b || b.days + d < 1) return;
    apply(resize(blocks, i, d), `${b.name}: ${b.days + d} ${b.days + d === 1 ? "day" : "days"}. The places after it moved.`);
  };
  const moveTo = (from: number, to: number) => {
    if (from === to || !blocks[from]) return;
    let next = blocks, i = from;
    while (i !== to) { next = move(next, i, to > i ? 1 : -1); i += to > i ? 1 : -1; }
    if (sel === from) setSel(to);
    apply(next, `${blocks[from].name} moved.`);
  };
  async function drop(i: number) {
    const s = bstops[i];
    if (!s || !start) return;
    if (s.status === "fixed") { setMsg({ text: `${s.name} is fixed: unlock it in "Change the days" before removing it.`, bad: true }); return; }
    setBusy(true);
    try {
      const next = remove(blocks, i, start, returnBooked);
      await api.deleteStop(trip.id, s.id);
      if (next.length) await api.layout(trip.id, next.map((b) => ({ id: b.id, days: b.days, status: b.status, gap_before: b.gap })));
      setSel(null);
      setMsg({ text: `${s.name} removed.` });
      await onChanged();
    } catch (e) { setMsg({ text: (e as Error).message, bad: true }); } finally { setBusy(false); }
  }
  async function add(p: Place, where: number | null, nDays = 2) {
    if (!board) return;
    const at = Math.max(0, Math.min(where ?? blocks.length, blocks.length));
    const first = start ?? addDays(new Date().toISOString().slice(0, 10), 60);
    const ins: Block = { id: "new", name: p.name, days: nDays, status: "idea", gap: 0 };
    let next = [...blocks.slice(0, at), ins, ...blocks.slice(at)];
    let pos = at;
    if (start && blocked(blocks, next, start, returnBooked)) { next = [...blocks, ins]; pos = blocks.length; }
    if (start && blocked(blocks, next, start, returnBooked)) {
      setMsg({ text: `${p.name} doesn't fit without moving something booked.`, bad: true });
      return;
    }
    setBusy(true);
    try {
      const d = place(next, first)[pos];
      const s = await api.addStop(trip.id, {
        name: p.name, country_code: p.country_code ?? null, latitude: p.latitude, longitude: p.longitude,
        elevation_m: p.elevation_m ?? 0, start_date: d.start, end_date: d.end, activities: [{ type: "unknown" }],
        notes: null, visits: [], position: pos, status: "idea",
      });
      next = next.map((b) => (b.id === "new" ? { ...b, id: s.id } : b));
      await api.layout(trip.id, next.map((b) => ({ id: b.id, days: b.days, status: b.status, gap_before: b.gap })));
      setInsAt(null);
      setOffer(null);
      setSel(pos);
      setMsg({ text: `${p.name} added, ${nDays} days, as stop ${pos + 1}.` });
      await onChanged();
    } catch (e) { setMsg({ text: (e as Error).message, bad: true }); } finally { setBusy(false); }
  }
  /** A place tapped on the map goes where it makes the shortest detour. */
  function bestSlot(lat: number, lon: number): number {
    if (!stops.length) return 0;
    const d = (a: Stop, b: { latitude: number; longitude: number }) => km(a.latitude, a.longitude, b.latitude, b.longitude);
    const p = { latitude: lat, longitude: lon };
    let best = stops.length, cost = d(stops[stops.length - 1], p);
    if (d(stops[0], p) < cost) { best = 0; cost = d(stops[0], p); }
    for (let i = 1; i < stops.length; i++) {
      const c = d(stops[i - 1], p) + d(stops[i], p) - d(stops[i - 1], stops[i]);
      if (c < cost) { cost = c; best = i; }
    }
    return best;
  }

  // ---- "say it": the common changes in plain words; anything else goes to the chat
  async function say(text: string) {
    const t = text.trim();
    if (!t) return;
    const find = (name: string) => {
      const n = norm(name);
      return stops.findIndex((s) => norm(s.name).includes(n) || n.includes(norm(s.name)));
    };
    let m = t.match(/^(?:add|aggiungi)\s+(.+?)(?:\s+(?:for\s+)?(\d+)\s*(?:days?|nights?|giorni|notti))?$/i);
    if (m) {
      try {
        const r = await api.geocode(m[1], trip.countries);
        const p = r.results[0];
        if (!p) { setMsg({ text: `I can't find "${m[1]}" on the map.`, bad: true }); return; }
        await add(p, bestSlot(p.latitude, p.longitude), m[2] ? Math.max(1, Math.min(60, +m[2])) : 2);
      } catch (e) { setMsg({ text: (e as Error).message, bad: true }); }
      return;
    }
    m = t.match(/(\d+)\s*(?:days?|nights?|giorni|notti)\s+(?:in|at|a|ad)\s+(.+)$/i) ?? t.match(/^(.+?)\s*[:,]?\s+(\d+)\s*(?:days?|nights?|giorni|notti)$/i);
    if (m) {
      const [n, name] = /^\d+$/.test(m[1]) ? [+m[1], m[2]] : [+m[2], m[1]];
      const i = find(name);
      if (i >= 0 && blocks[i]) { days(i, n - blocks[i].days); return; }
    }
    m = t.match(/^(?:remove|delete|drop|togli|rimuovi)\s+(.+)$/i);
    if (m) { const i = find(m[1]); if (i >= 0) { drop(i); return; } }
    onAsk(t);
  }

  const openStop = (i: number | null) => setSel(i === sel ? null : i);
  const s = sel != null ? stops[sel] : null;
  const total = totalOf(picks);
  const cur = picks[0]?.item.currency ?? plans?.currency;
  const inset = desk ? { top: 20, right: 70, bottom: 150, left: s ? 860 : 470 } : undefined;

  const say_ = (
    <form className="mf-say" onSubmit={(e) => { e.preventDefault(); const f = e.currentTarget.elements.namedItem("say") as HTMLInputElement; say(f.value); f.value = ""; }}>
      <Spark />
      <input name="say" placeholder={`Or say it: "add ${suggest(stops)}", "4 days in ${stops[1]?.name ?? stops[0]?.name ?? "Cusco"}"`} aria-label="Say a change" autoComplete="off" />
      <button type="submit" aria-label="Apply"><Arrow /></button>
    </form>
  );

  const rows = (
    <ol className={`mf-stops${busy ? " busy" : ""}`} aria-label="Stops">
      {stops.map((st, i) => {
        const b = bstops[i];
        const get = getAt(i);
        const leg = bstops[i + 1]?.arrival;
        const open = sel === i;
        return (
          <li key={st.id} className={`mf-li${drag === i ? " drag" : ""}`}
            onDragOver={(e) => { if (drag != null) e.preventDefault(); }}
            onDrop={(e) => { e.preventDefault(); if (drag != null) moveTo(drag, i); setDrag(null); }}>
            <div className={`mf-row${open ? " sel" : ""}`} draggable={desk} onDragStart={() => setDrag(i)} onDragEnd={() => setDrag(null)}>
              <button type="button" className="mf-hit" onClick={() => openStop(i)} aria-expanded={open} aria-label={`Stop ${i + 1}: ${st.name}`} />
              <span className="mf-num">{i + 1}</span>
              <span className="mf-thumb">{st.art ? <Illustration art={st.art} /> : null}</span>
              <span className="mf-nm">
                <b>{st.name}</b>
                <small>
                  <span className="mf-dates">{b ? `${dayMonth(b.start_date)} – ${dayMonth(b.end_date)}` : `${dayMonth(st.start_date)} – ${dayMonth(st.end_date)}`}</span>
                  {get.length > 0 && <span className="mf-gis" aria-label={`To get: ${get.map((l) => short(l)).join(", ")}`}>
                    {get.map((l) => <span key={l.slot} className="mf-gi"><Garment slot={l.slot} title={short(l)} /></span>)}
                  </span>}
                </small>
              </span>
              <span className="mf-step">
                <button type="button" onClick={() => days(i, -1)} disabled={!b || b.days <= 1 || busy} aria-label={`One day less in ${st.name}`}>−</button>
                <span>{b?.days ?? "–"}<i> {b?.days === 1 ? "day" : "days"}</i></span>
                <button type="button" onClick={() => days(i, 1)} disabled={!b || busy} aria-label={`One day more in ${st.name}`}>+</button>
              </span>
              <span className="mf-tools">
                {!desk && i > 0 && <button type="button" className="mf-ib" onClick={() => moveTo(i, i - 1)} aria-label={`Move ${st.name} earlier`}><Up /></button>}
                <button type="button" className="mf-ib" onClick={() => drop(i)} aria-label={`Remove ${st.name}`}><X /></button>
              </span>
            </div>
            {open && !desk && <div className="mf-inline">{card(i, false)}</div>}
            {leg && (
              <div className="mf-leg">
                <LegIcon mode={legMode(leg)} />
                <span>{legText(leg)}</span>
                <button type="button" className={`mf-ins${insAt === i + 1 ? " on" : ""}`} onClick={() => { setInsAt(insAt === i + 1 ? null : i + 1); setTimeout(() => addRef.current?.focus(), 0); }}>+ stop here</button>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );

  function card(i: number, floating: boolean) {
    const st = stops[i], b = bstops[i], w = wx(i), wear = wearAt(i);
    const month = st ? new Date(st.start_date + "T12:00:00Z").toLocaleString("en", { month: "long", timeZone: "UTC" }) : "";
    return (
      <div className={floating ? "mf-float mf-card" : "mf-card in"} key={st.id}>
        {floating && <button type="button" className="mf-x" onClick={() => setSel(null)} aria-label="Close"><X /></button>}
        {floating && st.art && <div className="mf-art"><Illustration art={st.art} /></div>}
        <div className="mf-card-in">
          {floating && <div>
            <span className="mf-k">Stop {i + 1} · {b ? `${dayMonth(b.start_date)} – ${dayMonth(b.end_date)} · ${b.days} ${b.days === 1 ? "day" : "days"}` : ""}</span>
            <h3>{st.name}</h3>
          </div>}
          {w && <span className="mf-k">{w.lo}–{w.hi}° in {month}{w.wet ? ` · rain on ${w.wet} of ${w.n} days` : " · mostly dry"}</span>}
          <b className="mf-sub">What you wear here</b>
          {wear.length ? <ul className="mf-wear">{wear.map((l) => <WearRow key={l.slot} l={l} />)}</ul>
            : <p className="mf-k">{plans ? "Nothing special here." : "Working out the clothes…"}</p>}
          {b?.trails && b.trails.length > 0 && (
            <>
              <b className="mf-sub">Treks from here</b>
              <ul className="mf-treks">
                {b.trails.slice(0, 3).map((t) => <li key={t.id}><Link to={`/trails/${t.id}`}>{t.name}</Link><span>{t.difficulty} · {t.km ? `${Math.round(t.km)} km` : `${t.days} d`}</span></li>)}
              </ul>
            </>
          )}
        </div>
      </div>
    );
  }

  const addField = <AddField inputRef={addRef} countries={trip.countries} label={insAt != null ? `Add a stop after ${stops[insAt - 1]?.name ?? "the start"}` : "Add a stop: town, park, glacier…"}
    onPick={(p) => add(p, insAt)} onCancel={insAt != null ? () => setInsAt(null) : undefined} />;

  return (
    <div className={`mf${s ? " has-card" : ""}`}>
      <div className="mf-map">
        <TripMap stops={stops} focusIndex={sel} bare inset={inset} tags={tags} onPin={(i) => setSel(i)}
          onPlace={(p) => setOffer(p)} />
        {desk && <span className="mf-mapnote">Tap a place on the map to add it</span>}
      </div>

      <section className="mf-float mf-panel" aria-label="Your trip">
        <div className="mf-head">{head}</div>
        <div className="mf-tabs">{tabs}</div>
        {say_}
        {msg && <p className={`mf-msg${msg.bad ? " bad" : ""}`} role="status">{msg.text}</p>}
        {offer && (
          <div className="mf-offer">
            {offer.art && <span className="mf-thumb"><Illustration art={{ kind: "landmark", id: offer.art, label: offer.name }} /></span>}
            <span className="mf-nm"><b>{offer.name}</b><small>goes in as stop {bestSlot(offer.lat, offer.lon) + 1}, the shortest detour</small></span>
            <button type="button" className="mf-btn go sm" disabled={busy}
              onClick={() => add({ name: offer.name, country_code: offer.country, latitude: offer.lat, longitude: offer.lon, elevation_m: 0 }, bestSlot(offer.lat, offer.lon))}>Add</button>
            <button type="button" className="mf-ib" onClick={() => setOffer(null)} aria-label="Not now"><X /></button>
          </div>
        )}
        {!desk && picks.length > 0 && (
          <div className="mf-phone-buy">
            <div className="mf-k">To get for this trip · {money(total, cur)}</div>
            <ProductRow picks={picks} tripId={trip.id} tier={tier} onPick={pick} />
          </div>
        )}
        <div className="mf-scroll">{rows}</div>
        {addField}
        <div className="mf-more">
          <button type="button" onClick={onFlights}><LegIcon mode="flight" />Flights</button>
          <button type="button" onClick={onBoard}>Days, bookings and things to do</button>
        </div>
        {!desk && (
          <div className="mf-phone-go">
            <button type="button" className="mf-btn go wide" onClick={onBag} disabled={!picks.length}>
              <BagIcon />{picks.length ? `Buy the ${picks.length} pieces · ${money(total, cur)}` : "Your closet covers it"}
            </button>
          </div>
        )}
      </section>

      {desk && sel != null && stops[sel] && card(sel, true)}
      {desk && (
        <BuyBar title="To get for this trip" sub={tp ? `${picks.length} of ${lines.filter((l) => l.kind !== "none").length} pieces, picked for the weather on the map` : "Working out the clothes…"}
          picks={picks} tripId={trip.id} tier={tier} onPick={pick} onBuy={onBag} buyLabel="Buy" />
      )}
    </div>
  );
}

function WearRow({ l }: { l: KitLine }) {
  const own = l.kind === "owned" || l.kind === "have";
  const it = l.item;
  return (
    <li className={own ? "" : "get"}>
      <Garment slot={l.slot} />
      <span className="mf-nm"><span>{l.slot_name}</span>
        <small>{own ? (l.kind === "have" && l.assumed ? "most people have one" : "in your closet") : l.kind === "rent" && l.rental ? `rent · ${l.rental.partner}` : it ? `${it.brand} ${it.name}` : "to get"}</small>
      </span>
      {own ? <span className="mf-tag ok">{l.kind === "have" && l.assumed ? "Have one?" : "You have it"}</span>
        : it?.image_url ? <img src={it.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" /> : null}
      {!own && <span className="mf-pr">{l.cost ? money(l.cost, it?.currency) : ""}</span>}
    </li>
  );
}

function AddField({ inputRef, countries, label, onPick, onCancel }: {
  inputRef: RefObject<HTMLInputElement | null>; countries?: string[]; label: string; onPick: (p: Place) => void; onCancel?: () => void;
}) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<Place[]>([]);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  function change(v: string) {
    setQ(v);
    window.clearTimeout(timer.current);
    if (v.trim().length < 2) { setRes([]); return; }
    timer.current = window.setTimeout(async () => {
      setBusy(true);
      try { setRes((await api.geocode(v.trim(), countries)).results.slice(0, 6)); } catch { setRes([]); } finally { setBusy(false); }
    }, 280);
  }
  return (
    <div className="mf-add">
      <Plus />
      <input ref={inputRef} type="search" value={q} placeholder={label} aria-label={label} autoComplete="off" onChange={(e) => change(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Escape") { setRes([]); onCancel?.(); } if (e.key === "Enter" && res[0]) { onPick(res[0]); setQ(""); setRes([]); } }} />
      {busy && <span className="spin" />}
      {onCancel && <button type="button" className="mf-ib" onClick={onCancel} aria-label="Cancel"><X /></button>}
      {res.length > 0 && (
        <ul className="mf-res" role="listbox">
          {res.map((p, i) => (
            <li key={i}><button type="button" onClick={() => { onPick(p); setQ(""); setRes([]); }}>
              <b>{p.name}</b><small>{[p.admin, p.country].filter(Boolean).join(", ")}</small>
            </button></li>
          ))}
        </ul>
      )}
    </div>
  );
}

const at = (l: KitLine, i: number) => !!l.where?.[i] && l.where[i] !== "none";
const norm = (s: string) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
/** "Shell jacket", not "Shell jacket (waterproof, 10k)" */
const short = (l: KitLine) => l.slot_name.replace(/\s*\(.*\)$/, "");
const suggest = (stops: Stop[]) => (stops.some((s) => s.country_code === "AR" || s.country_code === "CL") ? "Ushuaia" : "a town");

function legMode(l: BoardLeg): LegMode {
  if (l.chosen || l.booked) return l.mode;
  return l.guess === "flight" ? "flight" : l.guess === "local" ? "local" : "bus";
}
function legText(l: BoardLeg): string {
  const m = legMode(l);
  const how = m === "flight" ? "Flight" : m === "local" ? "Close by" : m === "train" ? "Train" : m === "boat" ? "Boat" : "By road";
  const t = legShort(l);
  return t && !/^(Flight|Close by|How\?)$/.test(t) && !(m === "flight" && t === "Flight") ? `${how} · ${t}` : how;
}

const I = (d: string) => () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>;
const X = I("M6 6l12 12M18 6L6 18");
const Up = I("M12 19V5M5 12l7-7 7 7");
const Plus = I("M12 5v14M5 12h14");
const Arrow = I("M5 12h14M13 6l6 6-6 6");
const Spark = I("M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6");
