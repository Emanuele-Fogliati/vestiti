import { describe, expect, it } from "vitest";
import type { GlobePlace } from "../worldmap";
import { minZoom, placesGeoJSON } from "../worldmap";

const place = (p: Partial<GlobePlace>): GlobePlace => ({
  id: "pe-x", name: "X", country: "PE", kind: "landmark", lat: -13, lon: -72, trips: 3,
  art: null, artLabel: null, itineraries: [], ...p,
});

describe("places appear as you zoom in", () => {
  it("shows the most visited places from space and the rare ones only up close", () => {
    expect(minZoom(109)).toBe(0);
    expect(minZoom(40)).toBeLessThan(minZoom(10));
    expect(minZoom(10)).toBeLessThan(minZoom(3));
    expect(minZoom(3)).toBeLessThanOrEqual(6);
  });

  it("brings a trip's own places forward on its map", () => {
    const fc = placesGeoJSON([place({ trips: 3 }), place({ name: "Cusco", trips: 3 })],
      { boost: (p) => (p.name === "Cusco" ? 99 : 0) });
    expect(fc.features[0].properties!.z).toBe(minZoom(3));
    expect(fc.features[1].properties!.z).toBe(0);
    expect(fc.features[1].geometry).toEqual({ type: "Point", coordinates: [-72, -13] });
  });

  it("marks sights apart from towns", () => {
    const [sight, town] = placesGeoJSON([place({ kind: "nature" }), place({ kind: "town" })]).features;
    expect(sight.properties!.sight).toBe(1);
    expect(town.properties!.sight).toBe(0);
  });
});
