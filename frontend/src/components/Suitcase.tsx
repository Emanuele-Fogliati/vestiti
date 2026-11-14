import { useEffect, useState } from "react";
import { api, buyUrl } from "../lib/api";
import { useApp } from "../lib/app-context";
import { dayMonth, money } from "../lib/format";
import type { Item, KitLine, Tier, TierPlan } from "../lib/types";
import { ProductArt } from "./ProductArt";
import { Sheet } from "./Sheet";
import { reqText } from "./SwapDrawer";

type State = "choose" | "have" | "picked" | "rent";

/** What the traveller has decided about a piece: nothing yet (our automatic pick is only a
 *  suggestion), "I have one", a product they picked, or a rental. */
export function stateOf(l: KitLine): State {
  if (l.kind === "have" || l.kind === "owned") return "have";
  if (l.kind === "rent") return "rent";
  return l.locked ? "picked" : "choose";
}

const TAG: Record<State, string> = { choose: "?", have: "✓", picked: "", rent: "R" };

/** The bag (design S11): stops on top, every piece inside a yellow suitcase. Dashed = still to
 *  choose. Tap a piece to choose it: a product from the shops, or "I already have one". */
export function Suitcase({ tripId, tier, tp, onChanged }: {
  tripId: string; tier: Tier; tp: TierPlan; onChanged: () => void;
}) {
  const [stop, setStop] = useState(-1);
  const [open, setOpen] = useState<KitLine | null>(null);
  const lines = tp.items.filter((l) => l.kind !== "none");
  const stops = tp.stops ?? [];
  const left = lines.filter((l) => stateOf(l) === "choose");
  const used = (l: KitLine) => stop < 0 || (l.where?.[stop] ?? "worn") !== "none";
  const here = stop < 0 ? lines.length : lines.filter(used).length;
  const kg = tp.totals.weight_g / 1000;

  return (
    <section className="sc" aria-label="Your bag">
      <div className="sc-stops" role="group" aria-label="Show the pieces for">
        <button type="button" className={`sc-pill${stop < 0 ? " on" : ""}`} onClick={() => setStop(-1)}>
          <span className="sc-pill-ic" aria-hidden="true"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><rect x="5" y="7" width="14" height="13" rx="3" /><path d="M9 7V4h6v3" /></svg></span>
          <span><b>Whole trip</b><small>{lines.length} pieces</small></span>
        </button>
        {stops.map((s, i) => (
          <button key={s.index} type="button" className={`sc-pill${stop === i ? " on" : ""}`} onClick={() => setStop(i)}>
            <span><b>{s.name}</b><small>{dayMonth(s.start)}{s.end !== s.start ? `–${dayMonth(s.end)}` : ""}</small></span>
          </button>
        ))}
      </div>
      <p className="sc-sky">{stop < 0 ? "Everything you pack. Tap a piece to choose it." : `In ${stops[stop].name} you use ${here} of ${lines.length} pieces.`}</p>
      <div className="sc-bag">
        <i className="sc-handle" aria-hidden="true" />
        <div className="sc-body">
          {lines.map((l) => {
            const st = stateOf(l), photo = st === "picked" || st === "rent" ? l.item?.image_url : null;
            return (
              <button key={l.slot} type="button" className={`sc-piece ${st}${used(l) ? "" : " off"}`} onClick={() => setOpen(l)}
                aria-label={`${l.slot_name}: ${st === "choose" ? "choose one" : st === "have" ? "you have it" : l.item ? `${l.item.brand} ${l.item.name}` : "rented"}`}>
                <span className="sc-disc">{photo ? <img src={photo} alt="" loading="lazy" /> : <ProductArt slot={l.base_slot ?? l.slot} className="sc-art" />}</span>
                {TAG[st] && <span className={`sc-tag ${st}`}>{TAG[st]}</span>}
                <span className="sc-name">{st === "picked" && l.item ? l.item.brand : l.slot_name}</span>
              </button>
            );
          })}
        </div>
        <i className="sc-wheel l" aria-hidden="true" /><i className="sc-wheel r" aria-hidden="true" />
        <span className="sc-label">{kg.toFixed(1)} KG<small>{lines.length} pieces</small></span>
      </div>
      <div className="sc-legend">
        <span><i className="choose" />to choose</span><span><i className="have">✓</i>you have it</span><span><i className="picked" />picked to buy</span>
      </div>
      <div className="sc-cta">
        {left.length > 0
          ? <button type="button" onClick={() => setOpen(left[0])}>Choose the {left.length} dashed {left.length === 1 ? "piece" : "pieces"} <span>→</span></button>
          : <a href="#your-list">Your list <span>· {money(tp.totals.total)}</span></a>}
      </div>
      {open && <Picker tripId={tripId} tier={tier} line={open} stops={stops.map((s) => s.name)} onClose={() => setOpen(null)}
        onDone={() => { setOpen(null); onChanged(); }} />}
    </section>
  );
}

/** Choose one piece: "I already have one", our pick, or any product of the shops that fits. */
function Picker({ tripId, tier, line, stops, onClose, onDone }: {
  tripId: string; tier: Tier; line: KitLine; stops: string[]; onClose: () => void; onDone: () => void;
}) {
  const { toast } = useApp();
  const [items, setItems] = useState<Item[] | null>(null);
  const [brands, setBrands] = useState<string[]>([]);
  const [brand, setBrand] = useState("");
  const [busy, setBusy] = useState(false);
  const st = stateOf(line);
  useEffect(() => {
    api.slotProducts(tripId, line.slot, { brand, sort: "fit", only_passing: true })
      .then((r) => { setItems(r.items); setBrands(r.brands); }).catch(() => setItems([]));
  }, [tripId, line.slot, brand]);

  async function choose(choice: string, product_id?: string) {
    setBusy(true);
    try {
      await api.select(tripId, { tier, slot: line.slot, choice, ...(product_id ? { product_id } : {}) });
      toast(choice === "have" ? `${line.slot_name}: yours, off the list.` : `${line.slot_name}: picked.`);
      onDone();
    } catch (e) { toast((e as Error).message); setBusy(false); }
  }

  const where = (line.where ?? []).map((u, i) => (u !== "none" ? stops[i] : null)).filter(Boolean);
  const req = reqText(line.requirement);
  const ours = line.kind === "product" && line.item ? line.item.id : null;
  const list = (items ?? []).slice().sort((a, b) => (a.id === ours ? -1 : b.id === ours ? 1 : 0));

  return (
    <Sheet open onClose={onClose} title={line.slot_name}>
      <div className="pk">
        <p className="pk-why"><b>What it must do.</b> {req ? `${req[0].toUpperCase()}${req.slice(1)}.` : ""} {where.length ? `Used in ${where.join(", ")}.` : ""}</p>
        <button type="button" className={`pk-have${st === "have" ? " on" : ""}`} disabled={busy} onClick={() => choose(st === "have" ? "buy" : "have")}>
          {st === "have" ? "✓ You have it · tap if you need one" : "I already have one"}
        </button>
        <div className="pk-h"><b>Or pick one</b><span>{items ? `${items.length} that fit this trip` : ""}</span></div>
        {brands.length > 1 && (
          <div className="pk-brands">
            {["", ...brands].map((b) => <button key={b || "all"} type="button" className={brand === b ? "on" : ""} onClick={() => setBrand(b)}>{b || "All"}</button>)}
          </div>
        )}
        {!items && <p><span className="spin" /></p>}
        <div className="pk-list">
          {list.map((it) => {
            const mine = line.locked && line.item?.id === it.id;
            return (
              <article key={it.id} className={`pk-item${mine ? " on" : ""}`}>
                <div className="pk-img">{it.image_url ? <img src={it.image_url} alt="" loading="lazy" /> : <ProductArt slot={line.base_slot ?? line.slot} className="sc-art" />}</div>
                <div className="pk-t">
                  <small>{it.brand}{it.id === ours && !line.locked ? " · our pick" : ""}</small>
                  <b>{it.name}</b>
                  <span>{[it.specs.weight_g ? `${it.specs.weight_g} g` : "", it.specs.clo ? `warmth ${it.specs.clo.toFixed(2)} clo` : "", it.merchant].filter(Boolean).join(" · ")}</span>
                  <div className="pk-row">
                    <b className="pk-price">{money(it.price, it.currency)}</b>
                    {mine
                      ? <a className="pk-buy" href={buyUrl(it.id, tripId, tier, line.slot)} target="_blank" rel="sponsored noopener">Buy at {it.merchant} →</a>
                      : <button type="button" disabled={busy} onClick={() => choose("product", it.id)}>Pick</button>}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
        <p className="pk-disc">{list.some((i) => i.checked_at) ? "Prices and stock read from the shop's page. " : ""}The shop's page is what counts. If you buy through these links we may earn a small commission; it never changes the order.</p>
      </div>
    </Sheet>
  );
}
