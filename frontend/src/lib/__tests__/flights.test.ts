import { describe, expect, it } from "vitest";
import { checks, duration, pickNote, shiftDay, total, visible } from "../flights";
import type { FlightLeg, FlightOffer } from "../types";

const off = (id: string, o: string, d: string, dep: string, arr: string, price: number, stops = 0): FlightOffer => ({
  id, price, currency: "EUR", airline: "Aerolineas Argentinas", expires_at: null, passenger_ids: ["p1"],
  changeable: true, refundable: false, bags: 1,
  slices: [{ origin: o, destination: d, departs: dep, arrives: arr, minutes: 180, stops,
    segments: [{ from: o, to: d, departs: dep, arrives: arr, airline: "Aerolineas Argentinas", flight: `AR ${id}` }] }],
});
const leg = (stop: string | null, date: string): FlightLeg => ({
  stop_id: stop, from_name: "A", to_name: "B", date, guess: "flight", km: 2000, hours: null, border: false, mode: "flight",
  chosen: false, booked: false, ref: null, note: null, from_airport: null, to_airport: null, links: [],
});

describe("flights", () => {
  it("lists every flight in departure order, or direct only, or cheapest first", () => {
    const os = [off("3", "AEP", "FTE", "2026-12-03T15:00:00", "2026-12-03T18:10:00", 90),
      off("1", "AEP", "FTE", "2026-12-03T06:00:00", "2026-12-03T09:10:00", 150),
      off("2", "AEP", "FTE", "2026-12-03T07:00:00", "2026-12-03T12:10:00", 80, 1)];
    expect(visible(os, { direct: false, sort: "time" }).map((o) => o.id)).toEqual(["1", "2", "3"]);
    expect(visible(os, { direct: true, sort: "time" }).map((o) => o.id)).toEqual(["1", "3"]);
    expect(visible(os, { direct: false, sort: "price" }).map((o) => o.id)).toEqual(["2", "3", "1"]);
  });

  it("says when a pick is on another day or too close to the next flight", () => {
    const legs = [leg("s1", "2026-12-03"), leg("s2", "2026-12-08")];
    const a = off("1", "AEP", "FTE", "2026-12-04T06:00:00", "2026-12-04T09:10:00", 150);
    expect(checks(legs, [a, null])[0][0].text).toMatch(/1 day later/);
    const b = off("2", "FTE", "USH", "2026-12-03T10:00:00", "2026-12-03T11:20:00", 70);
    const c = off("3", "AEP", "FTE", "2026-12-03T06:00:00", "2026-12-03T09:10:00", 150);
    expect(checks([leg("s1", "2026-12-03"), leg("s2", "2026-12-03")], [c, b])[0].some((x) => x.level === "bad" && /separate ticket/.test(x.text))).toBe(true);
    const late = off("4", "FTE", "USH", "2026-12-03T08:00:00", "2026-12-03T09:20:00", 70);
    expect(checks([leg("s1", "2026-12-03"), leg("s2", "2026-12-03")], [c, late])[0][0].text).toMatch(/before this one lands/);
  });

  it("adds up the picks and writes one line for the board", () => {
    const a = off("1", "AEP", "FTE", "2026-12-03T23:00:00", "2026-12-04T02:10:00", 150);
    expect(total([a, null, a])).toEqual({ amount: 300, currency: "EUR", count: 2 });
    expect(pickNote(a)).toBe("AR 1 23:00 → 02:10 (+1)");
    expect(duration(195)).toBe("3 h 15");
    expect(shiftDay("2026-12-31", 1)).toBe("2027-01-01");
  });
});
