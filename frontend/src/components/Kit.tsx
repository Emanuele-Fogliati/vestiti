import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, buyUrl, rentUrl } from "../lib/api";
import { useApp } from "../lib/app-context";
import { dayMonth, money } from "../lib/format";
import { TIER_LABEL, TIERS, type KitLine, type Plans, type Tier } from "../lib/types";
import { ProductArt } from "./ProductArt";
import { specRows } from "../lib/specs";
import { Stars } from "./Stars";
import { SwapDrawer } from "./SwapDrawer";
import { BrandPicker } from "./BrandPicker";
import { Sheet } from "./Sheet";

/** A number that counts to its new value instead of jumping. */
function useTween(value: number, ms = 650): number {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const rm = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    const a = from.current, t0 = performance.now();
    if (rm || a === value) { from.current = value; setShown(value); return; }
    let raf = 0;
    const step = (now: number) => {
      const k = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - k, 3);
      const v = a + (value - a) * e;
      from.current = v;
      setShown(v);
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, ms]);
  return shown;
}

function Card({ line, tripId, tier, onSwap, onChanged }: {
  line: KitLine; tripId: string; tier: Tier; onSwap: () => void; onChanged: () => void;
}) {
  const { toast } = useApp();
  const [more, setMore] = useState(false);
  const it = line.item;
  const fit = it?.fit;
  const have = line.kind === "have";
  const owned = line.kind === "owned";
  const rent = line.kind === "rent";
  const badge = have || owned ? <span className="x-badge own">Yours</span>
    : rent ? <span className="x-badge">Rent</span>
    : fit && fit.passes && fit.stars >= 3 ? <span className="x-badge ok"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12l4 4 10-10" /></svg>Passes</span>
    : fit ? <span className="x-badge warn">Check</span> : null;

  async function choose(choice: string, extra: Record<string, string> = {}) {
    await api.select(tripId, { tier, slot: line.slot, choice, ...extra });
    toast(choice === "auto" ? "Back to the automatic pick."
      : choice === "have" ? "Yours: taken off the total."
      : choice === "buy" ? "Back on the list." : "Bag updated.");
    onChanged();
  }

  const name = have ? (line.assumed ? "Most people have one" : "You said you have one")
    : rent && line.rental ? `${line.rental.partner} · ${line.rental.days} days`
    : it ? `${it.brand} ${it.name}` : (line.note ?? "Nothing selected");
  const price = have || owned || line.kind === "none" ? null : rent && line.rental ? line.rental.price : it ? it.price : null;

  return (
    <article className={`x-item${owned || have ? " owned" : ""}${line.preferred_brand ? " fav" : ""}`}>
      <div className="x-ic">
        {it?.image_url ? <img src={it.image_url} alt="" loading="lazy" /> : <ProductArt slot={line.base_slot ?? line.slot} className="x-art" />}
        <span className="x-lay">{line.code}</span>
        {line.preferred_brand && !line.locked && <span className="x-fav">Your brand</span>}
        {line.locked && !have && <span className="x-fav">Your pick</span>}
      </div>
      <div className="x-pc">{line.slot_name}</div>
      <div className="x-pn">{name}</div>
      {it && line.kind === "product" && (
        <div className="x-shop" title={it.checked_at ? "Price and stock read from the shop's page that day" : "Not checked with the shop yet: the real price may differ"}>
          {it.merchant} · {it.checked_at ? `checked ${dayMonth(it.checked_at)}` : "indicative price"}
        </div>)}
      <div className="x-row">
        <span className="x-price">{price !== null ? money(price, it?.currency) : "—"}</span>
        {badge}
      </div>
      <div className="x-acts">
        {!have && !owned && line.kind !== "none" && (rent && line.rental
          ? <a className="x-btn y" href={rentUrl(line.rental, tripId)} target="_blank" rel="sponsored noopener">Book</a>
          : it ? <a className="x-btn y" href={buyUrl(it.id, tripId, tier, line.slot)} target="_blank" rel="sponsored noopener">Buy</a> : null)}
        {have
          ? <button type="button" className="x-btn" onClick={() => choose("buy")}>I need one</button>
          : !owned && line.kind !== "none" && <button type="button" className="x-btn" onClick={() => choose("have")}>I have one</button>}
        <button type="button" className="x-btn ghost" aria-expanded={more} onClick={() => setMore(!more)} aria-label="More">⋯</button>
      </div>
      {more && (
        <div className="x-moreb">
          <div className="x-acts">
            <button type="button" className="x-btn" onClick={onSwap}>Swap{line.alternatives ? ` (${line.alternatives})` : ""}</button>
            {line.owned_alternatives.length > 0 && !owned && <button type="button" className="x-btn" onClick={() => choose("owned", { wardrobe_item_id: line.owned_alternatives[0].id })}>Use mine</button>}
            {have && <Link className="x-btn" to={`/wardrobe?slot=${line.base_slot ?? line.slot}`}>Check mine</Link>}
            {(line.rent_suggestion || line.rental_options.length > 0) && !rent && <button type="button" className="x-btn" onClick={() => choose("rent")}>Rent{line.rent_suggestion ? ` · save ${money(line.rent_suggestion.saving ?? 0)}` : ""}</button>}
            {(line.locked || (have && !line.assumed)) && <button type="button" className="x-btn" onClick={() => choose("auto")}>Auto</button>}
            {!line.locked && line.kind !== "none" && (!!line.zone || ["headwear", "gloves", "sun_hat", "shell_bottom", "base_bottom"].includes(line.slot)) && (
              <button type="button" className="x-btn" onClick={() => choose("skip")}>Skip it</button>)}
          </div>
          {it && fit && <Stars value={fit.stars} label="fit for this trip" />}
          {it && <dl className="x-specs">{specRows(it, line.base_slot ?? line.slot).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>}
          {fit && fit.issues.length > 0 && <ul className="x-list warn">{fit.issues.slice(0, 2).map((p) => <li key={p}>{p}</li>)}</ul>}
          {fit && fit.positives.length > 0 && <ul className="x-list">{fit.positives.slice(0, 2).map((p) => <li key={p}>{p}</li>)}</ul>}
          {(line.brand_note || (have && line.note)) && <p className="x-sub">{line.brand_note ?? line.note}</p>}
          {rent && line.rental?.is_placeholder && <p className="x-sub">Placeholder partner: no real rental deal yet.</p>}
        </div>
      )}
    </article>
  );
}

function tp_genders(items: KitLine[]): string[] {
  return items.map((l) => l.item?.gender ?? "unisex").filter((g) => g === "men" || g === "women");
}

export function Kit({ tripId, plans, tier, setTier, onChanged }: {
  tripId: string; plans: Plans; tier: Tier; setTier: (t: Tier) => void; onChanged: () => void;
}) {
  const { config, user, refreshUser, toast } = useApp();
  const [swap, setSwap] = useState<KitLine | null>(null);
  const [brandOpen, setBrandOpen] = useState(false);
  const [catalog, setCatalog] = useState<string[]>([]);
  const mine = user?.preferred_brands ?? [];

  async function openBrands() {
    setBrandOpen(true);
    if (!catalog.length) setCatalog((await api.profile()).catalog_brands);
  }
  async function setBrands(v: string[]) {
    await api.updateMe({ preferred_brands: v });
    await refreshUser();
    onChanged();
  }
  const pref = user?.gender_pref ?? "any";
  const genders = new Set(tp_genders(plans.tiers[tier].items));
  const mixed = pref === "any" && genders.has("men") && genders.has("women");

  async function setCut(g: "men" | "women" | "any") {
    if (g === pref) return;
    await api.updateMe({ gender_pref: g });
    await refreshUser();
    toast(g === "any" ? "Showing all cuts." : `Showing ${g}'s cuts and unisex pieces.`);
    onChanged();
  }
  const market = user?.market ?? "us";
  async function setMarket(m: "us" | "eu") {
    if (m === market) return;
    await api.updateMe({ market: m });
    await refreshUser();
    toast(m === "us" ? "Shopping in US stores, prices in $." : "Shopping in European stores, prices in €.");
    onChanged();
  }
  const tp = plans.tiers[tier];
  const haves = tp.items.filter((l) => l.kind === "have");
  const hot = plans.zones?.[0];
  const mainLines = tp.items.filter((l) => !l.zone && l.kind !== "have");
  const hotLines = tp.items.filter((l) => l.zone && l.kind !== "have");
  async function needOne(slot: string, name: string) {
    await api.select(tripId, { tier, slot, choice: "buy" });
    toast(`${name}: back on the list.`);
    onChanged();
  }
  const total = useTween(tp.totals.total);
  const fine = tp.owned_notes.filter((n) => n.verdict === "fine");
  const assumed = tp.items.filter((l) => l.kind === "have" && l.assumed);
  const bad = tp.owned_notes.filter((n) => n.verdict !== "fine");
  const cmp = new Map(plans.comparison.map((c) => [c.tier, c.total]));

  // the few things worth saying, one line each; the rest sits behind "Notes"
  const alerts: { k: string; warn?: boolean; text: ReactNode }[] = [];
  if (tp.shortfall) alerts.push({ k: "short", warn: !tp.shortfall.avoidable, text: tp.shortfall.message });
  if (mixed) alerts.push({ k: "mixed", warn: true, text: <>This bag mixes men's and women's cuts. <button type="button" className="x-link" onClick={() => setCut("men")}>Men</button> · <button type="button" className="x-link" onClick={() => setCut("women")}>Women</button></> });
  if (tp.advice) alerts.push({ k: "advice", text: <>{TIER_LABEL[tp.advice.tier]} is only {money(tp.advice.extra_cost)} more. <button type="button" className="x-link" onClick={() => setTier(tp.advice!.tier)}>See it</button></> });
  const notes: ReactNode[] = [];
  if (tp.brands) notes.push(tp.brands.message);
  if (assumed.length) notes.push(<>Counted as yours: {assumed.map((l) => l.slot_name.toLowerCase()).join(", ")}. Missing one? Tap “I need one”.</>);
  fine.forEach((n) => notes.push(n.message));
  bad.forEach((n) => notes.push(n.message));
  tp.auto_upgrades.forEach((a) => notes.push(<><b>{a.from ? `${a.from.name} → ${a.to.name}` : `+ ${a.to.name}`}</b> ({a.extra_cost >= 0 ? "+" : "−"}{money(Math.abs(a.extra_cost))}). {a.reason}</>));
  if (plans.catalog_note) notes.push(plans.catalog_note);

  return (
    <>
      <div className="x-bag-top x-rise">
        <div>
          <div className="x-k">Everything you still need</div>
          <div className="x-total" aria-live="polite">{money(Math.round(total))}</div>
          <div className="x-facts">
            <span>{tp.totals.items_to_buy} to buy</span><span>{tp.totals.items_owned} yours</span>
            {tp.totals.items_rented > 0 && <span>{tp.totals.items_rented} rented</span>}
            <span>{(tp.totals.weight_g / 1000).toFixed(1)} kg</span>
          </div>
        </div>
        <div className="x-seg big" role="group" aria-label="Budget">
          {TIERS.map((t) => (
            <button key={t} type="button" aria-pressed={t === tier} onClick={() => setTier(t)}>
              {TIER_LABEL[t]}<small>{cmp.has(t) ? money(cmp.get(t)!) : ""}</small>
            </button>
          ))}
        </div>
      </div>
      <div className="x-filters x-rise">
        <div className="x-seg sm" role="group" aria-label="Cut">
          {(["men", "women", "any"] as const).map((g) => (
            <button key={g} type="button" aria-pressed={g === pref} onClick={() => setCut(g)}>{g === "men" ? "Men" : g === "women" ? "Women" : "Any cut"}</button>))}
        </div>
        <div className="x-seg sm" role="group" aria-label="Shops">
          {(["us", "eu"] as const).map((m) => (
            <button key={m} type="button" aria-pressed={m === market} onClick={() => setMarket(m)}>{m === "us" ? "US shops $" : "EU shops €"}</button>))}
        </div>
        <button type="button" className={`x-chip${mine.length ? " on" : ""}`} onClick={openBrands}>
          {mine.length ? `♥ ${mine.join(", ")}` : "Brands you like"}
        </button>
      </div>
      {alerts.length > 0 && (
        <div className="x-alerts">{alerts.map((a) => <p key={a.k} className={`x-alert${a.warn ? " warn" : ""}`}>{a.text}</p>)}</div>
      )}
      {hot && <h3 className="x-h3">One bag for every stop</h3>}
      <div className="x-items">
        {mainLines.map((l) => <Card key={l.slot} line={l} tripId={tripId} tier={tier} onSwap={() => setSwap(l)} onChanged={onChanged} />)}
      </div>
      {hot && hotLines.length > 0 && (
        <>
          <h3 className="x-h3">Plus, for the hot days <small>{hot.names.join(", ")}</small></h3>
          <p className="x-sub">Light pieces for the day out. Jackets, fleece and the rest of the bag stay the same.</p>
          <div className="x-items">
            {hotLines.map((l) => <Card key={l.slot} line={l} tripId={tripId} tier={tier} onSwap={() => setSwap(l)} onChanged={onChanged} />)}
          </div>
        </>
      )}
      {haves.length > 0 && (
        <div className="x-yours">
          <b>Already yours</b>
          {haves.map((l) => (
            <button key={l.slot} type="button" className="x-chip" title="I need one" aria-label={`I need one: ${l.slot_name}`} onClick={() => needOne(l.slot, l.slot_name)}>{l.slot_name}</button>
          ))}
        </div>
      )}
      {notes.length > 0 && (
        <details className="x-more">
          <summary>Notes about this bag ({notes.length})</summary>
          <ul className="x-list">{notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </details>
      )}
      <p className="x-disc">{config?.disclosure} Prices can change: the shop's page is what counts.</p>
      <Sheet open={brandOpen} onClose={() => setBrandOpen(false)} title="Brands you like">
        <p className="x-sub" style={{ marginBottom: 12 }}>Used when they fit the trip and the budget.</p>
        <BrandPicker catalog={catalog} value={mine} onChange={setBrands} />
      </Sheet>
      {swap && <SwapDrawer tripId={tripId} tier={tier} line={swap} onClose={() => setSwap(null)} onChanged={() => { setSwap(null); onChanged(); }} />}
    </>
  );
}
