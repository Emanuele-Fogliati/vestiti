import { artPin } from "../lib/artpin";
import { maplibregl } from "../lib/maplibre";
import { api } from "../lib/api";
import { useEffect, useMemo, useRef, useState } from "react";
import { PlaceCard } from "./PlaceCard";
import type { GlobeData, GlobePlace } from "../lib/worldmap";
import type { StopArt } from "../lib/types";
import { baseStyle, blockPins, loadPlaces, mapColors, phoneGestures, placeLayers, placesGeoJSON, reducedMotion, worldZoom } from "../lib/worldmap";

export interface RouteStop {
  name: string;
  latitude: number;
  longitude: number;
  country_code?: string | null;
  visits?: { name: string }[];
  art?: StopArt | null;
}

const norm = (s: string) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

/** The trip on a map: the route from stop to stop, numbered. Tap a stop (on the map or in the
 *  row above it) to zoom in, and the places worth seeing around it appear. */
export interface RouteMapOpts {
  /** the map alone, filling its box: no stop chips, no note (the map-first trip page) */
  bare?: boolean;
  /** room the floating panels take over the map, in px */
  inset?: { top: number; right: number; bottom: number; left: number };
  /** a stop's pin was tapped (its index in the trip) */
  onPin?: (i: number) => void;
  /** a small tag over each stop's pin: "4–12°" */
  tags?: (string | null)[];
  /** a place dot was tapped: offered to the page instead of the map's own card */
  onPlace?: (p: GlobePlace) => void;
  /** one day's walk ([lon, lat] points), drawn over the route and zoomed to (a recommended trip's day) */
  walk?: [number, number][] | null;
}

export default function RouteMap({ stops, focusIndex, bare, inset, onPin, tags, onPlace, walk }: { stops: RouteStop[]; focusIndex?: number | null } & RouteMapOpts) {
  const opts = useRef({ inset, onPin, onPlace, walk });
  opts.current = { inset, onPin, onPlace, walk };
  const pinEls = useRef<HTMLButtonElement[]>([]);
  const [, setReady] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [data, setData] = useState<GlobeData | null>(null);
  const [sel, setSel] = useState<GlobePlace | null>(null);
  const [focus, setFocus] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  // where the camera was when the map was last rebuilt (a stop added): start from there, not the globe
  const cam = useRef<{ center: maplibregl.LngLat; zoom: number } | null>(null);

  // only stops we can place on the map, each with its number in the trip
  const pts = useMemo(() => stops.map((s, i) => ({ ...s, n: i + 1 }))
    .filter((s) => Number.isFinite(s.latitude) && Number.isFinite(s.longitude) && !(s.latitude === 0 && s.longitude === 0)), [stops]);
  const key = pts.map((s) => `${s.latitude.toFixed(3)},${s.longitude.toFixed(3)}`).join("|");

  useEffect(() => { loadPlaces().then(setData).catch(() => setData({ itineraries: [], places: [] })); }, []);

  useEffect(() => {
    const el = box.current;
    if (!el || !data) return; // no stops yet (a new trip): the whole world, to add the first one
    const c = mapColors();
    const countries = new Set(pts.map((s) => s.country_code?.toUpperCase()).filter(Boolean) as string[]);
    const onTrip = new Set(pts.flatMap((s) => [s.name, ...(s.visits ?? []).map((v) => v.name)]).map(norm));
    // places of this trip always show; the rest of its countries show sooner than on the globe
    const boost = (p: GlobePlace) => (onTrip.has(norm(p.name)) && (!countries.size || countries.has(p.country)) ? 99
      : countries.has(p.country) ? 2 : 0);

    let map: maplibregl.Map;
    try {
      // the same globe as Explore (Manu 2026-11-16: "il mappamondo che si possa zoomare"): it opens
      // on the whole Earth turned towards the trip, then comes down onto the route and turns flat
      const mid = centre(pts);
      map = new maplibregl.Map({
        container: el,
        style: baseStyle(c, { globe: true, photo: false }),
        center: cam.current?.center ?? mid,
        zoom: cam.current?.zoom ?? worldZoom(el, opts.current.inset),
        renderWorldCopies: false, minZoom: Math.max(0, worldZoom(el) - 1), // never smaller than the globe
        maxZoom: 16,
        cooperativeGestures: phoneGestures(),
        attributionControl: { compact: true },
        pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
        fadeDuration: 150,
      });
      // the empty globe sits in the free part of the map, beside the panels
      const r = room(el, opts.current.inset);
      if (!pts.length && typeof r !== "number") map.setPadding(r);
    } catch {
      setFailed(true);
      return;
    }
    mapRef.current = map;
    if (new URLSearchParams(location.search).has("mapdebug")) (window as unknown as { __map: unknown }).__map = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const markers: maplibregl.Marker[] = [];
    pinEls.current = [];
    map.on("load", () => {
      if (el.clientWidth < 600 || bare) el.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      const straight: LineFeature[] = [{ type: "Feature", properties: { air: 0 }, geometry: { type: "LineString", coordinates: pts.map((s) => [s.longitude, s.latitude]) } }];
      map.addSource("route", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "route-casing", type: "line", source: "route", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": c.halo, "line-width": 6 } });
      map.addLayer({ id: "route", type: "line", source: "route", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": c.ink, "line-width": 2.5, "line-dasharray": [2, 1.6] } });
      // then the real way (Manu, 2026-11-14): along the roads like Google Maps, flights as arcs
      if (pts.length > 1 && pts.length <= 40) {
        // a road the router could not give now comes back as a plain line: ask again, twice
        const ask = (n: number) => api.roads(pts.map((s) => [s.latitude, s.longitude])).then(({ legs }) => {
          if (!map.getSource("route")) return;
          if (n < 2 && legs.some((l) => l.mode === "line")) setTimeout(() => { if (map.getSource("route")) ask(n + 1).catch(() => undefined); }, 3000 * (n + 1));
          const feats = legs.map((l) => ({ type: "Feature" as const, properties: { air: l.mode === "road" ? 0 : 1 },
            geometry: { type: "LineString" as const, coordinates: l.line } }));
          drawIn(map.getSource("route") as maplibregl.GeoJSONSource, feats);
          map.setPaintProperty("route", "line-dasharray", ["case", ["==", ["get", "air"], 1], ["literal", [2, 1.6]], ["literal", [1, 0]]]);
          map.setPaintProperty("route", "line-width", ["case", ["==", ["get", "air"], 1], 2, 3.2]);
        });
        ask(0).catch(() => { if (map.getSource("route")) drawIn(map.getSource("route") as maplibregl.GeoJSONSource, straight); }); // straight lines then
      } else drawIn(map.getSource("route") as maplibregl.GeoJSONSource, straight);
      map.addSource("places", { type: "geojson", data: placesGeoJSON(data.places, { boost }) });
      for (const l of placeLayers(c)) map.addLayer(l);
      // the day's walk, over the places: the trail's own line, as on the Walks page
      map.addSource("walk", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "walk-casing", type: "line", source: "walk", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#FFFFFF", "line-width": 7 } });
      map.addLayer({ id: "walk-line", type: "line", source: "walk", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#D2452B", "line-width": 3.5 } });
      if (opts.current.walk) showWalk(opts.current.walk);
      // a stop's own name sits further out, beside its pin and not under it
      const atStop = new Set(pts.map((s) => norm(s.name)));
      const stopNames = [...new Set(data.places.filter((p) => atStop.has(norm(p.name))).map((p) => p.name))];
      map.setLayoutProperty("pl-name", "text-radial-offset", ["case", ["in", ["get", "name"], ["literal", stopNames]], 1.6,
        ["==", ["get", "p"], 1], 2.4, 0.75]);
      blockPins(map, pts.map((s) => [s.longitude, s.latitude]));
      // stops on top: numbered pins, same order as the list below
      const seen = new Map<string, HTMLButtonElement>();
      pts.forEach((s, i) => {
        const at = `${s.latitude.toFixed(3)},${s.longitude.toFixed(3)}`;
        const twin = seen.get(at);
        if (twin) { // back at the same place
          const k = twin.querySelector("b") ?? twin;
          k.textContent = `${k.textContent}·${s.n}`;
          return;
        }
        // the stop's own drawing when it has one, else the plain numbered pin
        const b = artPin(s.art, s.n, s.name) ?? document.createElement("button");
        if (!b.classList.contains("apin")) {
          b.type = "button";
          b.className = "rpin";
          b.textContent = String(s.n);
          b.title = s.name;
          b.setAttribute("aria-label", `Stop ${s.n}: ${s.name}`);
        }
        b.style.setProperty("--d", `${300 + i * 160}ms`); // pins pop up in order while the line reaches them
        b.dataset.i = String(i);
        b.addEventListener("click", (e) => { e.stopPropagation(); if (opts.current.onPin) opts.current.onPin(s.n - 1); else zoomStop(i); });
        pinEls.current[i] = b;
        seen.set(at, b);
        markers.push(new maplibregl.Marker({ element: b }).setLngLat([s.longitude, s.latitude]).addTo(map));
      });
      setReady((n) => n + 1); // the pins exist now: give them their tags
      // down from the globe onto the route (at once when it is only a stop more on the same map)
      // (the whole route first, even when the page opens with a stop picked)
      if (pts.length) map.setPadding(NONE).fitBounds(bounds(pts), { padding: room(el, opts.current.inset), maxZoom: 9,
        duration: reducedMotion() ? 0 : cam.current ? 700 : 1800, essential: true });
    });

    const layers = ["pl-dot", "pl-name"];
    map.on("click", (e) => {
      const f = map.queryRenderedFeatures([[e.point.x - 8, e.point.y - 8], [e.point.x + 8, e.point.y + 8]], { layers }).at(0);
      let p = f ? data.places[f.properties.i as number] : null;
      // a tap beside the dots, where the trip can take a stop: the nearest place there (Manu
      // 2026-11-16: "voglio poter cliccare anche sulla mappa e aggiungere delle fermate")
      if (!p && opts.current.onPlace) p = nearest(map, data.places, e.point);
      if (p && opts.current.onPlace) { opts.current.onPlace(p); return; }
      setSel(p);
    });
    for (const l of layers) {
      map.on("mouseenter", l, () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", l, () => { map.getCanvas().style.cursor = ""; });
    }
    map.on("moveend", () => declutter(pinEls.current));
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);

    return () => {
      ro.disconnect();
      cam.current = { center: map.getCenter(), zoom: map.getZoom() };
      for (const m of markers) m.remove();
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, key]);

  // the trip page's timeline drives the map: a stop opened there flies the map to it
  useEffect(() => {
    if (focusIndex === undefined || !mapRef.current) return;
    const i = focusIndex === null ? -1 : pts.findIndex((p) => p.n === focusIndex + 1);
    if (i < 0) whole(); else zoomStop(i);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusIndex]);

  // a day with a walk: its line on the map, zoomed to; without, back to the stop
  const walkKey = walk && walk.length > 1 ? `${walk.length}:${walk[0].join(",")}` : "";
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getSource("walk")) return;
    if (walk && walk.length > 1) showWalk(walk);
    else {
      (map.getSource("walk") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: [] });
      const i = focusIndex == null ? -1 : pts.findIndex((p) => p.n === focusIndex + 1);
      if (i >= 0) zoomStop(i);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [walkKey]);

  function showWalk(line: [number, number][]) {
    const map = mapRef.current;
    const src = map?.getSource("walk") as maplibregl.GeoJSONSource | undefined;
    if (!map || !src || !box.current) return;
    src.setData({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: line } });
    const lons = line.map((c) => c[0]), lats = line.map((c) => c[1]);
    // the padding of the last flight to a stop stays on the camera and would add to this one
    map.setPadding({ top: 0, right: 0, bottom: 0, left: 0 });
    map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: room(box.current, opts.current.inset), maxZoom: 14, duration: 900 });
  }

  function zoomStop(i: number) {
    const s = pts[i];
    setFocus(i);
    setSel(null);
    const r = room(box.current!, opts.current.inset);
    mapRef.current?.flyTo({ center: [s.longitude, s.latitude], zoom: bare ? 7.5 : 10.5, speed: 1.3, essential: true,
      padding: typeof r === "number" ? undefined : r });
  }

  function whole() {
    const map = mapRef.current;
    if (!map || !box.current) return;
    setFocus(null);
    setSel(null);
    const r = room(box.current, opts.current.inset);
    // no stops yet: the whole globe, to pick the first one
    if (!pts.length) { map.easeTo({ zoom: worldZoom(box.current, opts.current.inset), padding: typeof r === "number" ? undefined : r, duration: 600 }); return; }
    map.setPadding(NONE).fitBounds(bounds(pts), { padding: r, maxZoom: 9 }); // fitBounds adds the map's own padding
  }

  // the weather over each pin, and which pin is open
  useEffect(() => {
    pinEls.current.forEach((b, i) => {
      if (!b) return;
      b.classList.toggle("on", focusIndex != null && pts[i]?.n === focusIndex + 1);
      let t = b.querySelector<HTMLElement>(".rpin-tag");
      const v = tags?.[pts[i]?.n - 1] ?? null;
      if (!v) { t?.remove(); return; }
      if (!t) { t = document.createElement("span"); t.className = "rpin-tag"; b.appendChild(t); }
      t.textContent = v;
    });
    // again once the pins have popped up (they grow from nothing, in order)
    const t = [60, 1800].map((ms) => setTimeout(() => declutter(pinEls.current), ms));
    return () => t.forEach(clearTimeout);
  });

  // the panels moved (a card opened): keep the whole route in the free part of the map
  const insetKey = inset ? `${inset.top},${inset.right},${inset.bottom},${inset.left}` : "";
  useEffect(() => {
    if (!insetKey || !mapRef.current || focusIndex != null) return;
    whole();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [insetKey]);

  if (failed || (pts.length === 0 && !bare)) return null;

  if (bare) return <div className="rmap rmap-bare"><div className="rmap-map" ref={box} /></div>;

  return (
    <div className="rmap">
      <div className="rmap-stops" role="group" aria-label="Zoom to a stop">
        <button type="button" className={`chip-btn${focus === null ? " on" : ""}`} onClick={whole}>Whole route</button>
        {pts.map((s, i) => (
          <button type="button" key={i} className={`chip-btn${focus === i ? " on" : ""}`} onClick={() => zoomStop(i)}>
            <b>{s.n}</b> {s.name}
          </button>
        ))}
      </div>
      <div className="rmap-box">
        <div className="rmap-map" ref={box} />
        {sel && data && (
          <div className="rmap-card">
            <PlaceCard place={sel} onClose={() => setSel(null)}
              onZoom={() => mapRef.current?.flyTo({ center: [sel.lon, sel.lat], zoom: 12, speed: 1.3 })} />
          </div>
        )}
      </div>
      <p className="small muted">Tap a stop to zoom in: the places worth seeing around it appear on the map.</p>
    </div>
  );
}

/** The place of the globe nearest to a tap, within a thumb's width (48 px), else null. */
function nearest(map: maplibregl.Map, places: GlobePlace[], at: { x: number; y: number }): GlobePlace | null {
  let best: GlobePlace | null = null, d2 = 48 * 48;
  const b = map.getBounds();
  for (const p of places) {
    if (!b.contains([p.lon, p.lat])) continue;
    const q = map.project([p.lon, p.lat]);
    const d = (q.x - at.x) ** 2 + (q.y - at.y) ** 2;
    if (d < d2 || (d === d2 && best && p.level > best.level)) { d2 = d; best = p; }
  }
  return best;
}

/** The middle of the trip, to turn the globe towards it (the Atlantic when there is no stop yet). */
function centre(pts: RouteStop[]): [number, number] {
  if (!pts.length) return [10, 20];
  const lons = pts.map((s) => s.longitude), lats = pts.map((s) => s.latitude);
  return [(Math.min(...lons) + Math.max(...lons)) / 2, (Math.min(...lats) + Math.max(...lats)) / 2];
}

function bounds(pts: RouteStop[]): maplibregl.LngLatBoundsLike {
  if (!pts.length) return [[-150, -45], [160, 65]];
  const lons = pts.map((s) => s.longitude), lats = pts.map((s) => s.latitude);
  const [w, e, s, n] = [Math.min(...lons), Math.max(...lons), Math.min(...lats), Math.max(...lats)];
  // one stop only: show its surroundings, not a single point at max zoom
  const padDeg = w === e && s === n ? 0.6 : 0;
  return [[w - padDeg, s - padDeg], [e + padDeg, n + padDeg]];
}

const NONE = { top: 0, right: 0, bottom: 0, left: 0 };

function pad(el: HTMLElement): number {
  return Math.round(Math.min(56, Math.min(el.clientWidth, el.clientHeight) / 6));
}

/** Weather tags over pins that sit close together would overlap: the later stop's tag hides. */
function declutter(pins: HTMLButtonElement[]) {
  const seen: DOMRect[] = [];
  for (const b of pins) {
    const t = b?.querySelector<HTMLElement>(".rpin-tag");
    if (!t) continue;
    t.style.visibility = "";
    const r = t.getBoundingClientRect();
    const pinR = pins.filter((x) => x && x !== b).map((x) => x.getBoundingClientRect());
    const hit = [...seen, ...pinR].some((o) => r.left < o.right && r.right > o.left && r.top < o.bottom && r.bottom > o.top);
    if (hit) t.style.visibility = "hidden"; else seen.push(r);
  }
}

/** Padding that keeps the route clear of the floating panels, when there are any. */
function room(el: HTMLElement, inset?: RouteMapOpts["inset"]): number | { top: number; right: number; bottom: number; left: number } {
  const p = pad(el);
  if (!inset) return p;
  const w = el.clientWidth, h = el.clientHeight;
  // never leave less than 120 px of map: on a small window the panels give way
  const left = Math.min(inset.left, Math.max(0, w - 120 - inset.right)), top = Math.min(inset.top, Math.max(0, h - 120 - inset.bottom));
  return { top: top + p, right: inset.right + p, bottom: inset.bottom + p, left: left + p };
}

type LineFeature = { type: "Feature"; properties: Record<string, number>; geometry: { type: "LineString"; coordinates: number[][] } };

/** The route grows from the first stop to the last over about 1.6 s; at once with reduced motion. */
function drawIn(src: maplibregl.GeoJSONSource, feats: LineFeature[]) {
  const total = feats.reduce((n, f) => n + Math.max(1, f.geometry.coordinates.length - 1), 0);
  if (reducedMotion() || total < 2) { src.setData({ type: "FeatureCollection", features: feats }); return; }
  const t0 = performance.now(), dur = 1600;
  const step = (now: number) => {
    const u = Math.min(1, (now - t0) / dur), e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
    let left = e * total;
    const part: LineFeature[] = [];
    for (const f of feats) {
      const c = f.geometry.coordinates, segs = Math.max(1, c.length - 1);
      if (left <= 0) break;
      if (left >= segs) { part.push(f); left -= segs; continue; }
      const k = Math.floor(left), r = left - k, a = c[k], b = c[Math.min(k + 1, c.length - 1)];
      part.push({ ...f, geometry: { type: "LineString", coordinates: [...c.slice(0, k + 1), [a[0] + (b[0] - a[0]) * r, a[1] + (b[1] - a[1]) * r]] } });
      left = 0;
    }
    try { src.setData({ type: "FeatureCollection", features: part }); } catch { return; } // the map is gone
    if (u < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
