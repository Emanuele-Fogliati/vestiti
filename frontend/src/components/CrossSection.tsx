import { f2, minus } from "../lib/format";
import type { CrossSection as CS } from "../lib/types";

const FILL: Record<string, string> = {
  shell_top: "var(--ly-shell)", insulation_top: "var(--ly-ins)", mid_top: "var(--ly-fleece)", base_top: "var(--ly-base)",
};
const SHORT: Record<string, string> = { shell_top: "SHELL", insulation_top: "INSULATION", mid_top: "FLEECE", base_top: "BASE" };

/** Torso cross-section: outside air at the top, skin at the bottom, one band per layer.
 *  Worn layers are filled and sized by their clo; packed layers are dashed outlines. */
export function CrossSection({ cs, provided, required }: { cs: CS; provided: number; required: number }) {
  const W = 520, X0 = 56, X1 = W - 120;
  const T = (x: number, y: number, t: string, o: { c?: string; fs?: number; a?: "end" | "start"; w?: number } = {}) => (
    <text x={x} y={y} fontFamily="var(--f-mono)" fontSize={o.fs ?? 12} fill={o.c ?? "var(--ink-2)"}
      textAnchor={o.a} fontWeight={o.w}>{t}</text>
  );
  let y = 72;
  const bands = cs.layers.map((l) => {
    const h = l.worn ? Math.round(18 + l.clo * 70) : 18;
    const b = { ...l, y, h };
    y += h;
    return b;
  });
  const skinY = y;
  const temps = new Map(cs.interfaces.map((i) => [i.slot, i.outer_temp_c]));
  const windy = cs.wind_kmh >= 30;
  const wet = cs.precip_mm >= 1;
  const wl = (X1 - X0) * 0.42;
  const by = skinY + 40;
  const ok = provided >= required;
  return (
    <svg viewBox={`0 0 ${W} ${by + 10}`} role="img" aria-label="Cross-section of the layers worn at the selected stop">
      <defs>
        <pattern id="loft" width="24" height="14" patternUnits="userSpaceOnUse">
          <path d="M0 7 Q6 1 12 7 T24 7" fill="none" stroke="var(--ly-pattern)" strokeWidth="1" />
        </pattern>
        <pattern id="pile" width="8" height="8" patternUnits="userSpaceOnUse">
          <circle cx="4" cy="4" r="1" fill="var(--ly-pattern)" />
        </pattern>
        <marker id="ah" viewBox="0 0 8 8" refX="4" refY="4" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0 0 L8 4 L0 8 Z" fill="var(--vapor)" />
        </marker>
        <marker id="aha" viewBox="0 0 8 8" refX="4" refY="4" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0 0 L8 4 L0 8 Z" fill="var(--heat)" />
        </marker>
      </defs>
      {T(X0, 18, `OUTSIDE · ${minus(Math.round(cs.outside_c))} °C FEELS-LIKE`, { c: "var(--ink)", w: 600 })}
      {windy && (
        <g stroke="var(--ink-2)" strokeWidth="1.4">
          <path d={`M${X0} 46 H${X0 + wl * 0.8}`} /><path d={`M${X0} 58 H${X0 + wl}`} />
        </g>
      )}
      {windy && T(X0, 36, `WIND ${Math.round(cs.wind_kmh)} km/h`, { fs: 10 })}
      {wet && (
        <g stroke="var(--cold)" strokeWidth="1.6" strokeLinecap="round">
          {[0, 1, 2, 3, 4].map((i) => <path key={i} d={`M${X1 - 74 + i * 15} ${36 + (i % 2) * 8} l-4 10`} />)}
        </g>
      )}
      {wet && T(X1 + 10, 44, `${cs.precip_mm.toFixed(1)} mm`, { fs: 10, c: "var(--cold)" })}
      {bands.map((b) => b.worn ? (
        <g key={b.slot}>
          <rect x={X0} y={b.y} width={X1 - X0} height={b.h} fill={FILL[b.slot]} />
          {b.slot === "insulation_top" && <rect x={X0} y={b.y} width={X1 - X0} height={b.h} fill="url(#loft)" />}
          {b.slot === "mid_top" && <rect x={X0} y={b.y} width={X1 - X0} height={b.h} fill="url(#pile)" />}
          <line x1={X0} x2={X1} y1={b.y} y2={b.y} stroke="var(--rule-strong)" strokeWidth={b.slot === "shell_top" ? 2 : 1} />
          {T(X0 + 10, b.y + 14, `${b.code} ${SHORT[b.slot]}`, { c: b.slot === "shell_top" ? "var(--ly-shell-ink)" : "var(--ink)", w: 700, fs: 11 })}
          {T(X1 + 10, b.y + 14, `${f2(b.clo)} clo`, { c: "var(--ink)", fs: 11 })}
          {temps.has(b.slot) && T(X0 - 8, b.y + 4, `${minus(Math.round(temps.get(b.slot)!))}°`, { a: "end", fs: 11, c: "var(--ink)" })}
        </g>
      ) : (
        <g key={b.slot}>
          <rect x={X0 + 0.5} y={b.y + 3} width={X1 - X0 - 1} height={b.h - 6} fill="var(--surface)" stroke="var(--rule-strong)" strokeDasharray="4 3" />
          {T(X0 + 10, b.y + 13, `${b.code} ${SHORT[b.slot]}`, { fs: 10 })}
          {T(X1 + 10, b.y + 13, "in pack", { fs: 11 })}
        </g>
      ))}
      <rect x={X0} y={skinY} width={X1 - X0} height={22} fill="var(--ly-skin)" />
      {T(X0 + 10, skinY + 15, `SKIN · ${cs.skin_c} °C`, { c: "var(--heat-text)", fs: 11, w: 600 })}
      {T(X0 - 8, skinY + 4, `${cs.skin_c}°`, { a: "end", c: "var(--heat-text)", fs: 11 })}
      <g stroke="var(--vapor)" strokeWidth="1.4" strokeDasharray="3 3" fill="none" markerEnd="url(#ah)">
        <path d={`M${X1 - 62} ${skinY + 18} V30`} /><path d={`M${X1 - 42} ${skinY + 18} V30`} />
      </g>
      <path d={`M${X0 + 200} ${skinY + 16} V${skinY - 30}`} fill="none" stroke="var(--heat)" strokeWidth="1.6" markerEnd="url(#aha)" />
      {T(X0 + 230, by, "HEAT KEPT", { c: "var(--heat-text)", fs: 10, a: "end" })}
      {T(X1 - 62, by, "VAPOUR OUT", { c: "var(--vapor-text)", fs: 10 })}
      {T(X1 + 10, skinY + 15, `Σ ${f2(provided)}`, { c: ok ? "var(--ok-text)" : "var(--warn-text)", w: 700, fs: 11 })}
    </svg>
  );
}
