import { buildProfile, monoPath, niceMax } from "../lib/elevation";
import type { Stop } from "../lib/types";

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
  return (
    <figure className="elev">
      <div className="elev-head">
        <span className="label">Elevation profile · {days} days</span>
        <span className="label">Metres above sea level</span>
      </div>
      <div className="elev-scroll">
        <svg viewBox={`0 0 ${W} 300`} role="img"
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
          {peaks.map((b, i) => {
            const cx = X(b.peak.x), cy = Y(b.peak.e), right = cx < W * 0.6;
            return (
              <g key={b.index} pointerEvents="none">
                <circle cx={cx} cy={cy} r="6" fill="var(--el-dot)" stroke="var(--el-dot-ring)" strokeWidth="2" />
                <text x={right ? cx + 12 : cx - 12} y={cy - 8 - (i % 2) * 12} textAnchor={right ? "start" : "end"} fontSize="12"
                  fill="var(--ink)" fontFamily="var(--f-mono)">{Math.round(b.peak.e).toLocaleString("en-US")} m</text>
              </g>
            );
          })}
          {bands.map((b) => {
            const mid = X((b.x0 + b.x1) / 2);
            const narrow = X(b.x1) - X(b.x0) < 90;
            return (
              <g key={`l${b.index}`} pointerEvents="none">
                <text x={mid} y={B + 30} textAnchor="middle" fontSize={narrow ? 11 : 15} fontWeight="700" fill="var(--el-label)"
                  fontFamily="var(--f-display)" style={{ textTransform: "uppercase", letterSpacing: ".02em" }}>
                  {narrow && b.name.length > 10 ? b.name.slice(0, 9) + "…" : b.name}
                </text>
                <text x={mid} y={B + 48} textAnchor="middle" fontSize="11" fill="var(--ink-2)" fontFamily="var(--f-mono)">
                  {b.d0 === b.d1 ? `DAY ${b.d0}` : `DAYS ${b.d0}–${b.d1}`}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <p className="elev-hint">Tap a stop on the profile to see its layers. The line climbs to the highest point you entered for that stop's activities.</p>
    </figure>
  );
}
