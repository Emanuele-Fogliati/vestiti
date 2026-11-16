import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BagIcon, BuyBar, KitSheet, ProductRow, totalOf, type BuyPick } from "../components/BuyBar";
import { Illustration } from "../components/Illustration";
import { TreksMap } from "../components/Maps";
import { DIFFICULTY, TrailFacts, hoursText } from "../components/TrailCards";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { money } from "../lib/format";
import type { Item, TrailCard, TrailDifficulty, TrailSight, TrailWear } from "../lib/types";

const REGION = (() => { try { return new Intl.DisplayNames(["en"], { type: "region" }); } catch { return null; } })();
const countryName = (c: string) => { try { return REGION?.of(c) ?? c; } catch { return c; } };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const LEVELS: (TrailDifficulty | "")[] = ["", "easy", "moderate", "hard", "technical"];

/** Walks, map first (Manu 2026-11-15: the same page as a trip). The map shows every walk of the
 *  filters as a dot coloured by how hard it is, the famous ones and those of the recommended trips
 *  as their drawing; the panel on the left lists them. A walk picked opens in its own row, nowhere
 *  else (Manu 2026-11-16: no second popup on the right), and the bar at the bottom shows what it
 *  asks you to wear, with Cheaper / Better. Phone: the map on top, the list below. */
export default function Trails() {
  const [q, setQ] = useSearchParams();
  const country = q.get("country") ?? "";
  const month = Number(q.get("month")) || undefined;
  const level = (q.get("level") ?? "") as TrailDifficulty | "";
  const kind = q.get("kind") ?? "";
  const style = q.get("style") ?? "";
  const find = (q.get("find") ?? "").trim().toLowerCase(); // words typed here or on the home page
  const [typed, setTyped] = useState(q.get("find") ?? "");
  const selId = q.get("t");
  const savedTab = q.get("saved") === "1";
  const { user, ensureUser, setUser, toast } = useApp();
  const savedIds = useMemo(() => user?.saved_trails ?? [], [user]);
  const [more, setMore] = useState(false); // the filters, folded away (Manu 2026-11-16: fewer words)
  const [all, setAll] = useState<TrailCard[] | null>(null);
  const [countries, setCountries] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [desk, setDesk] = useState(() => typeof matchMedia === "undefined" || matchMedia("(min-width: 900px)").matches);
  const [wear, setWear] = useState<TrailWear | null>(null);
  const [chosen, setChosen] = useState<Record<string, Item>>({});
  const [buyOpen, setBuyOpen] = useState(false);
  // the chosen hike's path, drawn on the map as soon as it is picked
  const [line, setLine] = useState<[number, number][] | null>(null);
  const [sights, setSights] = useState<TrailSight[]>([]);
  // what the map shows: the list follows it (null = the whole globe)
  const [view, setView] = useState<{ w: number; s: number; e: number; n: number } | null>(null);

  useEffect(() => {
    const mq = matchMedia("(min-width: 900px)");
    const f = () => setDesk(mq.matches);
    mq.addEventListener("change", f);
    return () => mq.removeEventListener("change", f);
  }, []);

  useEffect(() => {
    setAll(null);
    api.trails({ country: country || undefined, month }).then((r) => { setAll(r.trails); setCountries(r.countries); })
      .catch((e) => setErr((e as Error).message));
  }, [country, month]);

  // the walks you saved (Manu 2026-11-16: "voglio vedere ... se ne ho salvati alcuni")
  const [extra, setExtra] = useState<Record<string, TrailCard>>({});
  useEffect(() => {
    if (!all) return;
    const have = new Set(all.map((t) => t.id));
    for (const id of savedIds) if (!have.has(id) && !extra[id])
      api.trailCard(id).then((c) => setExtra((x) => ({ ...x, [id]: c }))).catch(() => undefined);
  }, [savedIds, all]); // eslint-disable-line react-hooks/exhaustive-deps
  const savedCards = useMemo(() => {
    const by = new Map((all ?? []).map((t) => [t.id, t]));
    return savedIds.map((id) => by.get(id) ?? extra[id]).filter(Boolean) as TrailCard[];
  }, [savedIds, all, extra]);
  async function toggleSave(id: string) {
    const u = user ?? await ensureUser();
    const now = u.saved_trails ?? [];
    const on = !now.includes(id);
    setUser(await api.updateMe({ saved_trails: on ? [id, ...now] : now.filter((x) => x !== id) }));
    toast(on ? "Saved in Walks." : "Removed from Saved.");
  }

  const set = (k: string, v: string) => { const n = new URLSearchParams(q); if (v) n.set(k, v); else n.delete(k); if (k !== "t") n.delete("t"); setQ(n, { replace: true }); };
  const textHit = (t: TrailCard) => !find || ((h) => find.split(/\s+/).every((w) => h.includes(w)))(
    [t.name, t.country, countryName(t.country), t.region, t.base].join(" ").toLowerCase());
  const base = useMemo(() => (all ?? []).filter((t) => (!level || t.difficulty === level) && (!kind || t.kind === kind)
    && (!style || (t.style ?? "trek") === style)), [all, level, kind, style]);

  // search by zone (Manu 2026-11-16): "Fitz Roy" finds every walk around it, not only the ones with
  // the words in their name. The place is the map's own match for the words, or else the start of
  // the walks whose name has them; a country name stays a plain filter.
  const [geo, setGeo] = useState<{ q: string; lat: number; lon: number; name: string } | null>(null);
  useEffect(() => {
    if (find.length < 3) { setGeo(null); return; }
    let live = true;
    const h = setTimeout(() => {
      api.geocode(find).then((r) => {
        const p = r.results.find((x) => !/^(PCL|ADM1|CONT)/.test((x as { feature?: string }).feature ?? ""));
        if (live) setGeo(p ? { q: find, lat: p.latitude, lon: p.longitude, name: p.name } : null);
      }).catch(() => { if (live) setGeo(null); });
    }, 350);
    return () => { live = false; clearTimeout(h); };
  }, [find]);
  const [km, setKm] = useState(25);
  // a hike searched by its own name (Manu 2026-11-16): it comes first and opens, and every walk
  // around it shows too, as if you had zoomed in there
  const nameHit = (t: TrailCard) => !!find && find.split(/\s+/).every((w) => t.name.toLowerCase().includes(w));
  const zone = useMemo(() => {
    if (find.length < 3 || !all) return null;
    if (all.some((t) => countryName(t.country).toLowerCase() === find || t.country.toLowerCase() === find)) return null;
    const byName = all.filter((t) => t.lat != null && t.lon != null && nameHit(t));
    if (byName.length && byName.length <= 8) return { lat: byName[0].lat!, lon: byName[0].lon!, name: byName[0].name, trail: byName.length === 1 ? byName[0].id : null };
    if (geo && geo.q === find) return { lat: geo.lat, lon: geo.lon, name: geo.name.toLowerCase() === find ? typed.trim() : geo.name, trail: null };
    const named = all.filter((t) => t.lat != null && t.lon != null && textHit(t));
    if (!named.length || named.length > 8) return null;
    return { lat: named[0].lat!, lon: named[0].lon!, name: named[0].base || named[0].name, trail: null };
  }, [find, all, geo]); // eslint-disable-line react-hooks/exhaustive-deps
  // how far each walk's PATH comes to the place, or to the walk you searched (Manu 2026-11-16: not
  // from where it starts, since many walks share a trailhead and "0 km away" said nothing)
  const [aw, setAw] = useState<{ key: string; away: Record<string, number> } | null>(null);
  const zkey = zone ? `${zone.lat},${zone.lon},${zone.trail ?? ""}` : "";
  useEffect(() => {
    if (!zone) return;
    let live = true;
    api.trailsAround(zone.lat, zone.lon, 100, zone.trail).then((r) => { if (live) setAw({ key: zkey, away: r.away }); }).catch(() => undefined);
    return () => { live = false; };
  }, [zkey]); // eslint-disable-line react-hooks/exhaustive-deps
  const paths = aw && aw.key === zkey ? aw.away : null;
  const away = (t: TrailCard) => !zone ? Infinity : paths ? paths[t.id] ?? Infinity
    : t.lat != null && t.lon != null ? distKm(zone.lat, zone.lon, t.lat, t.lon) : Infinity;
  const ref = zone?.trail ? (all ?? []).find((t) => t.id === zone.trail) ?? null : null;
  const howFar = (t: TrailCard) => {
    const d = away(t);
    if (!zone || !Number.isFinite(d) || t.id === zone.trail) return "";
    if (ref && ref.lat != null && t.lat != null && distKm(ref.lat, ref.lon!, t.lat, t.lon!) < 0.3) return "Same start · ";
    if (d < 0.3) return ref ? "Shares part of the path · " : `Goes through ${zone.name} · `;
    return `${d < 1 ? "Under 1" : d < 10 ? d.toFixed(1) : Math.round(d)} km away · `;
  };

  const found = useMemo(() => base.filter((t) => textHit(t) || away(t) <= km)
    // the hike you named first, then the nearest; else in season first, then the famous ones (with a drawing)
    .sort((a, b) => Number(nameHit(b)) - Number(nameHit(a)) || (zone ? Math.min(away(a), 1e6) - Math.min(away(b), 1e6) : 0)
      || Number(b.in_season !== false) - Number(a.in_season !== false) || Number(!!b.art) - Number(!!a.art)
      || Number(b.tier === "A") - Number(a.tier === "A")), [base, find, zone, km, paths]); // eslint-disable-line react-hooks/exhaustive-deps
  const shown = savedTab ? savedCards : found;
  // one hike matches the name: it opens (card, what to wear) once you stop typing
  useEffect(() => {
    if (!zone?.trail || selId === zone.trail) return;
    const h = setTimeout(() => set("t", zone.trail!), 700);
    return () => clearTimeout(h);
  }, [zone?.trail]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => setPage(0), [all, level, kind, style, find, km, zone?.lat]);

  const inView = (t: TrailCard) => !view || (t.lat != null && t.lon != null && t.lat >= view.s && t.lat <= view.n
    && (view.w <= view.e ? t.lon >= view.w && t.lon <= view.e : t.lon >= view.w || t.lon <= view.e));
  const listed = useMemo(() => (savedTab ? shown : shown.filter((t) => inView(t) || t.id === selId)), [shown, view, selId, savedTab]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => setPage(0), [view]);
  const PER = desk ? 6 : 20;
  const pages = Math.max(1, Math.ceil(listed.length / PER));
  const list = desk ? listed.slice(page * PER, page * PER + PER) : listed.slice(0, (page + 1) * PER);
  const sel = selId ? (all ?? []).find((t) => t.id === selId) ?? null : null;
  // a trek picked on the map: its page of the list opens, so its row shows highlighted
  useEffect(() => {
    const i = selId ? listed.findIndex((t) => t.id === selId) : -1;
    if (i >= 0 && desk) setPage(Math.floor(i / PER));
  }, [selId, listed, desk, PER]);

  useEffect(() => {
    setLine(null);
    setSights([]);
    if (!selId) return;
    let live = true;
    api.trail(selId).then((t) => { if (!live) return; if (t.line.length > 1) setLine(t.line); setSights(t.sights ?? []); }).catch(() => undefined);
    return () => { live = false; };
  }, [selId]);

  // what the chosen trek asks you to wear, with products
  const wearMonth = month ?? new Date().getMonth() + 1;
  useEffect(() => {
    setWear(null);
    setChosen({});
    if (!selId) return;
    let live = true;
    api.trailWear(selId, wearMonth).then((w) => { if (live) setWear(w); }).catch(() => undefined);
    return () => { live = false; };
  }, [selId, wearMonth]);
  const picks: BuyPick[] = (wear?.pieces ?? []).flatMap((p) => {
    const it = chosen[p.slot] ?? p.products?.medium ?? p.products?.cheap ?? p.products?.premium;
    return it ? [{ slot: p.slot, label: p.name.replace(/\s*\/.*$/, ""), item: it, cheaper: p.products?.cheap, better: p.products?.premium }] : [];
  });
  const pick = (slot: string, it: Item) => setChosen((c) => ({ ...c, [slot]: it }));
  const cur = picks[0]?.item.currency;

  // country codes as names, A to Z (the list holds every country we have walks for)
  const byName = useMemo(() => {
    const l = countries.map((c) => [c, countryName(c)] as const);
    if (country && !countries.includes(country)) l.push([country, countryName(country)]);
    return l.sort((a, b) => a[1].localeCompare(b[1]));
  }, [countries, country]);

  const nf = [country, kind, style, month, level].filter(Boolean).length;
  const inset = desk ? { top: 20, right: 60, bottom: sel ? 150 : 20, left: 470 } : undefined;

  const search = (
    <form className="mf-say mf-search" role="search" onSubmit={(e) => { e.preventDefault(); set("find", typed.trim()); }}>
      <SearchIcon />
      <input type="search" value={typed} aria-label="Search walks" placeholder="Search"
        onChange={(e) => { setTyped(e.target.value); set("find", e.target.value.trim()); }} />
      {typed && <button type="button" aria-label="Clear" onClick={() => { setTyped(""); set("find", ""); }}>×</button>}
    </form>
  );

  const filters = (
    <div className="mf-filters">
      <div className="mf-selects">
        <select aria-label="Country" value={country} onChange={(e) => set("country", e.target.value)}>
          <option value="">Every country</option>
          {byName.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
        </select>
        <select aria-label="How long" value={kind} onChange={(e) => set("kind", e.target.value)}>
          <option value="">Any length</option>
          <option value="day">Day walks</option>
          <option value="multiday">Several days</option>
        </select>
      </div>
      <div className="mf-chips" role="group" aria-label="Nature or city">
        {([["", "All walks"], ["trek", "Nature"], ["city", "City"]] as const).map(([v, l]) => (
          <button key={v} type="button" className={style === v ? "on" : ""} onClick={() => set("style", v)}>
            {v && <i className={`mf-dot ${v === "city" ? "city" : "nature"}`} />}{l}</button>
        ))}
      </div>
      <div className="mf-chips" role="group" aria-label="When you go">
        <button type="button" className={!month ? "on" : ""} onClick={() => set("month", "")}>Any month</button>
        {MONTHS.map((m, i) => <button key={m} type="button" className={month === i + 1 ? "on" : ""} onClick={() => set("month", String(i + 1))}>{m}</button>)}
      </div>
      <div className="mf-chips" role="group" aria-label="How hard">
        {LEVELS.map((l) => <button key={l} type="button" className={level === l ? "on" : ""} onClick={() => set("level", l)}>
          {l && <i className={`mf-dot ${l}`} />}{l ? DIFFICULTY[l] : "Any level"}</button>)}
      </div>
    </div>
  );

  const rows = (
    <ul className="mf-treks">
      {list.map((t) => {
        const on = t.id === selId;
        return (
          <li key={t.id} className={on ? "open" : undefined}>
            <button type="button" className={`mf-trow${on ? " sel" : ""}${t.in_season === false ? " off" : ""}`} aria-expanded={on} onClick={() => set("t", on ? "" : t.id)}>
              <span className="mf-thumb">{t.art ? <Illustration art={t.art} /> : null}</span>
              <span className="mf-nm">
                <b>{t.name}</b>
                <small><span className={`tag diff-${t.difficulty}`}>{DIFFICULTY[t.difficulty]}</span>
                  {t.km != null && <span>{Math.round(t.km)} km</span>}
                  <span className="mf-base">{howFar(t)}{t.base}</span></small>
              </span>
            </button>
            {on && desk && (
              <div className="mf-topen">
                <span className="mf-k">{[t.gain_m != null ? `+${Math.round(t.gain_m).toLocaleString("en-US")} m` : "", hoursText(t.hours, t.days), `best ${t.months_text}`].filter(Boolean).join(" · ")}</span>
                <span className="mf-topen-go">
                  <button type="button" className={`mf-btn sm x-save${savedIds.includes(t.id) ? " on" : ""}`} aria-pressed={savedIds.includes(t.id)} onClick={() => toggleSave(t.id)}>
                    {savedIds.includes(t.id) ? "✓ Saved" : "Save"}</button>
                  <Link className="mf-btn sm go" to={`/trails/${t.id}${month ? `?month=${month}` : ""}`}>Open</Link>
                </span>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );

  // phone: the walk picked takes the panel (desktop: it opens in its row)
  const card = sel && (
    <div className="mf-tcard in">
      {sel.art && <div className="mf-art"><Illustration art={sel.art} label={sel.name} /></div>}
      <div className="mf-card-in">
        <div>
          <span className={`tag diff-${sel.difficulty}`}>{DIFFICULTY[sel.difficulty]}</span>{" "}
          <span className="mf-k">{sel.base} · best {sel.months_text}</span>
          <h3>{sel.name}</h3>
        </div>
        <TrailFacts t={sel} />
        <span className="mf-topen-go">
          <button type="button" className={`mf-btn sm x-save${savedIds.includes(sel.id) ? " on" : ""}`} aria-pressed={savedIds.includes(sel.id)} onClick={() => toggleSave(sel.id)}>
            {savedIds.includes(sel.id) ? "✓ Saved" : "Save"}</button>
          <Link className="mf-btn sm go" to={`/trails/${sel.id}${month ? `?month=${month}` : ""}`}>Open</Link>
        </span>
      </div>
    </div>
  );

  return (
    <main className="trk">
      <div className="mf">
        <div className="mf-map">
          <TreksMap trails={shown} selected={selId} onPick={(id) => set("t", id)} inset={inset} line={line} sights={sights} onView={setView}
            around={zone ? { lat: zone.lat, lon: zone.lon, km } : null}
            fitKey={`${savedTab ? `saved:${savedIds.length}|` : ""}${country}|${month}|${level}|${kind}|${style}|${find}|${shown.length}|${zone ? `${zone.lat},${zone.lon},${km}` : ""}`} />
          {desk && <div className="mf-legend">{(["easy", "moderate", "hard", "technical"] as const).map((l) => <span key={l}><i className={`mf-dot ${l}`} />{DIFFICULTY[l]}</span>)}<span><i className="mf-dot city" />City walk</span></div>}
        </div>

        <section className="mf-float mf-panel" aria-label="Walks">
          {!desk && sel ? (
            <>
              <button type="button" className="mf-btn sm mf-back" onClick={() => set("t", "")}><Back /> All walks</button>
              {card}
              {picks.length > 0 && <div className="mf-phone-buy"><div className="mf-k">What you wear · {money(totalOf(picks), cur)}</div>
                <ProductRow picks={picks} onPick={pick} /></div>}
              <div className="mf-phone-go">
                <button type="button" className="mf-btn go wide" disabled={!picks.length} onClick={() => setBuyOpen(true)}>
                  <BagIcon />{picks.length ? `Buy the ${picks.length} pieces · ${money(totalOf(picks), cur)}` : "Working out the kit…"}</button>
              </div>
            </>
          ) : (
            <>
              <div className="mf-thead"><h1>Walks</h1></div>
              <div className="mf-segrow">
                <div className="mf-seg" role="tablist" aria-label="Walks">
                  <button type="button" role="tab" aria-selected={!savedTab} className={!savedTab ? "on" : ""} onClick={() => set("saved", "")}>All</button>
                  <button type="button" role="tab" aria-selected={savedTab} className={savedTab ? "on" : ""} onClick={() => set("saved", "1")}>Saved{savedIds.length ? ` · ${savedIds.length}` : ""}</button>
                </div>
                {!savedTab && <button type="button" className={`mf-btn sm mf-fbtn${more || nf ? " on" : ""}`} aria-expanded={more} onClick={() => setMore(!more)}>
                  <FilterIcon />Filters{nf ? ` · ${nf}` : ""}</button>}
              </div>
              {!savedTab && search}
              {zone && (
                <div className="mf-chips mf-zone" role="group" aria-label={`How far from ${zone.name}`}>
                  <span className="mf-k">{zone.name}</span>
                  {[10, 25, 50, 100].map((k) => <button key={k} type="button" className={km === k ? "on" : ""} onClick={() => setKm(k)}>{k} km</button>)}
                </div>
              )}
              {!savedTab && more && filters}
              {err && <p className="err">{err}</p>}
              {!all && !err ? <div className="loading"><span className="spin" /></div>
                : <div className="mf-scroll">{listed.length ? rows : <p className="mf-k">{savedTab ? "Nothing saved yet." : shown.length ? "None here. Zoom out." : "No walk found."}</p>}</div>}
              {all && listed.length > PER && (desk ? (
                <div className="mf-pager">
                  <button type="button" className="mf-btn sm" aria-label="Previous" disabled={!page} onClick={() => setPage(page - 1)}><Back /></button>
                  <span>{page + 1} / {pages}</span>
                  <button type="button" className="mf-btn sm" aria-label="Next" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}><Next /></button>
                </div>
              ) : list.length < listed.length && (
                <button type="button" className="mf-btn wide" onClick={() => setPage(page + 1)}>Show more ({(listed.length - list.length).toLocaleString("en-US")} left)</button>
              ))}
            </>
          )}
        </section>

        {desk && sel && (
          <BuyBar title="What you wear" sub={`${sel.name}, ${MONTHS[wearMonth - 1]}`} picks={picks} onPick={pick}
            onBuy={() => setBuyOpen(true)} empty={wear ? "Nothing special to wear on it." : "Working out the kit…"} />
        )}
      </div>

      <KitSheet open={buyOpen} onClose={() => setBuyOpen(false)} title={sel ? `Your kit for ${sel.name}` : "Your kit"} picks={picks} />
    </main>
  );
}

const I = (d: string) => () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>;
const Back = I("M19 12H5M11 6l-6 6 6 6");
const Next = I("M5 12h14M13 6l6 6-6 6");

/** Great-circle distance in km. */
function distKm(la1: number, lo1: number, la2: number, lo2: number) {
  const r = Math.PI / 180, a = Math.sin((la2 - la1) * r / 2) ** 2 + Math.cos(la1 * r) * Math.cos(la2 * r) * Math.sin((lo2 - lo1) * r / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(a));
}

const FilterIcon = () => <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4" /></svg>;
const SearchIcon = () => <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>;
