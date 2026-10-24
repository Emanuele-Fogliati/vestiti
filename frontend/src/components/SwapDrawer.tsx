import { useEffect, useState } from "react";
import { api, buyUrl } from "../lib/api";
import { money } from "../lib/format";
import type { Item, KitLine, Requirement, Tier } from "../lib/types";
import { specRows } from "../lib/specs";
import { ProductArt } from "./ProductArt";
import { Stars } from "./Stars";

const SORTS: [string, string][] = [
  ["fit", "Best fit"], ["price_asc", "Price: low to high"], ["price_desc", "Price: high to low"],
  ["warmth", "Warmest"], ["weight", "Lightest"], ["rating", "Shopper rating"], ["waterproof", "Most waterproof"],
];

function reqText(r: Requirement): string {
  const parts: string[] = [];
  if (r.ref_clo && !["shell_top", "shell_bottom", "footwear", "sun_hat", "socks"].includes(r.slot)) parts.push(`about ${r.ref_clo.toFixed(2)} clo (${r.level.replace("_", " ")})`);
  if (r.waterproof) parts.push(`waterproof${r.waterproof_grade_mm ? ` ${r.waterproof_grade_mm.toLocaleString("en-US")} mm+` : ""}`);
  if (r.footwear_type) parts.push(`at least ${r.footwear_type.replace("_", " ")}`);
  if (r.ankle_support) parts.push("ankle support");
  if (r.insulated) parts.push("insulated");
  if (r.breathable_high) parts.push("breathable for hard efforts");
  if (r.packable) parts.push("packs small");
  return parts.join(" · ");
}

export function SwapDrawer({ tripId, tier, line, onClose, onChanged }: {
  tripId: string; tier: Tier; line: KitLine; onClose: () => void; onChanged: () => void;
}) {
  const [q, setQ] = useState("");
  const [brand, setBrand] = useState("");
  const [sort, setSort] = useState("fit");
  const [only, setOnly] = useState(true);
  const [items, setItems] = useState<Item[] | null>(null);
  const [brands, setBrands] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    const t = window.setTimeout(async () => {
      const r = await api.slotProducts(tripId, line.slot, { q, brand, sort, only_passing: only });
      setItems(r.items);
      setBrands(r.brands);
    }, 200);
    return () => window.clearTimeout(t);
  }, [tripId, line.slot, q, brand, sort, only]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);

  async function pick(id: string, choice = "product") {
    setBusy(id);
    try {
      await api.select(tripId, { tier, slot: line.slot, choice, ...(choice === "product" ? { product_id: id } : { wardrobe_item_id: id }) });
      onChanged();
    } finally { setBusy(null); }
  }

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`Swap ${line.slot_name}`}>
        <header>
          <div className="row"><h2 style={{ fontSize: 22 }}>Swap · {line.slot_name}</h2><span className="spacer" />
            <button type="button" className="btn sm" onClick={onClose}>Close</button></div>
          <p className="small muted">This trip needs: {reqText(line.requirement) || "anything comfortable"}.</p>
          <div className="filters">
            <input type="search" placeholder="Search name or brand" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search" />
            <select value={brand} onChange={(e) => setBrand(e.target.value)} aria-label="Brand">
              <option value="">All brands</option>{brands.map((b) => <option key={b}>{b}</option>)}
            </select>
            <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort">
              {SORTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>
          <label className="check"><input type="checkbox" checked={only} onChange={(e) => setOnly(e.target.checked)} /> Only items that meet the trip's needs</label>
        </header>
        <div className="dbody">
          {line.owned_alternatives.map((o) => (
            <div className={`prow${line.item?.id === o.id ? " cur" : ""}`} key={o.id}>
              <div className="ph-s"><ProductArt slot={line.slot} /></div>
              <div><div className="nm">{o.name}<span className="tag">yours</span></div>
                {o.fit && <Stars value={o.fit.stars} label="fit" />}
                {o.fit?.issues.length ? <div className="note">{o.fit.issues[0]}</div> : null}</div>
              <div className="right"><span className="price">{money(0)}</span>
                <button className="buy" type="button" disabled={busy === o.id || line.item?.id === o.id} onClick={() => pick(o.id, "owned")}>Use mine</button></div>
            </div>
          ))}
          {items === null ? <p className="loading"><span className="spin" /></p> : items.length === 0 ? (
            <p className="empty">Nothing matches. Clear the filters or untick "only items that meet the trip's needs".</p>
          ) : items.map((it) => (
            <div className={`prow${line.item?.id === it.id ? " cur" : ""}${it.fit && !it.fit.passes ? " fail" : ""}`} key={it.id}>
              <div className="ph-s">{it.image_url ? <img src={it.image_url} alt="" /> : <ProductArt slot={line.slot} />}</div>
              <div style={{ minWidth: 0 }}>
                <div className="brandline">{it.brand} · {it.merchant}</div>
                <div className="nm">{it.name}</div>
                {it.fit && <Stars value={it.fit.stars} label="fit" />}
                <div className="meta">{specRows(it, line.slot).map(([k, v]) => `${k} ${v}`).join(" · ")}</div>
                {it.fit?.issues.length ? <div className="note">{it.fit.issues[0]}</div> : null}
              </div>
              <div className="right">
                <span className="price">{money(it.price, it.currency)}</span>
                <button className="buy" type="button" disabled={busy === it.id || line.item?.id === it.id} onClick={() => pick(it.id)}>
                  {line.item?.id === it.id ? "Current" : "Choose"}</button>
                <a className="small" href={buyUrl(it.id, tripId, tier, line.slot)} target="_blank" rel="sponsored noopener">Shop ↗</a>
              </div>
            </div>
          ))}
        </div>
      </aside>
    </>
  );
}
