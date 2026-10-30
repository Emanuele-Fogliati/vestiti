import { describe, expect, it } from "vitest";
import type { GlobePlace } from "../worldmap";
import { insideOf, insideZoom, minZoom, placeZoom, placesGeoJSON, sceneAnchor } from "../worldmap";
import { groupPicks } from "../picks";

const place = (p: Partial<GlobePlace>): GlobePlace => ({
  id: "pe-x", name: "X", country: "PE", kind: "landmark", lat: -13, lon: -72, level: 1,
  art: null, artLabel: null, itineraries: [], parent: null, ...p,
});

describe("places appear as you zoom in", () => {
  it("shows the most visited places from space and the rare ones only up close", () => {
    expect(minZoom(6)).toBe(0);
    expect(minZoom(5)).toBeLessThan(minZoom(3));
    expect(minZoom(3)).toBeLessThan(minZoom(1));
    expect(minZoom(1)).toBeLessThanOrEqual(6);
  });

  it("brings a trip's own places forward on its map", () => {
    const fc = placesGeoJSON([place({ level: 1 }), place({ name: "Cusco", level: 1 })],
      { boost: (p) => (p.name === "Cusco" ? 99 : 0) });
    expect(fc.features[0].properties!.z).toBe(minZoom(1));
    expect(fc.features[1].properties!.z).toBe(0);
    expect(fc.features[1].geometry).toEqual({ type: "Point", coordinates: [-72, -13] });
  });

  it("marks sights apart from towns", () => {
    const [sight, town] = placesGeoJSON([place({ kind: "nature" }), place({ kind: "town" })]).features;
    expect(sight.properties!.sight).toBe(1);
    expect(town.properties!.sight).toBe(0);
  });
});

describe("places inside a city", () => {
  const florence = place({ id: "it-florence", name: "Florence", kind: "city", level: 5, art: "it-florence" });
  const uffizi = place({ id: "it-uffizi", name: "Uffizi Gallery", level: 1, parent: "it-florence" });
  const ponte = place({ id: "it-ponte", name: "Ponte Vecchio", level: 2, parent: "it-florence" });

  it("shows the city from far away and its places only once you zoom on it", () => {
    expect(placeZoom(florence)).toBe(minZoom(5));
    expect(placeZoom(uffizi)).toBeGreaterThanOrEqual(10);
    expect(placeZoom(ponte)).toBeLessThan(placeZoom(uffizi)); // the more visited first
    const [, u] = placesGeoJSON([florence, uffizi]).features;
    expect(u.properties!.z).toBe(insideZoom(1));
    expect(u.properties!.top).toBe(0);
  });

  it("lists a city's places, most visited first", () => {
    expect(insideOf([florence, uffizi, ponte]).get("it-florence")!.map((p) => p.name)).toEqual(["Ponte Vecchio", "Uffizi Gallery"]);
  });

  it("puts a picture on the sight it shows once you are close, on the city from far away", () => {
    const rome = place({ id: "it-rome", name: "Rome", kind: "city", level: 6, art: "it-colosseum" });
    const colosseum = place({ id: "it-colosseum", name: "Colosseum", level: 5, parent: "it-rome", art: "it-colosseum" });
    const byId = new Map([rome, colosseum].map((p) => [p.id, p]));
    expect(sceneAnchor([rome, colosseum], 4, byId)!.at.id).toBe("it-rome");
    expect(sceneAnchor([rome, colosseum], 12, byId)!.at.id).toBe("it-colosseum");
    // Kathmandu has no scene: from far away it shows Boudhanath's, which opens Boudhanath
    const ktm = place({ id: "np-kathmandu", name: "Kathmandu", kind: "city", level: 6 });
    const boud = place({ id: "np-boudhanath", name: "Boudhanath", level: 5, parent: "np-kathmandu", art: "np-boudhanath" });
    const far = sceneAnchor([boud], 4, new Map([ktm, boud].map((p) => [p.id, p])))!;
    expect([far.at.id, far.opens.id, far.own]).toEqual(["np-kathmandu", "np-boudhanath", false]);
  });
});

describe("picks for your own trip", () => {
  it("puts a sight under its city, keeps the order of the first pick", () => {
    const parent = (id: string) => ({ uffizi: "florence", ponte: "florence", pantheon: "rome" } as Record<string, string>)[id] ?? null;
    expect(groupPicks(["uffizi", "rome", "ponte", "florence"], parent)).toEqual([
      { id: "florence", whole: true, inside: ["uffizi", "ponte"] },
      { id: "rome", whole: true, inside: [] },
    ]);
    expect(groupPicks(["pantheon"], parent)).toEqual([{ id: "rome", whole: false, inside: ["pantheon"] }]);
  });
});
