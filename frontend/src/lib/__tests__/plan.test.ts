import { describe, expect, it } from "vitest";
import { dated, firstOf, move, setDays, totalDays } from "../plan";
import type { PlanStep } from "../types";

const st = (name: string, days: number, start_date: string | null = null): PlanStep =>
  ({ key: name, name, country: "AR", lat: 0, lon: 0, days, start_date, fixed_dates: !!start_date, sights: [] });

describe("plan", () => {
  it("puts the steps back to back and waits for a stop's own date", () => {
    const d = dated([st("BA", 3), st("Calafate", 2), st("Chalten", 3, "2027-01-12")], "2027-01-06");
    expect(d.map((x) => [x!.start, x!.end, x!.gap])).toEqual([
      ["2027-01-06", "2027-01-08", 0], ["2027-01-09", "2027-01-10", 0], ["2027-01-12", "2027-01-14", 1]]);
  });
  it("counts back from a later date when there is no start", () => {
    const d = dated([st("Paris", 3), st("London", 2, "2027-03-03")], null);
    expect(d[0]!.start).toBe("2027-02-28");
    expect(dated([st("Paris", 3)], null)).toEqual([null]);
  });
  it("changes days and order", () => {
    const s = setDays([st("A", 2), st("B", 2)], 1, 0);
    expect(totalDays(s)).toBe(3);
    expect(move(s, 0, 1).map((x) => x.name)).toEqual(["B", "A"]);
    expect(firstOf(1, "2026-11-12")).toBe("2027-01-01");
    expect(firstOf(12, "2026-11-12")).toBe("2026-12-01");
  });
});
