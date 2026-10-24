import { describe, expect, it } from "vitest";
import { buildProfile, monoPath, niceMax } from "../elevation";
import { activityText, addDays, minus, nights, signed } from "../format";
import { terrainFor } from "../terrain";
import type { Stop } from "../types";

const stop = (p: Partial<Stop>): Stop => ({
  id: "x", position: 0, name: "S", country_code: null, latitude: 45, longitude: 7, elevation_m: 0,
  start_date: "2027-07-01", end_date: "2027-07-03", activities: [{ type: "city" }], notes: null, ...p,
} as Stop);

describe("format", () => {
  it("uses a real minus sign and signs margins", () => {
    expect(minus(-4)).toBe("−4");
    expect(signed(0.05)).toBe("+0.05");
    expect(signed(-0.1)).toBe("−0.10");
  });
  it("counts days inclusively", () => {
    expect(nights("2027-07-01", "2027-07-03")).toBe(3);
    expect(addDays("2027-12-31", 1)).toBe("2028-01-01");
  });
  it("describes activities", () => {
    expect(activityText({ type: "hiking", difficulty: "hard", max_altitude_m: 2600 })).toMatch(/2,?600/);
  });
});

describe("elevation profile", () => {
  const stops = [
    stop({ id: "a", position: 0, elevation_m: 1035, activities: [{ type: "hiking", difficulty: "hard", max_altitude_m: 2600 }] }),
    stop({ id: "b", position: 1, start_date: "2027-07-04", end_date: "2027-07-06", elevation_m: 20 }),
  ];
  it("rises to the highest activity point and covers every day", () => {
    const p = buildProfile(stops);
    expect(p.days).toBe(6);
    expect(p.bands).toHaveLength(2);
    expect(p.bands[0].peak.e).toBe(2600);
    expect(p.maxE).toBe(2600);
    for (let i = 1; i < p.points.length; i++) expect(p.points[i].x).toBeGreaterThan(p.points[i - 1].x);
  });
  it("draws a path and rounds axis maxima", () => {
    const p = buildProfile(stops);
    expect(monoPath(p.points, (x) => x * 10, (e) => 300 - e / 10)).toMatch(/^M/);
    expect(niceMax(2600)).toBeGreaterThanOrEqual(2600);
  });
  it("handles an empty trip", () => {
    expect(buildProfile([]).points).toEqual([]);
  });
});

describe("terrain", () => {
  it("picks a city for city stops and mountains for high hikes", () => {
    expect(terrainFor(stop({ activities: [{ type: "city" }] }))).toBe("city");
    expect(["alpine", "glacier", "snow", "hills"]).toContain(
      terrainFor(stop({ elevation_m: 1500, activities: [{ type: "hiking", difficulty: "hard", max_altitude_m: 3500 }] })));
  });
});
