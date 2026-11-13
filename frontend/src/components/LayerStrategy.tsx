import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { dayMonth, f2, minus, money, signed } from "../lib/format";
import type { CrossSection as CS, ModeResult, SlotStatus, Stage, Strategy, Tier, Upgrade } from "../lib/types";
import { CrossSection } from "./CrossSection";
import { ProductArt } from "./ProductArt";

const STATUS_TEXT: Record<SlotStatus, string> = {
  worn: "Worn while moving", stops: "On when you stop", pack: "In the bag, just in case", none: "Not needed",
};
// torso silhouette, long sleeves (200 x 200)
const SIL = "M72 18 Q100 34 128 18 L160 30 Q178 40 184 70 L196 176 L170 180 L156 92 L156 186 L44 186 L44 92 L30 180 L4 176 L16 70 Q22 40 40 30 Z";
const LOOK: Record<string, { fill: string; pat: "knit" | "dots" | "baffle" | "sheen" }> = {
  base_top: { fill: "var(--x-l-base)", pat: "knit" },
  mid_top: { fill: "var(--x-l-fleece)", pat: "dots" },
  insulation_top: { fill: "var(--x-l-down)", pat: "baffle" },
  shell_top: { fill: "var(--x-l-shell)", pat: "sheen" },
};
const reduced = () => typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;

function Pattern({ id, pat }: { id: string; pat: string }) {
  if (pat === "knit") return <pattern id={id} width="10" height="10" patternUnits="userSpaceOnUse"><path d="M0 5 Q2.5 0 5 5 T10 5" fill="none" stroke="var(--ink)" strokeOpacity=".18" strokeWidth="1.4" /></pattern>;
  if (pat === "dots") return <pattern id={id} width="9" height="9" patternUnits="userSpaceOnUse"><circle cx="4.5" cy="4.5" r="1.5" fill="var(--ink)" fillOpacity=".22" /></pattern>;
  if (pat === "baffle") return <pattern id={id} width="200" height="30" patternUnits="userSpaceOnUse"><path d="M0 29 H200" stroke="var(--accent)" strokeOpacity=".55" strokeWidth="2" /></pattern>;
  return (
    <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
      <stop offset=".35" stopColor="#fff" stopOpacity="0" /><stop offset=".5" stopColor="#fff" stopOpacity=".55" /><stop offset=".65" stopColor="#fff" stopOpacity="0" />
    </linearGradient>
  );
}

/** Scroll to get dressed: the worn torso layers drop onto the body one by one, base first,
 *  and the warmth meter climbs to what this stop needs. */
function DressStack({ m, title, up, applying, onApply, resetKey }: {
  m: ModeResult; title: string; up: Upgrade | null; applying: boolean; onApply: () => void; resetKey: string;
}) {
  const track = useRef<HTMLDivElement>(null);
  const [p, setP] = useState(reduced() ? 1 : 0);
  useEffect(() => {
    if (reduced()) { setP(1); return; }
    let raf = 0;
    const calc = () => {
      raf = 0;
      const el = track.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const span = Math.max(1, r.height - innerHeight * 0.8);
      setP(Math.min(1, Math.max(0, (-r.top + 60) / span)));
    };
    const on = () => { if (!raf) raf = requestAnimationFrame(calc); };
    calc();
    addEventListener("scroll", on, { passive: true });
    addEventListener("resize", on);
    return () => { removeEventListener("scroll", on); removeEventListener("resize", on); cancelAnimationFrame(raf); };
  }, [resetKey]);

  const cs: CS = m.cross_section;
  const torso = cs.layers.filter((l) => LOOK[l.slot]);
  const worn = [...torso].filter((l) => l.worn).reverse(); // base first
  const bag = torso.filter((l) => !l.worn);
  const n = Math.max(1, worn.length);
  const max = Math.max(m.required * 1.2, m.provided * 1.08, 0.6);
  let clo = 0;
  const slabs = worn.map((l, wi) => {
    const k = Math.min(1, Math.max(0, (p - wi / n) / (1 / n)));
    const e = 1 - Math.pow(1 - k, 3);
    clo += l.clo * e;
    const zRest = wi * 7, zFly = 46 + wi * 44;
    return { l, wi, e, z: zFly + (zRest - zFly) * e };
  });
  // the warmth the model counts beyond the torso layers (legs, head, hands), shown once dressed
  const torsoSum = worn.reduce((s, l) => s + l.clo, 0);
  const rest = Math.max(0, m.provided - torsoSum);
  clo += rest * Math.min(1, p * 1.2);
  const done = p > 0.97;
  const ok = m.margin >= 0;

  return (
    <div className="x-track" ref={track} style={{ height: `${120 + n * 45}vh` }}>
      <div className="x-sticky">
        <div className="x-scene">
          <div className="x-stack">
            <div className="x-slab" style={{ transform: "translateZ(-6px)" }}>
              <svg viewBox="-4 0 208 200" aria-hidden="true"><path d={SIL} fill="var(--x-l-skin)" opacity=".7" /></svg>
            </div>
            {slabs.map(({ l, wi, e, z }) => (
              <div key={l.slot} className="x-slab" style={{ transform: `translate3d(0,0,${z}px) scale(${1 + wi * 0.035})`, opacity: 0.42 + 0.58 * e }}>
                <svg viewBox="-4 0 208 200" aria-hidden="true">
                  <defs><Pattern id={`pt-${l.slot}`} pat={LOOK[l.slot].pat} /></defs>
                  <path d={SIL} fill={LOOK[l.slot].fill} stroke="var(--ink)" strokeWidth="3" strokeLinejoin="round" />
                  <path d={SIL} fill={`url(#pt-${l.slot})`} />
                </svg>
              </div>
            ))}
          </div>
        </div>
        <div className="x-gauge" aria-live="polite">
          <div className="x-k">{title}</div>
          <div className="x-clo">{f2(done ? m.provided : clo)} <small>clo</small></div>
          <div className="x-meter">
            <span className={`f${done && !ok ? " cold" : ""}`} style={{ width: `${Math.min(100, ((done ? m.provided : clo) / max) * 100)}%` }} />
            <span className="need" style={{ left: `${(m.required / max) * 100}%` }}><span>need {f2(m.required)}</span></span>
          </div>
          <div className="x-ll">
            {[...worn].reverse().map((l) => {
              const wi = worn.indexOf(l);
              const landed = p >= (wi + 0.6) / n;
              return (
                <div key={l.slot} className={`x-lr${landed ? "" : " wait"}`}>
                  <i style={{ background: LOOK[l.slot].fill }} /><span title={l.item}>{l.name}</span><span className="c">+{f2(l.clo)}</span>
                </div>
              );
            })}
            {bag.map((l) => (
              <div key={l.slot} className="x-lr bag"><i style={{ background: LOOK[l.slot].fill }} /><span>{l.name}</span><span className="c">in the bag</span></div>
            ))}
          </div>
          {done ? (
            <div className="x-verdict-row">
              <span className={`x-verdict${ok ? " ok" : ""}`}>
                {ok ? <>Warm enough · {signed(m.margin)} clo</> : m.status === "marginal" ? <>Just short · {signed(m.margin)}</> : <>Too cold · {signed(m.margin)}</>}
              </span>
              {!ok && up && (
                <button type="button" className="x-btn y" disabled={applying} onClick={onApply}>
                  {up.slot_name}: {up.item.brand} {up.item.name} · {up.extra_cost >= 0 ? "+" : "−"}{money(Math.abs(up.extra_cost))}
                </button>
              )}
            </div>
          ) : (
            <div className="x-hint"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M12 5v14M6 13l6 6 6-6" /></svg>Scroll: each layer goes on</div>
          )}
        </div>
      </div>
    </div>
  );
}

export function LayerStrategy({ tripId, strategy, tier, stageIdx, setStageIdx, onChanged }: {
  tripId: string; strategy: Strategy; tier: Tier; stageIdx: number; setStageIdx: (i: number) => void;
  onChanged: () => void;
}) {
  const { toast } = useApp();
  const [mode, setMode] = useState<"moving" | "rest">("rest");
  const [cell, setCell] = useState<{ slot: string; stage: number } | null>(null);
  const [ai, setAi] = useState<{ text: string; source: string } | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [applying, setApplying] = useState(false);

  const stages = strategy.stages;
  const st: Stage | undefined = stages[stageIdx] ?? stages[0];
  useEffect(() => { setAi(null); }, [stageIdx, cell]);
  if (!st) return null;

  const m = st.modes[mode];
  const up = st.upgrades[mode];
  const kit = strategy.kit;

  async function apply() {
    if (!up) return;
    setApplying(true);
    try {
      await api.select(tripId, { tier, slot: up.slot, choice: "product", product_id: up.item.id });
      toast(`Upgrade added to your bag: ${up.item.brand} ${up.item.name}.`);
      onChanged();
    } finally { setApplying(false); }
  }

  async function explain(slot: string, si: number) {
    setAiBusy(true);
    try {
      const sname = strategy.slots.find((s) => s.key === slot)?.name ?? slot;
      setAi(await api.explain(tripId, { topic: `Why is the ${sname} set like this at ${stages[si]?.name}?`, stage_index: si, slot, tier }));
    } catch (e) { setAi({ text: (e as Error).message, source: "error" }); } finally { setAiBusy(false); }
  }

  const cs = cell ? stages[cell.stage] : undefined;
  const cslot = cell && cs ? cs.slots[cell.slot] : undefined;
  const cname = cell ? strategy.slots.find((s) => s.key === cell.slot)?.name : undefined;
  const title = `${st.name} · ${mode === "moving" ? "moving" : "resting"} · feels ${minus(Math.round(m.condition.feels_like_c))}°`;

  return (
    <>
      <div className="x-ctrl x-rise">
        <div className="x-scroller">
          <div className="x-seg" role="tablist" aria-label="Place">
            {stages.map((s, i) => (
              <button key={s.index} type="button" role="tab" aria-selected={i === stageIdx} onClick={() => setStageIdx(i)}>{s.name}</button>
            ))}
          </div>
        </div>
        <div className="x-seg" role="group" aria-label="Activity">
          <button type="button" aria-pressed={mode === "rest"} onClick={() => setMode("rest")}>Resting</button>
          <button type="button" aria-pressed={mode === "moving"} onClick={() => setMode("moving")}>Moving</button>
        </div>
      </div>

      <DressStack m={m} title={title} up={up} applying={applying} onApply={apply} resetKey={`${stageIdx}:${mode}`} />

      <details className="x-more">
        <summary>Cross-section and day by day · {st.name}</summary>
        <div className="x-more-b">
          <p className="x-sub">{dayMonth(m.condition.date)} · {m.condition.where} · feels {minus(Math.round(m.condition.feels_like_c))} °C · wind {Math.round(m.condition.wind_kmh)} km/h · rain {m.condition.precip_mm.toFixed(1)} mm</p>
          <CrossSection cs={m.cross_section} provided={m.provided} required={m.required} />
          {m.penalties.length > 0 && <p className="x-sub">{m.penalties.join(". ")}.</p>}
          {st.exceptions.length > 0 && <ul className="x-list">{st.exceptions.map((e) => <li key={e.date}>{e.summary}</li>)}</ul>}
          {st.notes.length > 0 && <ul className="x-list">{st.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
          <p className="x-sub">{strategy.model_note}</p>
        </div>
      </details>

      <section className="x-matrix">
        <h2 className="x-h2">Where you wear what</h2>
        <div className="x-scroller">
          <table className="x-mtx">
            <thead>
              <tr>
                <th />
                {stages.map((s, i) => (
                  <th key={s.index} className={i === stageIdx ? "on" : ""}><button type="button" onClick={() => setStageIdx(i)}>{s.name}</button></th>
                ))}
              </tr>
            </thead>
            <tbody>
              {strategy.slots.map((sl) => (
                <tr key={sl.key}>
                  <td className="x-mn"><ProductArt slot={sl.key} className="x-mart" /><span>{sl.name}<small>{kit[sl.key]?.name}</small></span></td>
                  {stages.map((s, i) => {
                    const status = (s.slots[sl.key]?.status ?? "none") as SlotStatus;
                    const on = cell?.slot === sl.key && cell.stage === i;
                    return (
                      <td key={s.index} className={i === stageIdx ? "on" : ""}>
                        <button type="button" className={`x-cell ${status}`} aria-pressed={on}
                          aria-label={`${sl.name} at ${s.name}: ${STATUS_TEXT[status]}`}
                          onClick={() => setCell(on ? null : { slot: sl.key, stage: i })} />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td className="x-mn"><span>Warmth at rest</span></td>
                {stages.map((s, i) => {
                  const g = s.modes.rest.margin;
                  return <td key={s.index} className={i === stageIdx ? "on" : ""}><span className={`x-mg${g >= 0 ? "" : " cold"}`}>{signed(g)}</span></td>;
                })}
              </tr>
            </tfoot>
          </table>
        </div>
        <div className="x-legend">
          <span><i className="x-cell worn" />Worn</span>
          <span><i className="x-cell stops" />On when you stop</span>
          <span><i className="x-cell pack" />In the bag</span>
          <span><i className="x-cell none" />Not needed</span>
        </div>
        <div className="x-why" aria-live="polite">
          {cs && cslot && cname ? (
            <>
              <b>{cname} · {cs.name}: {STATUS_TEXT[cslot.status as SlotStatus].toLowerCase()}.</b> {cslot.why}
              {ai && <p className="x-ai">{ai.text}</p>}
              {!ai && <button type="button" className="x-link" disabled={aiBusy} onClick={() => explain(cell!.slot, cell!.stage)}>{aiBusy ? "Thinking…" : "Explain in plain words"}</button>}
            </>
          ) : <span>Tap a dot to see why.</span>}
        </div>
      </section>
    </>
  );
}
