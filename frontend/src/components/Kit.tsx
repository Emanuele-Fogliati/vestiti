import { useState } from "react";
import { Link } from "react-router-dom";
import { api, buyUrl, rentUrl } from "../lib/api";
import { useApp } from "../lib/app-context";
import { money } from "../lib/format";
import { TIER_LABEL, TIERS, type KitLine, type Plans, type Tier } from "../lib/types";
import { ProductArt } from "./ProductArt";
import { specRows } from "../lib/specs";
import { Stars } from "./Stars";
import { SwapDrawer } from "./SwapDrawer";

function Card({ line, tripId, tier, onSwap, onChanged }: {
  line: KitLine; tripId: string; tier: Tier; onSwap: () => void; onChanged: () => void;
}) {
  const { toast } = useApp();
  const it = line.item;
  const fit = it?.fit;
  const have = line.kind === "have";
  const owned = line.kind === "owned";
  const rent = line.kind === "rent";
  const chip = have ? <span className="chip own">YOURS</span>
    : owned ? <span className="chip own">YOURS</span>
    : rent ? <span className="chip rent">RENT</span>
    : fit && fit.passes && fit.stars >= 3 ? <span className="chip pass">PASS</span>
    : fit ? <span className="chip marginal">CHECK</span> : null;

  async function choose(choice: string, extra: Record<string, string> = {}) {
    await api.select(tripId, { tier, slot: line.slot, choice, ...extra });
    toast(choice === "auto" ? "Back to the automatic pick."
      : choice === "have" ? "Marked as yours: removed from the total."
      : choice === "buy" ? "Added to the shopping list." : "Kit updated.");
    onChanged();
  }

  return (
    <article className={`card${owned || have ? " owned" : ""}${line.kind === "none" ? " none" : ""}`}>
      <div className="fig">
        {it?.image_url ? <img src={it.image_url} alt={it.name} loading="lazy" /> : <ProductArt slot={line.slot} />}
        <span className="lt">{line.code} · {line.slot_name.toUpperCase()}</span>
        {chip}
        {line.locked && !have && <span className="chip lock">YOUR CHOICE</span>}
      </div>
      <div className="body">
        {have ? (
          <>
            <div className="brandline">{line.assumed ? "Most people already have one" : "You said you have one"}</div>
            <h3>Your {line.slot_name.toLowerCase()}</h3>
            <p className="note">{line.note}</p>
            <p className="okline">Not in the total.</p>
          </>
        ) : rent && line.rental ? (
          <>
            <div className="brandline">{line.rental.partner}</div>
            <h3>Rent a {line.slot_name.toLowerCase()}</h3>
            <p className="model">{line.rental.days} days × {money(line.rental.daily_rate)} · {line.rental.start} → {line.rental.end}</p>
            {line.rental.is_placeholder && <p className="note">Placeholder partner: no real rental deal yet.</p>}
            <div className="priceline"><span className="price">{money(line.rental.price)}</span>
              <a className="buy" href={rentUrl(line.rental, tripId)} target="_blank" rel="sponsored noopener">Book</a></div>
          </>
        ) : it ? (
          <>
            <div className="brandline">{it.brand}{owned ? " · your wardrobe" : ` · ${it.merchant}`}</div>
            <h3>{it.name}</h3>
            {fit && <Stars value={fit.stars} label="fit for this trip" />}
            {it.rating && !owned && <span className="small muted">Shoppers: {it.rating.toFixed(1)}/5 ({it.review_count.toLocaleString("en-US")})</span>}
            <dl className="specs">{specRows(it, line.slot).map(([k, v]) => <div key={k} style={{ display: "contents" }}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
            {fit && fit.positives.length > 0 && <ul className="pos">{fit.positives.slice(0, 2).map((p) => <li key={p}>{p}</li>)}</ul>}
            {fit && fit.issues.length > 0 && <ul className="issues">{fit.issues.slice(0, 2).map((p) => <li key={p}>{p}</li>)}</ul>}
            {owned ? (
              <p className="okline">{line.owned_verdict === "fine" ? "Already yours and fine for this trip. Nothing to buy." : "Yours. It works, but see the notes above."}</p>
            ) : (
              <div className="priceline"><span className="price">{money(it.price, it.currency)}</span>
                <a className="buy" href={buyUrl(it.id, tripId, tier, line.slot)} target="_blank" rel="sponsored noopener">Buy</a></div>
            )}
          </>
        ) : (
          <><h3>{line.slot_name}</h3><p className="note">{line.note ?? "Nothing selected."}</p></>
        )}
        {line.rent_suggestion && (
          <p className="rentline">Needed {line.requirement.days_needed} of {line.requirement.trip_days} days: renting costs {money(line.rent_suggestion.price)} (save {money(line.rent_suggestion.saving ?? 0)}).{" "}
            <button type="button" className="link" onClick={() => choose("rent")}>Rent instead</button></p>
        )}
        {have ? (
          <div className="act2">
            <button type="button" className="buy" onClick={() => choose("buy")}>I need one</button>
            <Link className="buy" to={`/wardrobe?slot=${line.slot}`}>Check mine</Link>
            {!line.assumed && <button type="button" className="buy" onClick={() => choose("auto")}>Auto</button>}
          </div>
        ) : (
        <div className="act2">
          {!owned && line.kind !== "none" && (
            <button type="button" className="buy" title="Already in your wardrobe: no need to say which one" onClick={() => choose("have")}>I have it</button>
          )}
          <button type="button" className="buy" onClick={onSwap}>Swap{line.alternatives ? ` (${line.alternatives})` : ""}</button>
          {line.owned_alternatives.length > 0 && !owned && (
            <button type="button" className="buy" onClick={() => choose("owned", { wardrobe_item_id: line.owned_alternatives[0].id })}>Use mine</button>
          )}
          {owned && <button type="button" className="buy" onClick={onSwap}>Buy one instead</button>}
          {line.rental_options.length > 0 && !rent && !line.rent_suggestion && (
            <button type="button" className="buy" onClick={() => choose("rent")}>Rent</button>
          )}
          {line.locked && <button type="button" className="buy" onClick={() => choose("auto")}>Auto</button>}
          {!line.locked && line.kind !== "none" && ["headwear", "gloves", "sun_hat", "shell_bottom", "base_bottom"].includes(line.slot) && (
            <button type="button" className="buy" title="I'll do without it" onClick={() => choose("skip")}>Skip</button>
          )}
        </div>
        )}
      </div>
    </article>
  );
}

function tp_genders(items: KitLine[]): string[] {
  return items.map((l) => l.item?.gender ?? "unisex").filter((g) => g === "men" || g === "women");
}

function upgradeTitle(ups: { added: boolean }[]): string {
  const added = ups.filter((u) => u.added).length;
  const swapped = ups.length - added;
  const parts = [swapped ? `upgraded ${swapped} piece${swapped > 1 ? "s" : ""}` : "",
    added ? `added ${added} layer${added > 1 ? "s" : ""}` : ""].filter(Boolean);
  return `We ${parts.join(" and ")} so this budget keeps you warm`;
}

export function Kit({ tripId, plans, tier, setTier, onChanged }: {
  tripId: string; plans: Plans; tier: Tier; setTier: (t: Tier) => void; onChanged: () => void;
}) {
  const { config, user, refreshUser, toast } = useApp();
  const [swap, setSwap] = useState<KitLine | null>(null);
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
  const tp = plans.tiers[tier];
  const fine = tp.owned_notes.filter((n) => n.verdict === "fine");
  const assumed = tp.items.filter((l) => l.kind === "have" && l.assumed);
  const bad = tp.owned_notes.filter((n) => n.verdict !== "fine");
  const max = Math.max(...plans.comparison.map((c) => c.total), 1);
  const statusText = { covered: "Covered", marginal: "Marginal", cold: "Too cold" } as const;

  return (
    <>
      <div className="toolbar">
        <div className="wrap">
          <div className="tb-l"><span className="label">Budget</span>
            <div className="seg" role="group" aria-label="Budget">
              {TIERS.map((t) => <button key={t} type="button" aria-pressed={t === tier} onClick={() => setTier(t)}>{TIER_LABEL[t]}</button>)}
            </div>
          </div>
          <div className="tb-l"><span className="label">Cut</span>
            <div className="seg" role="group" aria-label="Cut">
              {(["men", "women", "any"] as const).map((g) => (
                <button key={g} type="button" aria-pressed={g === pref} onClick={() => setCut(g)}>
                  {g === "men" ? "Men" : g === "women" ? "Women" : "Any"}</button>))}
            </div>
          </div>
          <div className="tsum" aria-live="polite"><span className="label">Kit total</span>
            <span className="big">{money(tp.totals.total)}</span>
            {tp.totals.owned_value_saved > 0 && <span className="sv">−{money(tp.totals.owned_value_saved)} thanks to what you own</span>}
          </div>
        </div>
      </div>
      <div className="wrap stack">
        {assumed.length > 0 && (
          <div className="banner ok"><b>{assumed.length} basics counted as yours: {assumed.map((l) => l.slot_name.toLowerCase()).join(", ")}.</b>{" "}
            Most people already have them, so they are not in the total. Missing one? Tap “I need one” on its card.</div>
        )}
        {fine.length > 0 && (
          <div className="banner ok"><b>Good news: {fine.length} {fine.length === 1 ? "thing you own is" : "things you own are"} fine for this trip.</b>
            <ul>{fine.map((n) => <li key={n.slot}>{n.message}</li>)}</ul></div>
        )}
        {bad.length > 0 && (
          <div className="banner warn"><b>Honest check on your wardrobe</b><ul>{bad.map((n) => <li key={n.slot + n.item.id}>{n.message}</li>)}</ul></div>
        )}
        {mixed && (
          <div className="banner warn"><b>This kit mixes men's and women's cuts.</b> Pick yours so every piece fits:{" "}
            <button type="button" className="link" onClick={() => setCut("men")}>Men</button>{" · "}
            <button type="button" className="link" onClick={() => setCut("women")}>Women</button></div>
        )}
        {tp.auto_upgrades.length > 0 && (
          <div className="banner info"><b>{upgradeTitle(tp.auto_upgrades)}</b>
            <ul>{tp.auto_upgrades.map((a) => (
              <li key={a.slot}><b>{a.from ? `${a.from.name} → ${a.to.name}` : `+ ${a.to.name}`}</b>{" "}
                <span className="muted">({a.extra_cost > 0 ? "+" : a.extra_cost < 0 ? "−" : "±"}{money(Math.abs(a.extra_cost))})</span>
                <br /><span className="small">{a.reason}</span></li>))}</ul></div>
        )}
        {tp.advice && (
          <div className="banner info"><b>{TIER_LABEL[tp.advice.tier]} is only {money(tp.advice.extra_cost)} more</b>
            <p>{tp.advice.message}{" "}
              <button type="button" className="link" onClick={() => setTier(tp.advice!.tier)}>See {TIER_LABEL[tp.advice.tier]}</button></p></div>
        )}
        {tp.shortfall && (
          <div className={`banner ${tp.shortfall.avoidable ? "info" : "warn"}`}>
            <b>{tp.shortfall.avoidable ? `Cold evenings outside at ${tp.shortfall.stage}` : `Warmth check: still too cold at ${tp.shortfall.stage}`}</b>
            <p>{tp.shortfall.message}</p></div>
        )}
        {plans.catalog_note && <p className="small muted">{plans.catalog_note}</p>}
        <div className="grid">
          {tp.items.map((l) => <Card key={l.slot} line={l} tripId={tripId} tier={tier} onSwap={() => setSwap(l)} onChanged={onChanged} />)}
        </div>
        <p className="disclosure">{config?.disclosure} Links open the shop in a new tab. Prices and stock can change; the shop's page is what counts.</p>
      </div>

      <section className="band" id="total">
        <div className="wrap">
          <header className="sh"><p className="sh-k">The total</p><h2>What this trip costs you</h2>
            <p>Owned pieces cost nothing. Rentals are priced for the days you need them.</p></header>
          <div className="ledger">
            <div className="lt-box">
              <table className="lt">
                <thead><tr><th>Piece</th><th>Model</th><th>Source</th><th className="num">Cost</th></tr></thead>
                <tbody>
                  {tp.items.map((l) => (
                    <tr key={l.slot} className={l.kind === "owned" || l.kind === "have" ? "ownrow" : ""}>
                      <td>{l.slot_name}</td>
                      <td>{l.kind === "rent" ? l.rental?.partner : l.kind === "have" ? "Yours" : l.item ? `${l.item.brand} ${l.item.name}` : "—"}</td>
                      <td><span className={`src ${l.kind === "owned" || l.kind === "have" ? "own" : l.kind === "rent" ? "rent" : ""}`}>
                        {l.kind === "owned" || l.kind === "have" ? "OWNED" : l.kind === "rent" ? "RENT" : l.kind === "none" ? "SKIP" : TIER_LABEL[tier].toUpperCase()}</span></td>
                      <td className="num">{l.kind === "owned" || l.kind === "have" || l.kind === "none" ? "—" : money(l.cost)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot><tr><td colSpan={3}>Total to spend</td><td className="num">{money(tp.totals.total)}</td></tr></tfoot>
              </table>
            </div>
            <div className="totalp">
              <div className="label">Your kit · {tp.items.length} pieces · {TIER_LABEL[tier]}</div>
              <div className="big">{money(tp.totals.total)}</div>
              <div className="meta">{tp.totals.items_to_buy} to buy · {tp.totals.items_owned} from your wardrobe · {tp.totals.items_rented} rented</div>
              <div className="cmp">
                {plans.comparison.map((c) => (
                  <div key={c.tier} className={`cmp-row${c.tier === tier ? " you" : ""}`}>
                    <span>{TIER_LABEL[c.tier]}</span>
                    <span className="track"><span className="fill" style={{ width: `${(c.total / max) * 100}%` }} /></span>
                    <span className="val">{money(c.total)}</span>
                  </div>
                ))}
              </div>
              <div className="tfacts">
                <div><div className="label">Warmth check</div><div className="v">{tp.warmth.status === "cold" && tp.shortfall?.avoidable ? "OK, cold evenings" : statusText[tp.warmth.status]}</div>
                  {tp.shortfall && <div className="small muted">{tp.shortfall.gap_clo.toFixed(2)} clo short at {tp.shortfall.stage} {tp.shortfall.mode === "rest" ? "at rest" : "on the move"}</div>}</div>
                <div><div className="label">Saved by owning</div><div className="v">{money(tp.totals.owned_value_saved)}</div></div>
                <div><div className="label">Rentals</div><div className="v">{money(tp.totals.rent)}</div></div>
                <div><div className="label">Pack weight</div><div className="v">{(tp.totals.weight_g / 1000).toFixed(1)} kg</div></div>
              </div>
            </div>
          </div>
        </div>
      </section>
      {swap && <SwapDrawer tripId={tripId} tier={tier} line={swap} onClose={() => setSwap(null)} onChanged={() => { setSwap(null); onChanged(); }} />}
    </>
  );
}
