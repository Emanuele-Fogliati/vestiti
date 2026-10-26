// Shared pieces of the home globe and the trip maps: the map style (free OpenFreeMap vector
// tiles + free AWS terrain tiles for the hill shading, no API key), the places we show and how
// they appear as you zoom in.
import type { FeatureCollection } from "geojson";
import type { ExpressionSpecification, StyleSpecification } from "maplibre-gl";

export type PlaceKind = "city" | "town" | "landmark" | "nature" | "island" | "region";

export interface GlobePlace {
  id: string;
  name: string;
  country: string;
  kind: PlaceKind;
  lat: number;
  lon: number;
  /** Popularity from 1 (few visit it) to 6 (the most visited). Never shown as a number:
   *  the app does not say how many trips include a place. */
  level: number;
  art: string | null;
  artLabel: string | null;
  /** Indexes into GlobeData.itineraries: ready-made itineraries that stop here. */
  itineraries: number[];
}

export interface GlobeData {
  itineraries: { slug: string; title: string }[];
  places: GlobePlace[];
}

type Row = [string, string, string, PlaceKind, number, number, number, string | null, string | null, number[]];

let cache: Promise<GlobeData> | null = null;

/** All the places, fetched once per page load (one compact, gzipped response). */
export function loadPlaces(): Promise<GlobeData> {
  if (!cache) {
    cache = fetch(`/api/globe/places?v=${__BUILD_ID__}`)
      .then((r) => { if (!r.ok) throw new Error(`places: ${r.status}`); return r.json(); })
      .then((d: { itineraries: GlobeData["itineraries"]; places: Row[] }) => ({
        itineraries: d.itineraries,
        places: d.places.map(([id, name, country, kind, lat, lon, level, art, artLabel, itineraries]) =>
          ({ id, name, country, kind, lat, lon, level, art, artLabel, itineraries })),
      }));
    cache.catch(() => { cache = null; });
  }
  return cache;
}

/** The zoom from which a place shows: the most visited places (level 6) are visible from
 *  space, the rarest (level 1) appear when you are close. */
export function minZoom(level: number): number {
  const l = Math.min(6, Math.max(1, Math.round(level)));
  return [5.6, 4.6, 3.6, 2.6, 1.6, 0][l - 1];
}

export const SIGHT_KINDS: PlaceKind[] = ["landmark", "nature", "island", "region"];

export function placesGeoJSON(places: GlobePlace[], opts: { boost?: (p: GlobePlace) => number } = {}): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: places.map((p, i) => ({
      type: "Feature",
      id: i,
      geometry: { type: "Point", coordinates: [p.lon, p.lat] },
      properties: {
        i, name: p.name, kind: p.kind, level: p.level, art: p.art ? 1 : 0,
        sight: SIGHT_KINDS.includes(p.kind) ? 1 : 0,
        z: Math.max(0, minZoom(p.level) - (opts.boost?.(p) ?? 0)),
      },
    })),
  };
}

const regionNames = typeof Intl !== "undefined" && "DisplayNames" in Intl
  ? new Intl.DisplayNames(["en"], { type: "region" }) : null;

export function countryName(cc: string): string {
  try { return regionNames?.of(cc.toUpperCase()) ?? cc; } catch { return cc; }
}

export const KIND_LABEL: Record<PlaceKind, string> = {
  city: "City", town: "Town", landmark: "Landmark", nature: "Nature", island: "Island", region: "Region",
};

function cssVar(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export interface MapColors {
  sea: string; land: string; green: string; ice: string; sand: string; line: string; label: string;
  halo: string; accent: string; ink: string; space: string; atmosphere: string;
}

/** Colours come from the theme tokens (theme/app.css, --map-*), so the maps follow the theme. */
export function mapColors(): MapColors {
  return {
    sea: cssVar("--map-sea", "#BFD7E3"),
    land: cssVar("--map-land", "#F7F4EA"),
    green: cssVar("--map-green", "#E3EBD3"),
    ice: cssVar("--map-ice", "#FFFFFF"),
    sand: cssVar("--map-sand", "#F1E8CF"),
    line: cssVar("--map-line", "#B9B6A8"),
    label: cssVar("--map-label", "#6F6D63"),
    halo: cssVar("--map-halo", "#FFFFFF"),
    accent: cssVar("--accent", "#FFD60A"),
    ink: cssVar("--ink", "#0D0D0D"),
    space: cssVar("--map-space", "#FFFFFF"),
    atmosphere: cssVar("--map-atmosphere", "#D9ECF7"),
  };
}

const FONT = ["Noto Sans Regular"];
const FONT_BOLD = ["Noto Sans Bold"];
const NAME: ExpressionSpecification = ["coalesce", ["get", "name:en"], ["get", "name:latin"], ["get", "name"]];

export const ATTRIBUTION =
  '<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> · ' +
  '<a href="https://www.openmaptiles.org/" target="_blank" rel="noopener">© OpenMapTiles</a> · ' +
  '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap</a> · ' +
  'Terrain: <a href="https://registry.opendata.aws/terrain-tiles/" target="_blank" rel="noopener">Mapzen/AWS</a>';

/** A light, quiet base map: sea, land, forests, ice, hill shading, borders, roads when close,
 *  a few town names. Our places go on top and are the only thing in colour. */
export function baseStyle(c: MapColors, opts: { globe: boolean }): StyleSpecification {
  return {
    version: 8,
    projection: { type: opts.globe ? "globe" : "mercator" },
    glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
    sky: {
      "sky-color": c.atmosphere,
      "horizon-color": c.halo,
      "fog-color": c.halo,
      "sky-horizon-blend": 0.6,
      "horizon-fog-blend": 0.6,
      "fog-ground-blend": 0.9,
      "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 5, 0.6, 8, 0],
    },
    sources: {
      omt: { type: "vector", url: "https://tiles.openfreemap.org/planet", attribution: ATTRIBUTION },
      dem: {
        type: "raster-dem", encoding: "terrarium", tileSize: 256, maxzoom: 12,
        tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
      },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": c.land } },
      { id: "cover-green", type: "fill", source: "omt", "source-layer": "landcover",
        filter: ["in", ["get", "class"], ["literal", ["wood", "grass", "wetland"]]],
        paint: { "fill-color": c.green, "fill-opacity": 0.8 } },
      { id: "cover-sand", type: "fill", source: "omt", "source-layer": "landcover",
        filter: ["==", ["get", "class"], "sand"], paint: { "fill-color": c.sand } },
      { id: "cover-ice", type: "fill", source: "omt", "source-layer": "landcover",
        filter: ["==", ["get", "class"], "ice"], paint: { "fill-color": c.ice } },
      { id: "park", type: "fill", source: "omt", "source-layer": "park", minzoom: 6,
        paint: { "fill-color": c.green, "fill-opacity": 0.5 } },
      { id: "hills", type: "hillshade", source: "dem",
        paint: {
          "hillshade-exaggeration": ["interpolate", ["linear"], ["zoom"], 0, 0.55, 6, 0.45, 12, 0.3],
          "hillshade-shadow-color": "rgba(60,55,40,0.45)",
          "hillshade-highlight-color": "rgba(255,255,255,0.35)",
          "hillshade-accent-color": "rgba(60,55,40,0.25)",
        } },
      { id: "water", type: "fill", source: "omt", "source-layer": "water",
        filter: ["!=", ["get", "brunnel"], "tunnel"], paint: { "fill-color": c.sea } },
      { id: "rivers", type: "line", source: "omt", "source-layer": "waterway", minzoom: 6,
        paint: { "line-color": c.sea, "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.6, 12, 2] } },
      { id: "roads", type: "line", source: "omt", "source-layer": "transportation", minzoom: 6,
        filter: ["in", ["get", "class"], ["literal", ["motorway", "trunk", "primary", "secondary"]]],
        paint: { "line-color": "#FFFFFF", "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.6, 10, 1.6, 14, 4] } },
      { id: "streets", type: "line", source: "omt", "source-layer": "transportation", minzoom: 12,
        filter: ["in", ["get", "class"], ["literal", ["tertiary", "minor", "service"]]],
        paint: { "line-color": "#FFFFFF", "line-width": ["interpolate", ["linear"], ["zoom"], 12, 0.8, 16, 4] } },
      { id: "borders", type: "line", source: "omt", "source-layer": "boundary",
        filter: ["all", ["==", ["get", "admin_level"], 2], ["!=", ["get", "maritime"], 1]],
        paint: { "line-color": c.line, "line-width": ["interpolate", ["linear"], ["zoom"], 1, 0.5, 6, 1.2] } },
      { id: "country-names", type: "symbol", source: "omt", "source-layer": "place", maxzoom: 6,
        filter: ["==", ["get", "class"], "country"],
        layout: { "text-field": NAME, "text-font": FONT, "text-size": ["interpolate", ["linear"], ["zoom"], 1, 9, 5, 13],
          "text-transform": "uppercase", "text-letter-spacing": 0.12, "text-max-width": 7 },
        paint: { "text-color": c.label, "text-halo-color": c.halo, "text-halo-width": 1.2, "text-opacity": 0.8 } },
      { id: "town-names", type: "symbol", source: "omt", "source-layer": "place", minzoom: 7,
        filter: ["in", ["get", "class"], ["literal", ["city", "town", "village"]]],
        layout: { "text-field": NAME, "text-font": FONT, "text-size": 11, "symbol-sort-key": ["get", "rank"] },
        paint: { "text-color": c.label, "text-halo-color": c.halo, "text-halo-width": 1.2 } },
      { id: "peaks", type: "symbol", source: "omt", "source-layer": "mountain_peak", minzoom: 11,
        layout: { "text-field": ["concat", "▲ ", NAME], "text-font": FONT, "text-size": 10 },
        paint: { "text-color": c.label, "text-halo-color": c.halo, "text-halo-width": 1 } },
    ],
  };
}

/** Our places on top of the base map: dots sized by popularity, names that never overlap
 *  (the most visited win), each place only once you are close enough. */
export function placeLayers(c: MapColors, source = "places"): StyleSpecification["layers"] {
  const shown: ExpressionSpecification = [">=", ["zoom"], ["get", "z"]];
  return [
    { id: "pl-dot", type: "circle", source, filter: shown,
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["get", "level"], 1, 3.5, 5, 5.5, 6, 7.5],
        "circle-color": ["case", ["==", ["get", "sight"], 1], c.accent, c.ink],
        "circle-stroke-color": ["case", ["==", ["get", "sight"], 1], c.ink, c.halo],
        "circle-stroke-width": 1.6,
      } },
    { id: "pl-name", type: "symbol", source, filter: shown,
      layout: {
        "text-field": ["get", "name"], "text-font": FONT_BOLD,
        "text-size": ["interpolate", ["linear"], ["get", "level"], 1, 11, 6, 13.5],
        "text-variable-anchor": ["left", "right", "top", "bottom"], "text-radial-offset": 0.75,
        "text-justify": "auto", "text-max-width": 9, "symbol-sort-key": ["-", 0, ["get", "level"]],
        "text-optional": true,
      },
      paint: { "text-color": c.ink, "text-halo-color": c.halo, "text-halo-width": 1.6 } },
  ];
}

export function reducedMotion(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** WebGL is needed for the maps; without it the page shows the rest of the content. */
export function webglOK(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}
