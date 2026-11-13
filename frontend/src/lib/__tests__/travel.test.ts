import { describe, expect, it } from "vitest";
import { guessLeg, legText, legWeight } from "../travel";

const calafate = { lat: -50.34, lon: -72.27, country: "AR" };
const chalten = { lat: -49.33, lon: -72.89, country: "AR" };
const natales = { lat: -51.73, lon: -72.51, country: "CL" };
const ushuaia = { lat: -54.8, lon: -68.3, country: "AR" };
const bariloche = { lat: -41.13, lon: -71.31, country: "AR" };

describe("guessLeg", () => {
  it("is a flight from home", () => expect(guessLeg(null, calafate).guess).toBe("flight"));
  it("is local inside the same area", () => expect(guessLeg(calafate, { lat: -50.35, lon: -72.28 }).guess).toBe("local"));
  it("is a bus with hours for a short road", () => {
    const l = guessLeg(calafate, chalten);
    expect(l.guess).toBe("road");
    expect(l.hours).toBeGreaterThan(2);
    expect(l.hours).toBeLessThan(4);
  });
  it("adds an hour at a border", () => {
    const l = guessLeg(calafate, natales);
    expect(l.border).toBe(true);
    expect(legText(l)).toContain("border");
  });
  it("flies the long ones", () => expect(guessLeg(calafate, bariloche).guess).toBe("flight"));
  it("road or flight in between", () => expect(guessLeg(calafate, ushuaia).guess).toBe("road_or_flight"));
});

describe("legWeight", () => {
  it("a long road takes the day", () => expect(legWeight({ guess: "road", hours: 7 })).toBe("full"));
  it("a flight takes half", () => expect(legWeight({ guess: "flight", hours: null })).toBe("half"));
  it("a chosen flight on a long road takes half", () => expect(legWeight({ guess: "road_or_flight", hours: 11 }, "flight")).toBe("half"));
  it("a short bus leaves the day", () => expect(legWeight({ guess: "road", hours: 2 })).toBe("light"));
});
