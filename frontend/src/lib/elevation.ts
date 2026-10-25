import { daysBetween, nights } from "./format";
import type { Stop } from "./types";

export interface ProfilePoint { x: number; e: number }
export interface Band { x0: number; x1: number; index: number; name: string; peak: ProfilePoint; d0: number; d1: number }

/** Day-indexed elevation profile: each stop sits at its town elevation and rises to the
 *  highest point of its activities in the middle of the stay. */
export function buildProfile(stops: Stop[]): { points: ProfilePoint[]; bands: Band[]; days: number; maxE: number } {
  const sorted = [...stops].sort((a, b) => a.position - b.position);
  if (!sorted.length) return { points: [], bands: [], days: 0, maxE: 0 };
  const t0 = sorted.reduce((m, s) => (s.start_date < m ? s.start_date : m), sorted[0].start_date);
  const points: ProfilePoint[] = [];
  const bands: Band[] = [];
  let cursor = 0;
  sorted.forEach((s, i) => {
    const len = nights(s.start_date, s.end_date);
    const x0 = Math.max(cursor, daysBetween(t0, s.start_date));
    const x1 = x0 + len;
    const base = s.elevation_m || 0;
    const top = Math.max(base, ...s.activities.map((a) => a.max_altitude_m || 0));
    const mid = x0 + len / 2;
    points.push({ x: x0, e: base });
    if (top > base + 30) {
      points.push({ x: x0 + len * 0.3, e: base + (top - base) * 0.55 });
      points.push({ x: mid, e: top });
      points.push({ x: x0 + len * 0.7, e: base + (top - base) * 0.5 });
    } else {
      points.push({ x: mid, e: base });
    }
    points.push({ x: x1 - 0.001, e: base });
    bands.push({ x0, x1, index: i, name: s.name, peak: { x: mid, e: top }, d0: x0 + 1, d1: x1 });
    cursor = x1;
  });
  // keep x strictly increasing for the spline
  const clean: ProfilePoint[] = [];
  points.forEach((p) => {
    if (!clean.length || p.x > clean[clean.length - 1].x + 1e-6) clean.push(p);
  });
  const maxE = Math.max(...clean.map((p) => p.e), 100);
  return { points: clean, bands, days: cursor, maxE };
}

/** Monotone cubic (Fritsch-Carlson) path, so the line never overshoots below sea level. */
export function monoPath(pts: ProfilePoint[], X: (x: number) => number, Y: (e: number) => number): string {
  const n = pts.length;
  if (n === 0) return "";
  if (n === 1) return `M${X(pts[0].x)} ${Y(pts[0].e)}`;
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.e), d: number[] = [], m: number[] = [];
  for (let i = 0; i < n - 1; i++) d[i] = (ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]);
  m[0] = d[0];
  m[n - 1] = d[n - 2];
  for (let i = 1; i < n - 1; i++) m[i] = d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2;
  for (let i = 0; i < n - 1; i++) {
    if (d[i] === 0) { m[i] = m[i + 1] = 0; continue; }
    const a = m[i] / d[i], b = m[i + 1] / d[i], s = a * a + b * b;
    if (s > 9) { const t = 3 / Math.sqrt(s); m[i] = t * a * d[i]; m[i + 1] = t * b * d[i]; }
  }
  let p = `M${X(xs[0]).toFixed(1)} ${Y(ys[0]).toFixed(1)}`;
  for (let i = 0; i < n - 1; i++) {
    const h = xs[i + 1] - xs[i];
    p += ` C${X(xs[i] + h / 3).toFixed(1)} ${Y(ys[i] + (m[i] * h) / 3).toFixed(1)} ${X(xs[i + 1] - h / 3).toFixed(1)} ${Y(ys[i + 1] - (m[i + 1] * h) / 3).toFixed(1)} ${X(xs[i + 1]).toFixed(1)} ${Y(ys[i + 1]).toFixed(1)}`;
  }
  return p;
}

export function niceMax(v: number): number {
  const steps = [500, 1000, 1500, 2000, 3000, 4000, 5000, 6000, 7000, 9000];
  return steps.find((s) => s >= v * 1.1) ?? Math.ceil(v / 1000) * 1000;
}
