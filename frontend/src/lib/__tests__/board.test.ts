import { describe, expect, it } from "vitest";
import { activitiesFrom, blocked, fixes, move, place, remove, resize, type Block } from "../board";

const S = "2027-01-06";
const trip: Block[] = [
  { id: "ba", name: "Buenos Aires", days: 3, status: "flex", gap: 0 },
  { id: "cal", name: "El Calafate", days: 2, status: "flex", gap: 0 },
  { id: "cha", name: "El Chaltén", days: 3, status: "flex", gap: 0 },
  { id: "tdp", name: "Torres del Paine", days: 5, status: "fixed", gap: 0, fixedNote: "refugios booked" },
];

describe("trip board", () => {
  it("lays stops back to back", () => {
    const p = place(trip, S);
    expect(p[1].start).toBe("2027-01-09");
    expect(p[3].end).toBe("2027-01-18");
  });

  it("stops a change that moves a fixed stop and offers where to take the day", () => {
    const after = resize(trip, 0, 1);
    expect(blocked(trip, after, S, false)).toMatch(/Torres del Paine is fixed/);
    const f = fixes(trip, after, S, false, 0);
    expect(f[0].label).toBe("Take the day from El Calafate");
    expect(blocked(trip, f[0].blocks, S, false)).toBeNull();
  });

  it("a booked arrival keeps its day", () => {
    const t = trip.map((b) => (b.id === "cha" ? { ...b, arrivalBooked: true } : { ...b, status: "flex" as const }));
    expect(blocked(t, resize(t, 1, -1), S, false)).toMatch(/El Chaltén/);
    expect(blocked(t, resize(t, 2, 1), S, false)).toBeNull();
  });

  it("a booked flight home keeps the end of the trip", () => {
    const t = trip.map((b) => ({ ...b, status: "flex" as const }));
    expect(blocked(t, resize(t, 3, 1), S, true)).toMatch(/flight home/);
    expect(blocked(t, resize(t, 3, 1), S, false)).toBeNull();
  });

  it("moving keeps free days in place", () => {
    const t = trip.map((b, i) => (i === 2 ? { ...b, gap: 1 } : b));
    const m = move(t, 1, 1);
    expect(m.map((b) => b.id)).toEqual(["ba", "cha", "cal", "tdp"]);
    expect(m.map((b) => b.gap)).toEqual([0, 0, 1, 0]);
  });

  it("removing before something fixed leaves the days free", () => {
    const r = remove(trip, 1, S, false);
    expect(r.map((b) => b.id)).toEqual(["ba", "cha", "tdp"]);
    expect(r[1].gap).toBe(2);
    expect(place(r, S)[2].start).toBe(place(trip, S)[3].start);
    const free = trip.map((b) => ({ ...b, status: "flex" as const }));
    expect(remove(free, 1, S, false)[1].gap).toBe(0);
  });

  it("clothes activities from the things to do", () => {
    const a = activitiesFrom([
      { type: "hiking", difficulty: "moderate", max_altitude_m: 650 },
      { type: "hiking", difficulty: "hard", max_altitude_m: 1200 },
      { type: "boat" }, null, { type: "hiking", difficulty: "easy", max_altitude_m: 300, glacier: true },
    ]);
    expect(a).toEqual([{ type: "hiking", difficulty: "hard", max_altitude_m: 1200, glacier: true }, { type: "boat" }]);
  });
});
