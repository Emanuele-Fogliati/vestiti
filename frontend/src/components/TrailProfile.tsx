import { useState } from "react";
import type { TrailPoint } from "../lib/types";

const W = 640, H = 180, L = 44, R = 12, T = 14, B = 26;

/** The trail's altitude along the way, with its key points numbered as on the map. Tap or hover
 *  to read the altitude at any kilometre. */
export default function TrailProfile({ profile, points, onFocus }: {
  profile: [number, number][]; points: TrailPoint[]; onFocus?: (i: number) => void;
}) {
  const [at, setAt] = useState<number | null>(null);
  if (profile.length < 2) return null;
  const maxKm = profile[profile.length - 1][0];
  const es = profile.map((p) => p[1]);
  const lo = Math.floor((Math.min(...es) - 30) / 100) * 100;
  const hi = Math.ceil((Math.max(...es) + 30) / 100) * 100;
  const X = (k: number) => L + (k / maxKm) * (W - L - R);
  const Y = (e: number) => T + (1 - (e - lo) / (hi - lo)) * (H - T - B);
  const path = profile.map(([k, e], i) => `${i ? "L" : "M"}${X(k).toFixed(1)},${Y(e).toFixed(1)}`).join("");
  const area = `${path}L${X(maxKm)},${H - B}L${X(0)},${H - B}Z`;
  const step = (hi - lo) > 1200 ? 500 : (hi - lo) > 500 ? 200 : 100;
  const ticks = [];
  for (let e = Math.ceil(lo / step) * step; e <= hi; e += step) ticks.push(e);
  const kmStep = maxKm > 40 ? 10 : maxKm > 15 ? 5 : maxKm > 6 ? 2 : 1;
  const kms = [];
  for (let k = 0; k <= maxKm; k += kmStep) kms.push(k);
  const near = at === null ? null : profile.reduce((a, b) => (Math.abs(b[0] - at) < Math.abs(a[0] - at) ? b : a));

  function move(e: React.PointerEvent<SVGSVGElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * W;
    setAt(Math.max(0, Math.min(maxKm, ((x - L) / (W - L - R)) * maxKm)));
  }

  return (
    <figure className="tprof">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Altitude from ${Math.round(Math.min(...es))} to ${Math.round(Math.max(...es))} m over ${maxKm.toFixed(1)} km`}
        onPointerMove={move} onPointerLeave={() => setAt(null)}>
        {ticks.map((e) => (
          <g key={e}>
            <line x1={L} x2={W - R} y1={Y(e)} y2={Y(e)} className="tp-grid" />
            <text x={L - 6} y={Y(e) + 4} textAnchor="end" className="tp-ax">{e.toLocaleString("en-US")}</text>
          </g>
        ))}
        {kms.map((k) => <text key={k} x={X(k)} y={H - 8} textAnchor="middle" className="tp-ax">{k} km</text>)}
        <path d={area} className="tp-area" />
        <path d={path} className="tp-line" />
        {points.map((p, i) => p.km == null || p.ele == null ? null : (
          <g key={p.id} className="tp-pt" onClick={() => onFocus?.(i)} role="button" aria-label={`${i + 1}: ${p.name}`}>
            <circle cx={X(p.km)} cy={Y(p.ele)} r={9} />
            <text x={X(p.km)} y={Y(p.ele) + 4} textAnchor="middle">{i + 1}</text>
          </g>
        ))}
        {near && (
          <g className="tp-at" pointerEvents="none">
            <line x1={X(near[0])} x2={X(near[0])} y1={T} y2={H - B} />
            <text x={Math.min(X(near[0]) + 6, W - 90)} y={T + 10}>{near[0].toFixed(1)} km · {Math.round(near[1]).toLocaleString("en-US")} m</text>
          </g>
        )}
      </svg>
    </figure>
  );
}
