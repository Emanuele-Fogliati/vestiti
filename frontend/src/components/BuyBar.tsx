import { buyUrl } from "../lib/api";
import { money } from "../lib/format";
import type { Item, Tier } from "../lib/types";
import { Garment, baseSlot } from "./Garment";
import { ProductArt } from "./ProductArt";

/** One piece to get: the product picked now, and the cheaper and better ones it can switch to. */
export interface BuyPick {
  slot: string;
  label: string;
  item: Item;
  cheaper?: Item | null;
  better?: Item | null;
}

const same = (a?: Item | null, b?: Item | null) => !!a && !!b && a.id === b.id;

/** A product as a small card: photo, what it is for, price, and Cheaper / Better. */
export function ProductCard({ p, tripId, tier, onPick }: {
  p: BuyPick; tripId?: string; tier?: Tier; onPick?: (slot: string, item: Item) => void;
}) {
  const it = p.item;
  const href = buyUrl(it.id, tripId, tier, tripId ? p.slot : undefined);
  const cheap = p.cheaper && !same(p.cheaper, p.better) ? p.cheaper : null;
  const better = p.better && !same(p.cheaper, p.better) ? p.better : null;
  return (
    <div className="mf-pcard">
      <a className="mf-pimg" href={href} target="_blank" rel="sponsored noopener" aria-label={`${it.brand} ${it.name} at ${it.merchant}`}>
        {it.image_url ? <img src={it.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" /> : <ProductArt slot={baseSlot(p.slot)} />}
      </a>
      <span className="mf-pk"><span>{p.label}</span><span className="mf-price">{money(it.price, it.currency)}</span></span>
      <a className="mf-pname" href={href} target="_blank" rel="sponsored noopener">{it.brand} {it.name}</a>
      {onPick && (cheap || better) && (
        <span className="mf-sw" role="group" aria-label={`${p.label}: cheaper or better`}>
          <button type="button" disabled={!cheap} aria-pressed={same(it, cheap)} onClick={() => cheap && !same(it, cheap) && onPick(p.slot, cheap)}
            title={cheap ? `${cheap.brand} ${cheap.name} · ${money(cheap.price, cheap.currency)}` : undefined}>Cheaper</button>
          <button type="button" disabled={!better} aria-pressed={same(it, better)} onClick={() => better && !same(it, better) && onPick(p.slot, better)}
            title={better ? `${better.brand} ${better.name} · ${money(better.price, better.currency)}` : undefined}>Better</button>
        </span>
      )}
    </div>
  );
}

export function ProductRow({ picks, tripId, tier, onPick }: {
  picks: BuyPick[]; tripId?: string; tier?: Tier; onPick?: (slot: string, item: Item) => void;
}) {
  return <div className="mf-prow">{picks.map((p) => <ProductCard key={p.slot} p={p} tripId={tripId} tier={tier} onPick={onPick} />)}</div>;
}

export const totalOf = (picks: BuyPick[]) => picks.reduce((n, p) => n + p.item.price, 0);

/** The bar at the bottom of the map, the same on Trips and Treks: what to get, and the total. */
export function BuyBar({ title, sub, picks, tripId, tier, onPick, onBuy, buyLabel, empty }: {
  title: string; sub: string; picks: BuyPick[]; tripId?: string; tier?: Tier;
  onPick?: (slot: string, item: Item) => void; onBuy?: () => void; buyLabel?: string; empty?: string;
}) {
  const cur = picks[0]?.item.currency;
  return (
    <section className="mf-float mf-buy" aria-label={title}>
      <div className="mf-buy-h"><b>{title}</b><span>{sub}</span></div>
      {picks.length ? <ProductRow picks={picks} tripId={tripId} tier={tier} onPick={onPick} />
        : <p className="mf-buy-none">{empty ?? "Your closet covers it. Nothing to buy."}</p>}
      <div className="mf-buy-go">
        <button type="button" className="mf-btn go" disabled={!picks.length || !onBuy} onClick={onBuy}>
          <BagIcon />{buyLabel ?? "Buy"}{picks.length ? ` · ${money(totalOf(picks), cur)}` : ""}
        </button>
        <span className="mf-fine">Prices from the shops. We may earn a commission.</span>
      </div>
    </section>
  );
}

export function BagIcon() {
  return <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 9a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2zM9 7V5a3 3 0 0 1 6 0v2" /></svg>;
}

export { Garment };
