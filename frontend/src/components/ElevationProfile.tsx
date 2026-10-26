import { buildProfile, monoPath, niceMax } from "../lib/elevation";
import type { Band } from "../lib/elevation";
import type { Stop } from "../lib/types";

// rough text widths in SVG units (uppercase display font, monospace numbers)
const CAPS_W = 0.68;
const MONO_W = 0.62;

/** Altitude labels centred above each peak (a peak is the top of the line there, so the
 *  line never runs through its label), lifted when two labels would touch. */
function placePeakLabels(peaks: Band[], X: (x: number) => number, Y: (e: number) => number, W: number) {
  const placed: { x0: number; x1: number; y: number }[] = [];
  return peaks.map((b) => {
    const cx = X(b.peak.x), cy = Y(b.peak.e);
    const w = `${Math.round(b.peak.e).toLocaleString("en-US")} m`.length * 12 * MONO_W;
    const tx = Math.min(Math.max(cx, 60 + w / 2), W - 4 - w / 2);
    const x0 = tx - w / 2, x1 = tx + w / 2;
    let ty = cy - 13;
    for (let guard = 0; guard < 8 && placed.some((p) => x0 < p.x1 + 6 && x1 > p.x0 - 6 && Math.abs(p.y - ty) < 14); guard++) ty -= 14;
    placed.push({ x0, x1, y: ty });
    return { b, cx, cy, tx, ty, right: false };
  });
}

/** Stop names under the profile: full size when they fit, smaller when not, and on a
 *  second row (alternating) when neighbours are too narrow to share one line. */
export function placeStopLabels(bands: Band[], X: (x: number) => number) {
  const out: { index: number; mid: number; size: number; row: number; text: string; full: string; days: string }[] = [];
  let prevRow = 1;
  bands.forEach((b) => {
    const w = X(b.x1) - X(b.x0) - 8;
    const days = b.d0 === b.d1 ? `DAY ${b.d0}` : `DAYS ${b.d0}–${b.d1}`;
    const short = b.name.replace(/\s*\(.*\)$/, "");
    let size = 15, row = 0, text = b.name;
    if (text.length * 15 * CAPS_W > w) {
      size = 11;
      text = short;
      const fitsOne = text.length * 11 * CAPS_W <= w && days.length * 11 * MONO_W <= w;
      if (!fitsOne) {
        // alternate rows so a narrow label can spill over its neighbours
        row = prevRow === 0 ? 1 : 0;
        const room = Math.max(w * 2.2, 40);
        const max = Math.max(4, Math.floor(room / (11 * CAPS_W)));
        if (text.length > max) text = text.slice(0, max - 1).trimEnd() + "…";
      }
    }
    prevRow = row;
    out.push({ index: b.index, mid: X((b.x0 + b.x1) / 2), size, row, text, full: b.name, days });
  });
  return out;
}

export function ElevationProfile({ stops, selected, onSelect }: {
  stops: Stop[]; selected: number; onSelect: (i: number) => void;
}) {
  const { points, bands, days, maxE } = buildProfile(stops);
  if (!points.length) return null;
  const top = niceMax(maxE);
  const W = 1000, L = 56, R = 24, T = 34, B = 226;
  const X = (x: number) => L + (x / Math.max(days, 1)) * (W - L - R);
  const Y = (e: number) => B - (Math.max(e, 0) / top) * (B - T);
  const line = monoPath(points, X, Y);
  const grid = [0, top / 2, top];
  const peaks = bands.filter((b) => b.peak.e > 0);
  const highest = Math.max(...bands.map((b) => b.peak.e));
  const peakLabels = placePeakLabels(peaks, X, Y, W);
  const stopLabels = placeStopLabels(bands, X);
  const ROW = 34;
  const H = stopLabels.some((l) => l.row) ? 300 + ROW : 300;
  return (
    <figure className="elev">
      <div className="elev-head">
        <span className="label">Elevation profile · {days} days</span>
        <span className="label">Metres above sea level</span>
      </div>
      <div className="elev-scroll">
        <svg viewBox={`0 0 ${W} ${H}`} role="img"
          aria-label={`Elevation across ${bands.length} stops. Highest point ${Math.round(highest)} m.`}>
          {bands.map((b) => (
            <rect key={b.index} className="eband" x={X(b.x0)} y={T - 24} width={Math.max(X(b.x1) - X(b.x0), 2)} height={B - T + 80}
              fill={b.index === selected ? "var(--el-sel)" : "transparent"} onClick={() => onSelect(b.index)}>
              <title>{b.name}</title>
            </rect>
          ))}
          {grid.map((v) => (
            <g key={v}>
              <line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} stroke="var(--rule)" strokeDasharray={v ? "3 5" : undefined} />
              <text x={L - 10} y={Y(v) + 4} textAnchor="end" fontSize="11" fill="var(--ink-2)" fontFamily="var(--f-mono)">
                {Math.round(v).toLocaleString("en-US")}
              </text>
            </g>
          ))}
          {bands.slice(1).map((b) => (
            <line key={b.index} x1={X(b.x0)} x2={X(b.x0)} y1={T - 14} y2={B} stroke="var(--rule-strong)" strokeDasharray="2 4" />
          ))}
          <path d={`${line} L${X(days)} ${Y(0)} L${X(0)} ${Y(0)}Z`} fill="var(--el-fill)" pointerEvents="none" />
          <path d={line} fill="none" stroke="var(--el-line)" strokeWidth="2.6" strokeLinejoin="round" pointerEvents="none" />
          {peakLabels.map(({ b, cx, cy, tx, ty }) => (
            <g key={b.index} pointerEvents="none">
              <circle cx={cx} cy={cy} r="6" fill="var(--el-dot)" stroke="var(--el-dot-ring)" strokeWidth="2" />
              <text x={tx} y={ty} textAnchor="middle" fontSize="12"
                fill="var(--ink)" fontFamily="var(--f-mono)">{Math.round(b.peak.e).toLocaleString("en-US")} m</text>
            </g>
          ))}
          {stopLabels.map((l) => (
            <g key={`l${l.index}`} pointerEvents="none">
              <text x={l.mid} y={B + 30 + l.row * ROW} textAnchor="middle" fontSize={l.size} fontWeight="700" fill="var(--el-label)"
                fontFamily="var(--f-display)" style={{ textTransform: "uppercase", letterSpacing: ".02em" }}>
                <title>{l.full}</title>{l.text}
              </text>
              <text x={l.mid} y={B + 46 + l.row * ROW} textAnchor="middle" fontSize="11" fill="var(--ink-2)" fontFamily="var(--f-mono)">
                {l.days}
              </text>
            </g>
          ))}
        </svg>
      </div>
      <p className="elev-hint">Tap a stop on the profile to see its layers. The line climbs to the highest point you entered for that stop's activities.</p>
    </figure>
  );
}
