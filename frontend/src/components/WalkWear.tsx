import { useEffect, useMemo, useState } from "react";
import { api, buyUrl } from "../lib/api";
import { useApp } from "../lib/app-context";
import { money } from "../lib/format";
import { TIER_LABEL, TIERS, type Tier, type TrailWear } from "../lib/types";
import { KitSheet, type BuyPick } from "./BuyBar";
import { ProductArt } from "./ProductArt";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const FOOT: Record<string, string> = {
  sneaker: "Trainers", trail_runner: "Trail shoes", hiking_boot: "Hiking boots", mountaineering_boot: "Mountaineering boots",
  sandal: "Sandals",
};

/** The clothes for one walk, under the map, as a trip's bag is under its route (Manu 2026-11-16:
 *  "mi manda sotto e mi fai vedere ... le opzioni con la temperatura, tutte le cose che fai anche in
 *  trip"): the weather on the walk, the budget, one card per piece, "I have one". Only this walk's
 *  clothes, not a suitcase. Used by the Walks list (the walk picked) and by the walk's own page. */
export function WalkWear({ id, name, month, onMonth, months }: {
  id: string; name: string; month: number;
  /** a month picker here (the Walks list has none in its panel) */
  onMonth?: (m: number) => void; months?: number[];
}) {
  const { config } = useApp();
  const [w, setW] = useState<TrailWear | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tier, setTier] = useState<Tier>("medium");
  const [have, setHave] = useState<string[]>([]);
  const [buyOpen, setBuyOpen] = useState(false);

  useEffect(() => {
    let live = true;
    setW(null); setErr(null); setHave([]);
    api.trailWear(id, month).then((x) => { if (live) setW(x); }).catch((e) => { if (live) setErr((e as Error).message); });
    return () => { live = false; };
  }, [id, month]);

  const pieces = w?.pieces ?? [];
  const toGet = pieces.filter((p) => !have.includes(p.slot));
  const total = (k: Tier) => toGet.reduce((n, p) => n + (p.products?.[k]?.price ?? 0), 0);
  const picks: BuyPick[] = useMemo(() => toGet.flatMap((p) => {
    const it = p.products?.[tier] ?? p.products?.medium ?? p.products?.cheap ?? p.products?.premium;
    return it ? [{ slot: p.slot, label: p.name.replace(/\s*\/.*$/, ""), item: it, cheaper: p.products?.cheap, better: p.products?.premium }] : [];
  }), [toGet, tier]); // eslint-disable-line react-hooks/exhaustive-deps
  const cur = picks[0]?.item.currency;
  const boots = pieces.find((p) => p.slot === "footwear");
  const toggle = (slot: string) => setHave((h) => (h.includes(slot) ? h.filter((x) => x !== slot) : [...h, slot]));
  const cold = w?.coldest;
  const wx = w?.weather;

  return (
    <section className="x-trip ip-bag" id="bag" aria-label="What to wear">
      <div className="ip-bag-in">
        <header className="ip-bag-h">
          <h2>What to wear <span>{name} · {MONTHS[month - 1]}</span></h2>
          {!w && !err && <span className="spin" aria-label="Updating" />}
        </header>
        {onMonth && (
          <div className="mf-months ww-months" role="radiogroup" aria-label="When">
            {MONTHS.map((m, i) => (
              <button type="button" role="radio" key={m} aria-checked={i + 1 === month}
                className={`${i + 1 === month ? "on" : ""}${months?.includes(i + 1) ? " best" : ""}`} onClick={() => onMonth(i + 1)}>{m.slice(0, 3)}</button>
            ))}
          </div>
        )}
        {err && <p className="err">{err}</p>}
        {!w && !err && <p className="loading"><span className="spin" /></p>}
        {w && (
          <div className="ww">
            {!w.in_season && <p className="x-alert warn">{MONTHS[month - 1]} is outside the walk's season: snow, closures or bad weather are likely.</p>}
            {(cold || wx) && (
              <div className="x-cold-top">
                <div className="x-cold-line">
                  <span className="n">{Math.round(cold ? cold.feels_like_c : wx!.tmin)}°</span>
                  <span className="t"><b>The coldest moment</b> {cold ? `${cold.where.charAt(0).toUpperCase()}${cold.where.slice(1)}. ` : ""}Your clothes are sized for this.</span>
                </div>
                {wx && (
                  <ul className="ww-wx" aria-label="Weather at the start">
                    <li><small>At the start</small><b>{Math.round(wx.tmin)}–{Math.round(wx.tmax)}°</b></li>
                    <li><small>Wind</small><b>{Math.round(wx.wind_kmh)} km/h</b></li>
                    <li><small>Rain</small><b>{Math.round(wx.rain_chance)}%</b></li>
                    {cold && <li><small>Coldest at</small><b>{Math.round(cold.altitude_m).toLocaleString("en-US")} m</b></li>}
                    <li><small>Source</small><b>{wx.source === "climate" ? "Past years" : "Forecast"}</b></li>
                  </ul>
                )}
              </div>
            )}

            <h2 className="x-h2" id="your-list">Your list</h2>
            <div className="x-bag-top x-rise">
              <div>
                <div className="x-k">Everything you still need</div>
                <div className="x-total" aria-live="polite">{money(total(tier), cur)}</div>
                <div className="x-facts">
                  <span>{toGet.length} to get</span><span>{have.length} yours</span>
                  {picks.length > 0 && <button type="button" className="x-link" onClick={() => setBuyOpen(true)}>Buy them all</button>}
                </div>
              </div>
              <div className="x-seg big" role="group" aria-label="Budget">
                {TIERS.map((k) => (
                  <button key={k} type="button" aria-pressed={k === tier} onClick={() => setTier(k)}>
                    {TIER_LABEL[k]}<small>{money(total(k), cur)}</small>
                  </button>
                ))}
              </div>
            </div>

            <div className="x-items">
              {pieces.filter((p) => !have.includes(p.slot)).map((p) => {
                const it = p.products?.[tier] ?? null;
                const why = p.slot === "footwear" && boots
                  ? `${FOOT[boots.footwear_type ?? ""] ?? "Shoes"}${boots.ankle_support ? ", ankle support" : ""}${boots.waterproof ? ", waterproof" : ""}.`
                  : null;
                return (
                  <article key={p.slot} className="x-item">
                    <div className="x-ic">
                      {it?.image_url ? <img src={it.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" /> : <ProductArt slot={p.slot} className="x-art" />}
                    </div>
                    <div className="x-pc">{p.name}{p.waterproof ? " · waterproof" : ""}</div>
                    <div className="x-pn">{it ? `${it.brand} ${it.name}` : "Nothing in the shops we check yet"}</div>
                    {it && <div className="x-shop">{it.merchant}</div>}
                    {why && <div className="x-where"><p>{why}</p></div>}
                    <div className="x-row"><span className="x-price">{it ? money(it.price, it.currency) : "—"}</span></div>
                    <div className="x-acts">
                      {it && <a className="x-btn y" href={buyUrl(it.id, undefined, tier, p.slot)} target="_blank" rel="sponsored noopener">Buy</a>}
                      <button type="button" className="x-btn" onClick={() => toggle(p.slot)}>I have one</button>
                    </div>
                  </article>
                );
              })}
            </div>
            {have.length > 0 && (
              <div className="x-yours">
                <b>Already yours</b>
                {pieces.filter((p) => have.includes(p.slot)).map((p) => (
                  <button key={p.slot} type="button" className="x-chip" title="I need one" aria-label={`I need one: ${p.name}`} onClick={() => toggle(p.slot)}>{p.name.replace(/\s*\/.*$/, "")}</button>
                ))}
              </div>
            )}
            <p className="x-disc">{config?.disclosure} Prices can change: the shop's page is what counts.</p>
          </div>
        )}
      </div>
      <KitSheet open={buyOpen} onClose={() => setBuyOpen(false)} title={`Your kit for ${name}`} picks={picks} />
    </section>
  );
}
