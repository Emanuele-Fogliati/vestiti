// Contour lines for the trail maps (Manu, 2026-11-14: "like the trekking sites"), made in the
// browser from the same free terrain tiles as the hill shading (Mapzen/AWS, terrarium):
// maplibre-contour turns each elevation tile into a small vector tile of contour lines.
import mlcontour from "maplibre-contour";
import type { StyleSpecification } from "maplibre-gl";
import { maplibregl } from "./maplibre";

let dem: InstanceType<typeof mlcontour.DemSource> | null = null;

function source() {
  if (!dem) {
    dem = new mlcontour.DemSource({
      url: "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
      encoding: "terrarium", maxzoom: 12, worker: true,
    });
    dem.setupMaplibre(maplibregl);
  }
  return dem;
}

/** Adds the contour lines (every 20-100 m by zoom, a bold one every 100-500 m with its height)
 *  to a style, under the trail. `ink` colours them. */
export function addContours(style: StyleSpecification, ink: string): void {
  style.sources.contours = {
    type: "vector", maxzoom: 15,
    tiles: [source().contourProtocolUrl({
      multiplier: 1, elevationKey: "ele", levelKey: "level", contourLayer: "contours",
      // [minor, major] interval in metres from each zoom
      thresholds: { 10: [100, 500], 12: [50, 250], 13: [20, 100], 15: [10, 50] },
    })],
  };
  style.layers.push(
    { id: "contour", type: "line", source: "contours", "source-layer": "contours", minzoom: 10,
      paint: { "line-color": ink, "line-opacity": ["case", ["==", ["get", "level"], 1], 0.42, 0.22],
        "line-width": ["case", ["==", ["get", "level"], 1], 1, 0.6] } },
    { id: "contour-label", type: "symbol", source: "contours", "source-layer": "contours", minzoom: 12,
      filter: [">", ["get", "level"], 0],
      layout: { "symbol-placement": "line", "text-field": ["concat", ["number-format", ["get", "ele"], {}], " m"],
        "text-font": ["Noto Sans Regular"], "text-size": 10, "text-max-angle": 30 },
      paint: { "text-color": ink, "text-opacity": 0.75, "text-halo-color": "#FFFFFF", "text-halo-width": 1.2 } },
  );
}
