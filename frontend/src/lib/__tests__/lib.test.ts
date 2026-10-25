import { describe, expect, it } from "vitest";
import { friendlyError } from "../api";
import { buildProfile, monoPath, niceMax } from "../elevation";
import { activityText, addDays, minus, monthRange, nights, signed } from "../format";
import { layOut, redate, spread } from "../spread";
import { terrainFor } from "../terrain";
import type { Stop } from "../types";

const stop = (p: Partial<Stop>): Stop => ({
  id: "x", position: 0, name: "S", country_code: null, latitude: 45, longitude: 7, elevation_m: 0,
  start_date: "2027-07-01", end_date: "2027-07-03", activities: [{ type: "city" }], notes: null, ...p,
} as Stop);

describe("format", () => {
  it("names a season across the new year", () => {
    expect(monthRange([11, 12, 1, 2, 3])).toBe("Nov–Mar");
    expect(monthRange([7])).toBe("Jul");
    expect(monthRange([])).toBe("");
  });
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


describe("friendlyError", () => {
  it("explains the trip description limit", () => {
    expect(friendlyError({ type: "string_too_long", loc: ["body", "text"], msg: "String should have at most 50000 characters", ctx: { max_length: 50000 } }))
      .toBe("Your trip description is too long: the limit is 50,000 characters.");
  });
  it("falls back to the raw message", () => {
    expect(friendlyError({ type: "x", loc: ["body", "email"], msg: "Not an email" })).toBe("email: not an email.");
  });
});

describe("spreading days over places", () => {
  it("matches the API rule", () => {
    expect(spread([null, null, null, null], null)).toEqual([2, 2, 2, 2]);
    expect(spread([null, null, null, null], 14)).toEqual([4, 4, 3, 3]);
    expect(spread([null, 4, null], 10)).toEqual([3, 4, 3]);
    expect(spread([null, null], 1)).toEqual([1, 1]);
  });
  it("lays stops back to back and moves visits with them", () => {
    const stops = [
      { start_date: "2027-05-01", end_date: "2027-05-02", days_estimated: true, visits: [] },
      { start_date: "2027-05-03", end_date: "2027-05-05", days_estimated: false, visits: [{ date: "2027-05-04" }] },
      { start_date: "2027-05-06", end_date: "2027-05-07", days_estimated: true, visits: [] },
    ];
    const moved = redate(stops, { start: "2027-06-10" });
    expect(moved.map((s) => s.start_date)).toEqual(["2027-06-10", "2027-06-12", "2027-06-15"]);
    expect(moved[1].visits[0].date).toBe("2027-06-13");
    const longer = redate(moved, { total: 11 });
    expect(longer.map((s) => [s.start_date, s.end_date])).toEqual([
      ["2027-06-10", "2027-06-13"], ["2027-06-14", "2027-06-16"], ["2027-06-17", "2027-06-20"]]);
    expect(longer[1].visits[0].date).toBe("2027-06-15");
    expect(layOut([1], "2027-12-31")).toEqual([["2027-12-31", "2027-12-31"]]);
  });
});
