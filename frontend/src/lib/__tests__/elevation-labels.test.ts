import { describe, expect, it } from "vitest";
import { placeStopLabels } from "../../components/ElevationProfile";
import { buildProfile } from "../elevation";
import type { Stop } from "../types";

const stop = (name: string, start: string, end: string, position: number): Stop => ({
  id: name, position, name, country_code: "PE", latitude: 0, longitude: 0, elevation_m: 100,
  start_date: start, end_date: end, activities: [{ type: "city" }], notes: null,
} as Stop);

describe("stop labels under the elevation profile", () => {
  it("never lets two neighbouring labels share a row when they would overlap", () => {
    // Peru: 1-day stops between long ones, like Paracas and Huacachina
    const stops = [
      stop("Lima", "2027-05-01", "2027-05-02", 0), stop("Paracas", "2027-05-03", "2027-05-03", 1),
      stop("Huacachina", "2027-05-04", "2027-05-04", 2), stop("Arequipa", "2027-05-05", "2027-05-06", 3),
      stop("Colca Canyon (Chivay)", "2027-05-07", "2027-05-08", 4), stop("Sacred Valley (Ollantaytambo)", "2027-05-09", "2027-05-09", 5),
      stop("Aguas Calientes", "2027-05-10", "2027-05-10", 6),
    ];
    const { bands, days } = buildProfile(stops);
    const X = (x: number) => 56 + (x / days) * (1000 - 56 - 24);
    const labels = placeStopLabels(bands, X);
    const box = (i: number) => {
      const l = labels[i];
      const w = Math.max(l.text.length * l.size * 0.68, l.days.length * 11 * 0.62);
      return { x0: l.mid - w / 2, x1: l.mid + w / 2, row: l.row };
    };
    for (let i = 1; i < labels.length; i++) {
      for (let j = 0; j < i; j++) {
        const a = box(j), b = box(i);
        if (a.row === b.row) expect(a.x1, `${labels[j].text} vs ${labels[i].text}`).toBeLessThanOrEqual(b.x0 + 1);
      }
    }
    expect(labels[4].text).not.toContain("(");  // "(Chivay)" is dropped when space is short
    expect(labels.every((l) => l.full)).toBe(true);
  });
});
