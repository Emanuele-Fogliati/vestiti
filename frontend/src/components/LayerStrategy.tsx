import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { dayMonth, f2, minus, money, signed } from "../lib/format";
import type { SlotStatus, Stage, Strategy, Tier } from "../lib/types";
import { CrossSection } from "./CrossSection";
import { ProductArt } from "./ProductArt";

const DOT: Record<SlotStatus, string> = { worn: "on", stops: "half", pack: "pack", none: "off" };
const STATUS_TEXT: Record<SlotStatus, string> = {
  worn: "Worn while moving", stops: "On at stops", pack: "In the pack, just in case", none: "Not needed",
};

export function LayerStrategy({ tripId, strategy, tier, stageIdx, setStageIdx, onChanged }: {
  tripId: string; strategy: Strategy; tier: Tier; stageIdx: number; setStageIdx: (i: number) => void;
  onChanged: () => void;
}) {
  const { toast } = useApp();
  const [mode, setMode] = useState<"moving" | "rest">("rest");
  const [cell, setCell] = useState<{ slot: string; stage: number }>({ slot: "shell_top", stage: stageIdx });
  const [ai, setAi] = useState<{ text: string; source: string } | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [applying, setApplying] = useState(false);

  const stages = strategy.stages;
  const st: Stage | undefined = stages[stageIdx] ?? stages[0];
  useEffect(() => { setCell((c) => ({ ...c, stage: stageIdx })); setAi(null); }, [stageIdx]);
  useEffect(() => {
    if (strategy.slots.length && !strategy.slots.find((s) => s.key === cell.slot)) setCell({ slot: strategy.slots[0].key, stage: stageIdx });
  }, [strategy]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!st) return null;

  const m = st.modes[mode];
  const ok = m.margin >= 0;
  const marginal = m.status === "marginal";
  const scale = Math.max(2.4, m.required + 0.4, m.provided + 0.2);
  const up = st.upgrades[mode];
  const kit = strategy.kit;
  const other = mode === "moving" ? st.modes.rest : st.modes.moving;

  async function apply() {
    if (!up) return;
    setApplying(true);
    try {
      await api.select(tripId, { tier, slot: up.slot, choice: "product", product_id: up.item.id });
      toast(`Upgrade applied to the ${tier} kit: ${up.item.brand} ${up.item.name}.`);
      onChanged();
    } finally { setApplying(false); }
  }

  async function explain() {
    setAiBusy(true);
    try {
      const sname = strategy.slots.find((s) => s.key === cell.slot)?.name ?? cell.slot;
      const r = await api.explain(tripId, { topic: `Why is the ${sname} set like this at ${stages[cell.stage]?.name}?`, stage_index: cell.stage, slot: cell.slot, tier });
      setAi(r);
    } catch (e) { setAi({ text: (e as Error).message, source: "error" }); } finally { setAiBusy(false); }
  }

  const cs = stages[cell.stage];
  const cslot = cs?.slots[cell.slot];
  const cname = strategy.slots.find((s) => s.key === cell.slot)?.name;

  return (
    <>
      <div className="sbar">
        <div style={{ minWidth: 0 }}><div className="label" style={{ marginBottom: 6 }}>Stop</div>
          <div className="seg" role="tablist" aria-label="Stop">
            {stages.map((s, i) => (
              <button key={s.index} type="button" role="tab" aria-selected={i === stageIdx} onClick={() => setStageIdx(i)}>
                <small>{String(i + 1).padStart(2, "0")} · {s.days.length} {s.days.length > 1 ? "days" : "day"}</small><b>{s.name}</b>
              </button>
            ))}
          </div>
        </div>
        <div><div className="label" style={{ marginBottom: 6 }}>Activity</div>
          <div className="seg" role="group" aria-label="Activity">
            <button type="button" aria-pressed={mode === "moving"} onClick={() => setMode("moving")}>Moving</button>
            <button type="button" aria-pressed={mode === "rest"} onClick={() => setMode("rest")}>At rest</button>
          </div>
        </div>
      </div>

      <div className="strat">
        <div className="panel">
          <div className="xhead">
            <span>TORSO CROSS-SECTION</span>
            <span><b>{dayMonth(m.condition.date)}</b> · {m.condition.where}</span>
            <span>feels <b>{minus(Math.round(m.condition.feels_like_c))} °C</b></span>
            <span>wind <b>{m.condition.wind_kmh} km/h</b></span>
            <span>rain <b>{m.condition.precip_mm.toFixed(1)} mm</b></span>
          </div>
          <CrossSection cs={m.cross_section} provided={m.provided} required={m.required} />
        </div>
        <div>
          <div className="panel" aria-live="polite">
            <div className="gtop">
              <div>
                <div className="label">Warmth check · {st.name} · {mode === "moving" ? "moving" : "at rest"}</div>
                <div className="gval">{f2(m.provided)} <small>/ {f2(m.required)} clo needed</small></div>
              </div>
              <span className={`pill ${ok ? "ok" : "cold"}`}>{ok ? `COVERED ${signed(m.margin)}` : marginal ? `MARGINAL ${signed(m.margin)}` : `TOO COLD ${signed(m.margin)}`}</span>
            </div>
            <div className={`gbar${ok ? "" : " cold"}`}>
              <span className="f" style={{ width: `${Math.min(100, (m.provided / scale) * 100)}%` }} />
              <span className="req" style={{ left: `${(m.required / scale) * 100}%` }}><span>needed {f2(m.required)}</span></span>
            </div>
            <p className="gnote">Clo is the insulation unit for clothing. Estimate from a simplified heat balance at {minus(Math.round(m.condition.feels_like_c))} °C feels-like{m.condition.altitude_m > st.elevation_m + 50 ? ` and ${m.condition.altitude_m.toLocaleString("en-US")} m` : ""}. <Link to="/how-it-works">How it works</Link></p>
            {m.penalties.length > 0 && <p className="note" style={{ marginTop: 8 }}>{m.penalties.join(". ")}.</p>}
            <div className="rec">
              {ok ? (
                <p>Covered with <b>{f2(m.margin)} clo</b> to spare. {mode === "moving" ? "Vent or take a layer off on climbs so you don't soak it with sweat." : "Nothing to change for this stop."}</p>
              ) : up ? (
                <>
                  <p>{up.closes ? "Fix:" : "Best upgrade:"} <b>{up.slot_name.toLowerCase()} → {up.item.brand} {up.item.name}</b>. {signed(up.gain_clo)} clo for {up.extra_cost >= 0 ? "+" : ""}{money(up.extra_cost)}.
                    {up.closes ? " That covers this stop." : marginal ? " Close enough for short stops; keep them under 15 minutes." : " Still short: keep stops short and add a hot drink."}</p>
                  <button type="button" className="apply" disabled={applying} onClick={apply}>Apply upgrade</button>
                </>
              ) : (
                <p>{marginal ? "Slightly short, fine for short stops (under 15 min)." : "This is already the warmest option in the catalog for these layers. Keep stops short."}</p>
              )}
            </div>
          </div>
          <div className="panel worn">
            {strategy.slots.map((s) => {
              const worn = m.worn.includes(s.key);
              const otherWorn = other.worn.includes(s.key);
              const status = st.slots[s.key]?.status ?? "none";
              const lab = worn ? (mode === "moving" ? "WORN" : "ON") : otherWorn ? (mode === "moving" ? "ON AT STOPS" : "OFF AT REST") : status !== "none" ? "IN PACK" : "NOT NEEDED";
              const cls = worn ? "" : otherWorn || status !== "none" ? "packed" : "none";
              return (
                <div className={`wrow ${cls}`} key={s.key}>
                  <div className="ph-s"><ProductArt slot={s.key} /></div>
                  <div style={{ minWidth: 0 }}>
                    <div className="nm"><span className="lc">{s.code}</span>{s.name}</div>
                    <div className="md">{kit[s.key]?.source === "owned" ? "Yours · " : kit[s.key]?.source === "rental" ? "Rental · " : ""}{kit[s.key]?.name}</div>
                  </div>
                  <div className="wr">{f2(kit[s.key]?.clo ?? 0)} clo<span className={`st2 ${worn ? "on" : cls === "packed" ? "half" : "off"}`}>{lab}</span></div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {(st.exceptions.length > 0 || st.notes.length > 0) && (
        <div className="mxwrap" style={{ marginTop: 24 }}>
          <div>
            <h3 className="subh" style={{ marginTop: 0 }}>Day-by-day exceptions · {st.name}</h3>
            {st.exceptions.length ? (
              <ul className="exc">{st.exceptions.map((e) => <li key={e.date}>{e.summary}</li>)}</ul>
            ) : <p className="muted">Every day at this stop uses the same layering.</p>}
          </div>
          <div>
            <h3 className="subh" style={{ marginTop: 0 }}>Notes</h3>
            <ul className="stagenotes">{st.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
          </div>
        </div>
      )}

      <h3 className="subh">Across the whole trip</h3>
      <p className="subp">Every piece, at every stop. Select any cell to read why. The kit shown is the {tier} budget.</p>
      <div className="mxwrap">
        <div>
          <div className="mx-box">
            <table className="mx">
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Layer · your pick</th>
                  {stages.map((s, i) => (
                    <th key={s.index} className={i === stageIdx ? "colsel" : ""} onClick={() => setStageIdx(i)} style={{ cursor: "pointer" }}>
                      {String(i + 1).padStart(2, "0")}<b>{s.name.length > 14 ? s.name.slice(0, 13) + "…" : s.name}</b>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {strategy.slots.map((sl) => (
                  <tr key={sl.key}>
                    <th><div className="mth"><div className="ph-s s"><ProductArt slot={sl.key} /></div>
                      <div>{sl.name}<small>{sl.code} · {kit[sl.key]?.name}</small></div></div></th>
                    {stages.map((s, i) => {
                      const v = s.slots[sl.key];
                      const status = (v?.status ?? "none") as SlotStatus;
                      return (
                        <td key={s.index} className={i === stageIdx ? "colsel" : ""}>
                          <button type="button" className="cell" aria-pressed={cell.slot === sl.key && cell.stage === i}
                            aria-label={`${sl.name} at ${s.name}: ${STATUS_TEXT[status]}`}
                            onClick={() => { setCell({ slot: sl.key, stage: i }); setAi(null); }}>
                            <span className={`dot ${DOT[status]}`} />
                            {v && v.days_total > 1 && status === "worn" && v.days_worn < v.days_total && (
                              <small className="mono" style={{ fontSize: 10 }}>{v.days_worn}/{v.days_total}d</small>
                            )}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
              <tfoot>
                {(["moving", "rest"] as const).map((md) => (
                  <tr key={md}>
                    <th>Warmth margin, {md === "moving" ? "moving" : "at rest"}</th>
                    {stages.map((s, i) => {
                      const g = s.modes[md].margin;
                      return <td key={s.index} className={i === stageIdx ? "colsel" : ""}><span className={`mg ${g >= 0 ? "ok" : "cold"}`}>{signed(g)}</span></td>;
                    })}
                  </tr>
                ))}
              </tfoot>
            </table>
          </div>
          <div className="mkey">
            <span><i className="dot on" />Worn while moving</span>
            <span><i className="dot half" />On at stops</span>
            <span><i className="dot pack" />In the pack, just in case</span>
            <span><i className="dot off" />Not needed</span>
          </div>
        </div>
        <aside className="why" aria-live="polite">
          {cs && cslot ? (
            <>
              <div className="why-s">{cs.name} · {cname}</div>
              <div className="why-t">{STATUS_TEXT[cslot.status as SlotStatus]}</div>
              <p className="why-b">{cslot.why}</p>
              {ai && <p className="why-b"><span className="ai-src">{ai.source === "llm" ? "AI explanation (local model)" : ai.source === "rules" ? "AI offline, rule text" : ""}</span><br />{ai.text}</p>}
              <div><button type="button" className="btn sm" disabled={aiBusy} onClick={explain}>{aiBusy ? <span className="spin" /> : "Explain in plain words"}</button></div>
              <p className="why-n">{strategy.model_note}</p>
            </>
          ) : <p>Select a cell.</p>}
        </aside>
      </div>
    </>
  );
}
