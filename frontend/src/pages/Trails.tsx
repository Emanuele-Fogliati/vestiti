import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BagIcon, BuyBar, KitSheet, ProductRow, totalOf, type BuyPick } from "../components/BuyBar";
import { Garment } from "../components/Garment";
import { Illustration } from "../components/Illustration";
import { TreksMap } from "../components/Maps";
import { DIFFICULTY, TrailFacts } from "../components/TrailCards";
import { api } from "../lib/api";
import { money } from "../lib/format";
import type { Item, TrailCard, TrailDifficulty, TrailWear } from "../lib/types";

const REGION = (() => { try { return new Intl.DisplayNames(["en"], { type: "region" }); } catch { return null; } })();
const countryName = (c: string) => { try { return REGION?.of(c) ?? c; } catch { return c; } };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const LEVELS: (TrailDifficulty | "")[] = ["", "easy", "moderate", "hard", "technical"];

/** Treks, map first (Manu 2026-11-15: the same page as a trip). The map shows every trek of the
 *  filters as a dot coloured by how hard it is; the panel on the left lists them with their drawing;
 *  a trek opens its card beside the panel (numbers, what you wear on it) and the bar at the bottom
 *  sells what it asks for, with Cheaper / Better. Phone: the map on top, the list below. */
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
  const [all, setAll] = useState<TrailCard[] | null>(null);
  const [countries, setCountries] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [desk, setDesk] = useState(() => typeof matchMedia === "undefined" || matchMedia("(min-width: 900px)").matches);
  const [wear, setWear] = useState<TrailWear | null>(null);
  const [chosen, setChosen] = useState<Record<string, Item>>({});
  const [buyOpen, setBuyOpen] = useState(false);

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
  const zone = useMemo(() => {
    if (find.length < 3 || !all) return null;
    if (all.some((t) => countryName(t.country).toLowerCase() === find || t.country.toLowerCase() === find)) return null;
    if (geo && geo.q === find) return { lat: geo.lat, lon: geo.lon, name: geo.name.toLowerCase() === find ? typed.trim() : geo.name };
    const named = all.filter((t) => t.lat != null && t.lon != null && textHit(t));
    if (!named.length || named.length > 8) return null;
    return { lat: named[0].lat!, lon: named[0].lon!, name: named[0].base || named[0].name };
  }, [find, all, geo]); // eslint-disable-line react-hooks/exhaustive-deps
  const away = (t: TrailCard) => zone && t.lat != null && t.lon != null ? distKm(zone.lat, zone.lon, t.lat, t.lon) : Infinity;

  const shown = useMemo(() => base.filter((t) => textHit(t) || away(t) <= km)
    // near the place first; else in season first, then the ones with a drawing (the famous ones), then the rest
    .sort((a, b) => (zone ? Math.round(away(a)) - Math.round(away(b)) : 0)
      || Number(b.in_season !== false) - Number(a.in_season !== false) || Number(!!b.art) - Number(!!a.art)
      || Number(b.tier === "A") - Number(a.tier === "A")), [base, find, zone, km]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => setPage(0), [all, level, kind, style, find, km, zone?.lat]);

  const PER = desk ? 6 : 20;
  const pages = Math.max(1, Math.ceil(shown.length / PER));
  const list = desk ? shown.slice(page * PER, page * PER + PER) : shown.slice(0, (page + 1) * PER);
  const sel = selId ? (all ?? []).find((t) => t.id === selId) ?? null : null;
  // a trek picked on the map: its page of the list opens, so its row shows highlighted
  useEffect(() => {
    const i = selId ? shown.findIndex((t) => t.id === selId) : -1;
    if (i >= 0 && desk) setPage(Math.floor(i / PER));
  }, [selId, shown, desk, PER]);

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

  const where = zone ? `around ${zone.name}` : country ? countryName(country) : find ? `“${find}”` : "the world";
  const inset = desk ? { top: 20, right: 60, bottom: 150, left: sel ? 870 : 470 } : undefined;

  const search = (
    <form className="mf-say mf-search" role="search" onSubmit={(e) => { e.preventDefault(); set("find", typed.trim()); }}>
      <SearchIcon />
      <input type="search" value={typed} aria-label="Search hikes" placeholder="Search a hike, park, town or country"
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
        <select aria-label="Hikes or city walks" value={style} onChange={(e) => set("style", e.target.value)}>
          <option value="">All walks</option>
          <option value="trek">Hikes</option>
          <option value="city">City walks</option>
        </select>
        <select aria-label="How long" value={kind} onChange={(e) => set("kind", e.target.value)}>
          <option value="">Any length</option>
          <option value="day">Day walks</option>
          <option value="multiday">Several days</option>
        </select>
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
      {list.map((t) => (
        <li key={t.id}>
          <button type="button" className={`mf-trow${t.id === selId ? " sel" : ""}${t.in_season === false ? " off" : ""}`} onClick={() => set("t", t.id === selId ? "" : t.id)}>
            <span className="mf-thumb">{t.art ? <Illustration art={t.art} /> : null}</span>
            <span className="mf-nm">
              <b>{t.name}</b>
              <small><span className={`tag diff-${t.difficulty}`}>{DIFFICULTY[t.difficulty]}</span>
                {t.km != null && <span>{Math.round(t.km)} km</span>}{t.gain_m != null && <span>+{Math.round(t.gain_m).toLocaleString("en-US")} m</span>}
                {t.kind === "multiday" && <span>{t.days} days</span>}</small>
              <small className="mf-base">{zone && Number.isFinite(away(t)) ? `${Math.round(away(t))} km away · ` : ""}From {t.base}{country ? "" : ` · ${countryName(t.country)}`} · best {t.months_text}</small>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );

  const card = sel && (
    <div className={desk ? "mf-float mf-card mf-tcard" : "mf-tcard in"}>
      {desk && <button type="button" className="mf-x" onClick={() => set("t", "")} aria-label="Close"><X /></button>}
      {sel.art && <div className="mf-art"><Illustration art={sel.art} label={sel.name} /></div>}
      <div className="mf-card-in">
        <div>
          <span className={`tag diff-${sel.difficulty}`}>{DIFFICULTY[sel.difficulty]}</span>{" "}
          <span className="mf-k">From {sel.base} · best {sel.months_text}</span>
          <h3>{sel.name}</h3>
        </div>
        <TrailFacts t={sel} />
        {wear?.weather && <span className="mf-k">{wear.weather.tmin}–{wear.weather.tmax}° in {MONTHS[wearMonth - 1]}{wear.coldest ? ` · feels ${wear.coldest.feels_like_c}° at the coldest` : ""}{wear.in_season ? "" : " · not in season then"}</span>}
        <b className="mf-sub">What you wear on it</b>
        {!wear ? <p className="mf-k"><span className="spin" /> Working it out…</p> : (
          <ul className="mf-wear">
            {wear.pieces.map((p) => {
              const it = chosen[p.slot] ?? p.products?.medium ?? null;
              return (
                <li key={p.slot} className="get">
                  <Garment slot={p.slot} />
                  <span className="mf-nm"><span>{p.name}</span><small>{it ? `${it.brand} ${it.name}` : p.reasons[0] ?? p.level}</small></span>
                  {it?.image_url && <img src={it.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" />}
                  {it && <span className="mf-pr">{money(it.price, it.currency)}</span>}
                </li>
              );
            })}
          </ul>
        )}
        <Link className="mf-btn wide" to={`/trails/${sel.id}${month ? `?month=${month}` : ""}`}>The trail: map, profile, when to turn back →</Link>
      </div>
    </div>
  );

  return (
    <main className="trk">
      <div className="mf">
        <div className="mf-map">
          <TreksMap trails={shown} selected={selId} onPick={(id) => set("t", id)} inset={inset}
            fitKey={`${country}|${month}|${level}|${kind}|${style}|${find}|${shown.length}`} />
          {desk && <div className="mf-legend">{(["easy", "moderate", "hard", "technical"] as const).map((l) => <span key={l}><i className={`mf-dot ${l}`} />{DIFFICULTY[l]}</span>)}</div>}
        </div>

        <section className="mf-float mf-panel" aria-label="Hikes">
          {!desk && sel ? (
            <>
              <button type="button" className="mf-btn sm mf-back" onClick={() => set("t", "")}><Back /> All hikes</button>
              {card}
              {picks.length > 0 && <div className="mf-phone-buy"><div className="mf-k">To get for this hike · {money(totalOf(picks), cur)}</div>
                <ProductRow picks={picks} onPick={pick} /></div>}
              <div className="mf-phone-go">
                <button type="button" className="mf-btn go wide" disabled={!picks.length} onClick={() => setBuyOpen(true)}>
                  <BagIcon />{picks.length ? `Buy the ${picks.length} pieces · ${money(totalOf(picks), cur)}` : "Working out the kit…"}</button>
              </div>
            </>
          ) : (
            <>
              <div className="mf-thead"><h1>Hikes</h1><span className="mf-k">{all ? `${shown.length.toLocaleString("en-US")} ${zone ? "" : "in "}${where}` : ""}</span></div>
              {search}
              {zone && (
                <div className="mf-chips mf-zone" role="group" aria-label={`How far from ${zone.name}`}>
                  <span className="mf-k">Around {zone.name}:</span>
                  {[10, 25, 50, 100].map((k) => <button key={k} type="button" className={km === k ? "on" : ""} onClick={() => setKm(k)}>{k} km</button>)}
                </div>
              )}
              {filters}
              {err && <p className="err">{err}</p>}
              {!all && !err ? <div className="loading"><span className="spin" /></div>
                : <div className="mf-scroll">{shown.length ? rows : <p className="mf-k">No trail matches: try another filter.</p>}</div>}
              {all && shown.length > PER && (desk ? (
                <div className="mf-pager"><span>{page + 1} / {pages}</span>
                  <span><button type="button" className="mf-btn sm" disabled={!page} onClick={() => setPage(page - 1)}>Back</button>
                    <button type="button" className="mf-btn sm" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>More hikes</button></span>
                </div>
              ) : list.length < shown.length && (
                <button type="button" className="mf-btn wide" onClick={() => setPage(page + 1)}>Show more ({(shown.length - list.length).toLocaleString("en-US")} left)</button>
              ))}
            </>
          )}
        </section>

        {desk && card}
        {desk && (sel ? (
          <BuyBar title="To get for this hike" sub={`what ${sel.name} asks for in ${MONTHS[wearMonth - 1]}`} picks={picks} onPick={pick}
            onBuy={() => setBuyOpen(true)} empty={wear ? "Nothing special to wear on it." : "Working out the kit…"} />
        ) : (
          <BuyBar title="To get for a hike" sub="pick one on the map or in the list" picks={[]}
            empty="Pick a hike: what it asks you to wear shows here, with real products and prices." />
        ))}
      </div>

      <KitSheet open={buyOpen} onClose={() => setBuyOpen(false)} title={sel ? `Your kit for ${sel.name}` : "Your kit"} picks={picks} />
    </main>
  );
}

const I = (d: string) => () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>;
const X = I("M6 6l12 12M18 6L6 18");
const Back = I("M19 12H5M11 6l-6 6 6 6");

/** Great-circle distance in km. */
function distKm(la1: number, lo1: number, la2: number, lo2: number) {
  const r = Math.PI / 180, a = Math.sin((la2 - la1) * r / 2) ** 2 + Math.cos(la1 * r) * Math.cos(la2 * r) * Math.sin((lo2 - lo1) * r / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(a));
}

const SearchIcon = () => <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>;
