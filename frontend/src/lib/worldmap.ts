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
  /** Indexes into GlobeData.itineraries: ready-made itineraries that stop here. */
  itineraries: number[];
  /** Id of the city or town this place is inside (the Uffizi is in Florence), else null.
   *  From far away only the city shows; its places appear once you zoom on it. */
  parent: string | null;
}

export interface GlobeData {
  itineraries: { slug: string; title: string }[];
  places: GlobePlace[];
}

type Row = [string, string, string, PlaceKind, number, number, number, string | null, number[], string | null];

let cache: Promise<GlobeData> | null = null;

/** All the places, fetched once per page load (one compact, gzipped response). */
export function loadPlaces(): Promise<GlobeData> {
  if (!cache) {
    cache = fetch(`/api/globe/places?v=${__BUILD_ID__}`)
      .then((r) => { if (!r.ok) throw new Error(`places: ${r.status}`); return r.json(); })
      .then((d: { itineraries: GlobeData["itineraries"]; places: Row[] }) => ({
        itineraries: d.itineraries,
        places: d.places.map(([id, name, country, kind, lat, lon, level, art, itineraries, parent]) =>
          ({ id, name, country, kind, lat, lon, level, art, itineraries, parent: parent ?? null })),
      }));
    cache.catch(() => { cache = null; });
  }
  return cache;
}

export interface RouteStop {
  /** The place on the globe (null on the routes that come from a ready-made itinerary). */
  place: string | null;
  name: string;
  country: string;
  kind: PlaceKind;
  lat: number;
  lon: number;
  elevation_m: number;
  days: number;
  /** [day of the stop, places you see that day] */
  visits: [number, string[]][];
}

export interface GlobeRoute {
  id: string;
  /** Slug of the ready-made itinerary with a day-by-day guide, when the route is one. */
  guide: string | null;
  countries: string[];
  bucket: string;
  days: number;
  title: string;
  best_months: number[];
  /** Jan..Dec: coldest night and warmest day on the route (°C), weather level 2 good /
   *  1 so-so / 0 poor, and the main reason when not good ("rainy season in Puno"). */
  months: { lo: number; hi: number; level: 0 | 1 | 2; note: string | null }[] | null;
  stops: RouteStop[];
}

export interface RouteData {
  buckets: { key: string; label: string }[];
  routes: GlobeRoute[];
}

let routeCache: Promise<RouteData> | null = null;

/** The routes you can pick on the globe, fetched once per page load. */
export function loadRoutes(): Promise<RouteData> {
  if (!routeCache) {
    routeCache = fetch("/api/globe/routes")
      .then((r) => { if (!r.ok) throw new Error(`routes: ${r.status}`); return r.json() as Promise<RouteData>; });
    routeCache.catch(() => { routeCache = null; });
  }
  return routeCache;
}

/** Distance in km between two points (haversine). */
export function km(aLat: number, aLon: number, bLat: number, bLon: number): number {
  const r = Math.PI / 180;
  const h = Math.sin(((bLat - aLat) * r) / 2) ** 2 + Math.cos(aLat * r) * Math.cos(bLat * r) * Math.sin(((bLon - aLon) * r) / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(h));
}

/** Routes that stop at a place, stop right next to it (a square in town) or visit it on a day
 *  out. Shortest first. */
export function routesThrough(place: GlobePlace, routes: GlobeRoute[]): GlobeRoute[] {
  const n = place.name.toLocaleLowerCase();
  return routes.filter((r) => r.countries.includes(place.country) && r.stops.some((s) =>
    s.place === place.id || s.name.toLocaleLowerCase() === n || km(s.lat, s.lon, place.lat, place.lon) < 15
    || s.visits.some(([, vs]) => vs.some((v) => v.toLocaleLowerCase() === n))))
    .sort((a, b) => a.days - b.days);
}

export function countriesLabel(cs: string[]): string {
  return cs.map(countryName).join(" & ");
}

/** The zoom from which a place shows: the most visited places (level 6) are visible from
 *  space, the rarest (level 1) appear when you are close. */
export function minZoom(level: number): number {
  const l = Math.min(6, Math.max(1, Math.round(level)));
  return [5.6, 4.6, 3.6, 2.6, 1.6, 0][l - 1];
}

/** The zoom from which the places inside a city show: once the city fills the screen. The
 *  most visited sights first (Qorikancha before the Twelve-Angled Stone). */
export function insideZoom(level: number): number {
  const l = Math.min(6, Math.max(1, Math.round(level)));
  return 10.5 + (6 - l) * 0.5;
}

/** The zoom from which a place shows on the map: a city by how visited it is, a place inside a
 *  city only when you are close to that city. */
export function placeZoom(p: Pick<GlobePlace, "level" | "parent">): number {
  return p.parent ? insideZoom(p.level) : minZoom(p.level);
}

/** The places inside each city, most visited first: { "it-florence": [Uffizi, ...] }. */
export function insideOf(places: GlobePlace[]): Map<string, GlobePlace[]> {
  const out = new Map<string, GlobePlace[]>();
  for (const p of places) {
    if (!p.parent) continue;
    const l = out.get(p.parent);
    if (l) l.push(p); else out.set(p.parent, [p]);
  }
  for (const l of out.values()) l.sort((a, b) => b.level - a.level);
  return out;
}

/** Where a scene's picture sits at this zoom, and which place it opens. Zoomed on a city, the
 *  picture sits on the sight it shows (the Colosseum); from far away on the city (Rome). A city
 *  with no scene of its own shows the scene of a place inside it from far away (Kathmandu shows
 *  Boudhanath), so no picture is lost; tapping it opens the place it shows. */
export function sceneAnchor(owners: GlobePlace[], zoom: number, byId: Map<string, GlobePlace>):
  { at: GlobePlace; opens: GlobePlace; own: boolean } | null {
  const child = owners.find((o) => o.parent && zoom >= insideZoom(o.level));
  if (child) return { at: child, opens: child, own: true };
  const top = owners.find((o) => !o.parent);
  if (top) return { at: top, opens: top, own: true };
  const city = owners[0]?.parent ? byId.get(owners[0].parent) : undefined;
  return city ? { at: city, opens: owners[0], own: false } : null;
}

/** Home globe ladder, by popularity (level 1..6): the zoom from which a place shows as a dot.
 *  From space only the most visited places, as pictures; every step closer, dots become pictures
 *  and empty land gets new dots, so the globe never fills up at once. */
const GLOBE_DOT = [5.6, 4.8, 4.0, 3.2, 2.5, 0];
const PICTURE_AFTER = 0.9; // a place's dot turns into its picture this much closer

const lvl = (level: number) => Math.min(6, Math.max(1, Math.round(level)));

export function globeDotZoom(p: Pick<GlobePlace, "level" | "parent">): number {
  return p.parent ? insideZoom(p.level) : GLOBE_DOT[lvl(p.level) - 1];
}

/** The zoom from which a place's picture shows on the home globe (the most visited from space). */
export function globePicZoom(p: Pick<GlobePlace, "level" | "parent">): number {
  if (p.parent) return insideZoom(p.level) + 0.6;
  return lvl(p.level) === 6 ? 0 : GLOBE_DOT[lvl(p.level) - 1] + PICTURE_AFTER;
}

export const SIGHT_KINDS: PlaceKind[] = ["landmark", "nature", "island", "region"];

export function placesGeoJSON(places: GlobePlace[],
  opts: { boost?: (p: GlobePlace) => number; zoomOf?: (p: GlobePlace) => number } = {}): FeatureCollection {
  const zoomOf = opts.zoomOf ?? placeZoom;
  return {
    type: "FeatureCollection",
    features: places.map((p, i) => ({
      type: "Feature",
      id: i,
      geometry: { type: "Point", coordinates: [p.lon, p.lat] },
      properties: {
        i, name: p.name, kind: p.kind, level: p.level, art: p.art ? 1 : 0,
        sight: SIGHT_KINDS.includes(p.kind) ? 1 : 0,
        top: p.parent ? 0 : 1, // a city's name wins over the names of the places inside it
        z: Math.max(0, zoomOf(p) - (opts.boost?.(p) ?? 0)),
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
  wood: string; water: string; road: string;
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
    wood: cssVar("--map-wood", "#CFDDB8"),
    water: cssVar("--map-water-label", "#3F78A0"),
    road: cssVar("--map-road-label", "#5E5A50"),
  };
}

const FONT = ["Noto Sans Regular"];
const FONT_BOLD = ["Noto Sans Bold"];
const FONT_ITALIC = ["Noto Sans Italic"];
const NAME: ExpressionSpecification = ["coalesce", ["get", "name:en"], ["get", "name:latin"], ["get", "name"]];

export const ATTRIBUTION =
  '<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> · ' +
  '<a href="https://www.openmaptiles.org/" target="_blank" rel="noopener">© OpenMapTiles</a> · ' +
  '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap</a> · ' +
  'Terrain: <a href="https://registry.opendata.aws/terrain-tiles/" target="_blank" rel="noopener">Mapzen/AWS</a>';
const ROAD_NAME = {
  "text-field": ["coalesce", NAME, ["get", "ref"]] as ExpressionSpecification, "text-font": FONT,
  "symbol-placement": "line" as const, "symbol-spacing": 300,
  "text-size": ["interpolate", ["linear"], ["zoom"], 10, 9.5, 16, 12] as ExpressionSpecification,
};
const SAT_ATTRIBUTION =
  'Earth from space: <a href="https://earthdata.nasa.gov/gibs" target="_blank" rel="noopener">NASA Blue Marble (GIBS)</a>';

/** The globe seen from space is the real Earth (NASA Blue Marble with relief and sea floor,
 *  public domain, no key); closer in it fades into the drawn map, which has the detail. */
const SAT_UNTIL = 6; // fully the drawn map from here
const SAT_FROM = 5; // fully the photo up to here
/** Opacity of the drawn map's fills on the globe: hidden under the photo from far away. */
const drawnIn = (full: number): ExpressionSpecification =>
  ["interpolate", ["linear"], ["zoom"], SAT_FROM, 0, SAT_UNTIL, full];

/** A light, quiet base map: sea, land, forests, ice, hill shading, borders, roads when close,
 *  a few town names. Our places go on top and are the only thing in colour. */
/** Names of the water (oceans, seas, lakes): written along the water when the tiles give a line
 *  for it, else on its middle. */
function waterNames(id: string, minzoom: number, classes: string[], layout: Record<string, unknown>,
  paint: Record<string, unknown>): StyleSpecification["layers"] {
  return (["Point", "LineString"] as const).map((g) => ({
    id: `${id}-${g === "Point" ? "pt" : "line"}`, type: "symbol" as const, source: "omt", "source-layer": "water_name", minzoom,
    filter: ["all", ["in", ["get", "class"], ["literal", classes]], ["==", ["geometry-type"], g]] as ExpressionSpecification,
    layout: { "text-field": NAME, "text-font": FONT_ITALIC, "symbol-placement": g === "Point" ? "point" : "line", ...layout },
    paint,
  })) as StyleSpecification["layers"];
}

export function baseStyle(c: MapColors, opts: { globe: boolean; photo?: boolean }): StyleSpecification {
  const sat = opts.globe && opts.photo !== false; // the Earth photo from space, or the drawn map at every zoom
  const fill = (full: number) => (sat ? drawnIn(full) : full);
  // on the photo (until the drawn map is fully in) names are white with a dark edge, after that grey with a white edge
  const onPhoto = (photo: string, map: string): ExpressionSpecification | string =>
    sat ? ["step", ["zoom"], photo, SAT_UNTIL, map] : map;
  const layers: StyleSpecification["layers"] = [
    { id: "bg", type: "background", paint: { "background-color": c.land } },
    ...(sat ? [{ id: "earth", type: "raster" as const, source: "sat",
      paint: { "raster-opacity": ["interpolate", ["linear"], ["zoom"], SAT_FROM, 1, SAT_UNTIL, 0] as ExpressionSpecification,
        "raster-saturation": 0.1, "raster-contrast": 0.05, "raster-fade-duration": 200 } }] : []),
    { id: "cover-green", type: "fill", source: "omt", "source-layer": "landcover",
      filter: ["in", ["get", "class"], ["literal", ["grass", "wetland", "farmland"]]],
      paint: { "fill-color": c.green, "fill-opacity": fill(0.8) } },
    // forests a deeper green than meadows: the land reads like land
    { id: "cover-wood", type: "fill", source: "omt", "source-layer": "landcover",
      filter: ["==", ["get", "class"], "wood"],
      paint: { "fill-color": c.wood, "fill-opacity": fill(0.85) } },
    { id: "cover-sand", type: "fill", source: "omt", "source-layer": "landcover",
      filter: ["==", ["get", "class"], "sand"], paint: { "fill-color": c.sand, "fill-opacity": fill(1) } },
    { id: "cover-ice", type: "fill", source: "omt", "source-layer": "landcover",
      filter: ["==", ["get", "class"], "ice"], paint: { "fill-color": c.ice, "fill-opacity": fill(1) } },
    { id: "park", type: "fill", source: "omt", "source-layer": "park", minzoom: 6,
      paint: { "fill-color": c.green, "fill-opacity": 0.5 } },
    { id: "hills", type: "hillshade", source: "dem",
      paint: {
        "hillshade-exaggeration": ["interpolate", ["linear"], ["zoom"], 0, sat ? 0 : 0.55, SAT_FROM, sat ? 0.2 : 0.5, 6, 0.5, 12, 0.35],
        "hillshade-shadow-color": "rgba(60,55,40,0.5)",
        "hillshade-highlight-color": "rgba(255,255,255,0.35)",
        "hillshade-accent-color": "rgba(60,55,40,0.25)",
      } },
    { id: "water", type: "fill", source: "omt", "source-layer": "water",
      filter: ["!=", ["get", "brunnel"], "tunnel"], paint: { "fill-color": c.sea, "fill-opacity": fill(1) } },
    { id: "rivers", type: "line", source: "omt", "source-layer": "waterway", minzoom: 6,
      paint: { "line-color": c.sea, "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.6, 12, 2, 16, 5] } },
    { id: "roads", type: "line", source: "omt", "source-layer": "transportation", minzoom: 6,
      filter: ["in", ["get", "class"], ["literal", ["motorway", "trunk", "primary", "secondary"]]],
      paint: { "line-color": "#FFFFFF", "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.6, 10, 1.6, 14, 4] } },
    { id: "streets", type: "line", source: "omt", "source-layer": "transportation", minzoom: 12,
      filter: ["in", ["get", "class"], ["literal", ["tertiary", "minor", "service"]]],
      paint: { "line-color": "#FFFFFF", "line-width": ["interpolate", ["linear"], ["zoom"], 12, 0.8, 16, 4] } },
    { id: "borders", type: "line", source: "omt", "source-layer": "boundary",
      filter: ["all", ["==", ["get", "admin_level"], 2], ["!=", ["get", "maritime"], 1]],
      paint: { "line-color": onPhoto("rgba(255,255,255,0.55)", c.line), "line-width": ["interpolate", ["linear"], ["zoom"], 1, 0.5, 6, 1.2] } },
    // names of the water: oceans and seas from space, lakes and bays closer, rivers along their course
    ...waterNames("sea-names", 0, ["ocean", "sea", "bay", "strait"], {
      "text-letter-spacing": 0.15, "text-max-width": 8, "text-size": ["interpolate", ["linear"], ["zoom"], 1, 10, 6, 13] },
    { "text-color": onPhoto("#DDEBF5", c.water), "text-halo-color": onPhoto("rgba(10,30,50,0.6)", c.halo), "text-halo-width": 1 }),
    ...waterNames("lake-names", 5, ["lake"], {
      "text-max-width": 7, "text-size": ["interpolate", ["linear"], ["zoom"], 5, 10.5, 12, 13] },
    { "text-color": c.water, "text-halo-color": c.halo, "text-halo-width": 1.2 }),
    { id: "river-names", type: "symbol", source: "omt", "source-layer": "waterway", minzoom: 8,
      filter: ["==", ["get", "class"], "river"],
      layout: { "text-field": NAME, "text-font": FONT_ITALIC, "text-size": 11, "symbol-placement": "line",
        "symbol-spacing": 400, "text-letter-spacing": 0.08 },
      paint: { "text-color": c.water, "text-halo-color": c.halo, "text-halo-width": 1.2 } },
    // road names: main roads when the region fills the screen, every street in town
    { id: "road-names", type: "symbol", source: "omt", "source-layer": "transportation_name", minzoom: 10,
      filter: ["in", ["get", "class"], ["literal", ["motorway", "trunk", "primary"]]],
      layout: ROAD_NAME, paint: { "text-color": c.road, "text-halo-color": c.halo, "text-halo-width": 1.4 } },
    { id: "street-names", type: "symbol", source: "omt", "source-layer": "transportation_name", minzoom: 13,
      filter: ["in", ["get", "class"], ["literal", ["secondary", "tertiary", "minor", "street", "pedestrian"]]],
      layout: ROAD_NAME, paint: { "text-color": c.road, "text-halo-color": c.halo, "text-halo-width": 1.4 } },
    { id: "country-names", type: "symbol", source: "omt", "source-layer": "place", maxzoom: 6,
      filter: ["==", ["get", "class"], "country"],
      layout: { "text-field": NAME, "text-font": FONT, "text-size": ["interpolate", ["linear"], ["zoom"], 1, 9, 5, 13],
        "text-transform": "uppercase", "text-letter-spacing": 0.12, "text-max-width": 7 },
      paint: { "text-color": onPhoto("#FFFFFF", c.label), "text-halo-color": onPhoto("rgba(20,30,20,0.7)", c.halo),
        "text-halo-width": 1.2, "text-opacity": sat ? 0.9 : 0.8 } },
    { id: "town-names", type: "symbol", source: "omt", "source-layer": "place", minzoom: 7,
      filter: ["in", ["get", "class"], ["literal", ["city", "town", "village"]]],
      layout: { "text-field": NAME, "text-font": FONT, "text-size": 11, "symbol-sort-key": ["get", "rank"] },
      paint: { "text-color": c.label, "text-halo-color": c.halo, "text-halo-width": 1.2 } },
    { id: "peaks", type: "symbol", source: "omt", "source-layer": "mountain_peak", minzoom: 11,
      layout: { "text-field": ["concat", "▲ ", NAME], "text-font": FONT, "text-size": 10 },
      paint: { "text-color": c.label, "text-halo-color": c.halo, "text-halo-width": 1 } },
  ];
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
      ...(sat ? { sat: {
        type: "raster" as const, tileSize: 256, maxzoom: 8, attribution: SAT_ATTRIBUTION,
        tiles: ["https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg"],
      } } : {}),
    },
    layers,
  };
}

/** Name of an empty image the size of a globe picture: a place showing its picture reserves that
 *  room, so no name (not even its own) is written under a picture. The map adds the image. */
export const PICTURE_ROOM = "picture-room";

/** The room the globe's pictures take, as a layer above the names: symbols on top are placed
 *  first, so the rooms are kept before any name is placed. */
export function pictureRoomLayer(source = "places"): StyleSpecification["layers"][number] {
  return { id: "pl-room", type: "symbol", source, filter: ["==", ["coalesce", ["get", "p"], 0], 1],
    layout: { "icon-image": PICTURE_ROOM, "icon-allow-overlap": true } };
}
const PIC_HIDES: ExpressionSpecification = ["case", ["==", ["coalesce", ["get", "p"], 0], 1], 0, 1];

/** Our places on top of the base map: dots sized by popularity, names that never overlap
 *  (the most visited win), each place only once you are close enough. */
export function placeLayers(c: MapColors, source = "places", opts: { photo?: boolean } = {}): StyleSpecification["layers"] {
  // on the globe's Earth-from-space photo the names are white with a dark edge
  const onPhoto = (photo: string, map: string): ExpressionSpecification | string =>
    opts.photo ? ["step", ["zoom"], photo, SAT_UNTIL, map] : map;
  const shown: ExpressionSpecification = [">=", ["zoom"], ["get", "z"]];
  return [
    { id: "pl-dot", type: "circle", source, filter: shown,
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["get", "level"], 1, 3.5, 5, 5.5, 6, 7.5],
        "circle-color": ["case", ["==", ["get", "sight"], 1], c.accent, c.ink],
        "circle-stroke-color": ["case", ["==", ["get", "sight"], 1], c.ink, c.halo],
        "circle-stroke-width": 1.6,
        // a place showing its picture (p = 1): the picture sits on the point, no dot peeking out
        "circle-opacity": PIC_HIDES,
        "circle-stroke-opacity": PIC_HIDES,
      } },
    { id: "pl-name", type: "symbol", source, filter: shown,
      layout: {
        "text-field": ["get", "name"], "text-font": FONT_BOLD,
        "text-size": ["interpolate", ["linear"], ["get", "level"], 1, 11, 6, 13.5],
        "text-variable-anchor": ["left", "right", "top", "bottom"],
        // a place showing its picture: the name goes beside the picture, not under it
        "text-radial-offset": ["case", ["==", ["get", "p"], 1], 2.4, 0.75],
        "text-justify": "auto", "text-max-width": 9, "symbol-sort-key": ["-", 0, ["+", ["get", "level"], ["*", 10, ["coalesce", ["get", "top"], 1]], ["*", 100, ["coalesce", ["get", "p"], 0]]]],
        "text-optional": true,
      },
      paint: { "text-color": onPhoto("#FFFFFF", c.ink), "text-halo-color": onPhoto("rgba(10,20,30,0.85)", c.halo), "text-halo-width": 1.6 } },
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
