import { describe, expect, it } from "vitest";
import { dayText, daysOf } from "../plandays";
import type { PlanStep } from "../types";

const cusco: PlanStep = {
  key: "pe-cusco", name: "Cusco", country: "PE", lat: -13.5, lon: -72, days: 3, sights: [],
  plan: [
    { day: 1, kind: "arrive", sights: ["Raqchi"] },
    { day: 2, kind: "day", sights: ["Qorikancha", "Sacsayhuamán"] },
    { day: 3, kind: "day", sights: ["Sacred Valley"] },
  ],
  also: ["Rainbow Mountain"],
};

describe("days of a step", () => {
  it("follows the days the traveller sets", () => {
    expect(daysOf(cusco).map((d) => d.day)).toEqual([1, 2, 3]);
    expect(daysOf({ ...cusco, days: 2 }).map((d) => d.sights)).toEqual([["Raqchi"], ["Qorikancha", "Sacsayhuamán"]]);
    const five = daysOf({ ...cusco, days: 5 });
    expect(five[3].sights).toEqual(["Rainbow Mountain"]);
    expect(five[4].kind).toBe("free");
  });
  it("cuts a trek to the days left", () => {
    const s: PlanStep = { ...cusco, days: 2, plan: [{ day: 1, kind: "arrive", sights: [] }, { day: 2, kind: "day", sights: ["Inca Trail"], days: 3 }] };
    expect(daysOf(s)[1].days).toBe(1);
  });
  it("reads as a line", () => {
    expect(dayText({ day: 2, kind: "day", sights: ["A", "B"] }, false)).toBe("A · B");
    expect(dayText({ day: 1, kind: "arrive", sights: ["Raqchi"] }, false)).toContain("Raqchi");
    expect(dayText({ day: 3, kind: "more", sights: [], of: "Inca Trail" }, false)).toContain("Inca Trail");
  });
});

describe("days from a guide written by hand", () => {
  const t = (id: string, name: string) => ({ id, name, hours: "", book: "", need: "any" as const, steps: [{ at: "08:00", what: "Start", note: "" }], extras: [] });
  const s: PlanStep = {
    key: "pe-cusco", name: "Cusco", country: "PE", lat: -13.5, lon: -72, days: 2, sights: [],
    plan: [
      { day: 1, kind: "arrive", sights: ["Plaza de Armas, Cusco"], items: [t("first", "A slow first afternoon")] },
      { day: 2, kind: "day", sights: ["Qorikancha"], items: [t("centre", "Cusco on foot")] },
    ],
    also: ["Rainbow Mountain (Vinicunca)"], more_things: [t("rainbow", "Rainbow Mountain (Vinicunca)")],
  };
  it("names the things, not the places", () => {
    expect(dayText(s.plan![1], false)).toBe("Cusco on foot");
    expect(dayText(s.plan![0], false)).toBe("Arrive · then A slow first afternoon");
  });
  it("a day added takes the next thing, with its hours", () => {
    const three = daysOf({ ...s, days: 3 });
    expect(three[2].items?.[0].id).toBe("rainbow");
    expect(three[2].items?.[0].steps.length).toBe(1);
  });
});
