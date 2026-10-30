import { maplibregl } from "../lib/maplibre";
import { useEffect, useMemo, useRef, useState } from "react";
import type { FeatureCollection } from "geojson";
import { loadLandmark } from "./Illustration";
import { PlaceCard } from "./PlaceCard";
import { RouteCard } from "./RouteCard";
import { MONTH_LONG } from "../lib/format";
import type { GlobeData, GlobePlace, GlobeRoute, RouteData } from "../lib/worldmap";
import {
  baseStyle, countriesLabel, km, loadPlaces, loadRoutes, mapColors, placeLayers, placesGeoJSON, reducedMotion, routesThrough,
} from "../lib/worldmap";

const SPIN_DEG_PER_S = 3; // one turn in two minutes
const RESUME_AFTER_MS = 1500; // the globe starts turning again this long after you let go
const SPIN_UNTIL_ZOOM = 3; // closer than this you are exploring: the globe stays still
const PLACES_FROM_ZOOM = 3.5; // from far away the routes speak; places show when you get closer
const DEFAULT_BUCKET = "10d";

const narrow = (el: HTMLElement) => el.clientWidth < 600;

/** Web Mercator pixels at zoom 0 (512 px world). */
function merc(lon: number, lat: number): [number, number] {
  const s = Math.sin((lat * Math.PI) / 180);
  return [((lon + 180) / 360) * 512, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * 512];
}

/** Room the title and the length picker take at the top, so the globe sits below them. */
function topPad(el: HTMLElement): number {
  return narrow(el) ? 160 : 150;
}

/** The zoom at which the whole globe fills the box under the title. */
function fitZoom(el: HTMLElement): number {
  const side = Math.min(el.clientWidth, el.clientHeight - topPad(el));
  return Math.max(0.2, Math.log2(side / 512) + (narrow(el) ? 1.75 : 1.62));
}

/** A round thumbnail of the place's own illustration, pinned on the globe. */
function artMarker(p: GlobePlace, onClick: () => void): maplibregl.Marker {
  const el = document.createElement("button");
  el.type = "button";
  el.className = "gmark";
  el.setAttribute("aria-label", p.name);
  el.title = p.name;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "50 0 200 200");
  svg.setAttribute("preserveAspectRatio", "xMidYMid slice");
  el.appendChild(svg);
  if (p.art) loadLandmark(p.art).then((s) => { if (s) svg.innerHTML = s; });
  el.addEventListener("click", (e) => { e.stopPropagation(); onClick(); });
  return new maplibregl.Marker({ element: el, anchor: "bottom", opacityWhenCovered: "0" }).setLngLat([p.lon, p.lat]);
}

function routeLines(rs: GlobeRoute[]): FeatureCollection {
  return { type: "FeatureCollection", features: rs.map((r, i) => ({
    type: "Feature", id: i, properties: { id: r.id },
    geometry: { type: "LineString", coordinates: r.stops.map((s) => [s.lon, s.lat]) },
  })) };
}

/** One label per route, on its middle stop: the country name you read from space. */
function routeLabels(rs: GlobeRoute[]): FeatureCollection {
  const seen = new Set<string>();
  const out: FeatureCollection = { type: "FeatureCollection", features: [] };
  for (const r of rs) {
    const t = countriesLabel(r.countries);
    if (seen.has(t)) continue; // two routes in Brazil: one label is enough
    seen.add(t);
    const s = r.stops[Math.floor(r.stops.length / 2)];
    out.features.push({ type: "Feature", properties: { id: r.id, t }, geometry: { type: "Point", coordinates: [s.lon, s.lat] } });
  }
  return out;
}

/** The open route's stops, numbered; a place you come back to shows both numbers ("3 · 6"). */
function routeStops(r: GlobeRoute | null): FeatureCollection {
  const at = new Map<string, { n: number[]; name: string; lon: number; lat: number }>();
  (r?.stops ?? []).forEach((s, i) => {
    const k = `${s.lat},${s.lon}`;
    const hit = at.get(k);
    if (hit) hit.n.push(i + 1);
    else at.set(k, { n: [i + 1], name: s.name, lon: s.lon, lat: s.lat });
  });
  return { type: "FeatureCollection", features: [...at.values()].map((s) => ({
    type: "Feature", properties: { n: s.n.join(" · "), w: s.n.length, name: s.name },
    geometry: { type: "Point", coordinates: [s.lon, s.lat] },
  })) };
}

/** The home's centrepiece: "find your trip". Pick how long you have, the globe shows the routes
 *  of that length that organised trips really follow; open one and we dress you for it. The
 *  globe turns slowly by itself; zoom in anywhere and the places worth seeing appear. */
export default function Globe() {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [data, setData] = useState<GlobeData | null>(null);
  const [rdata, setRdata] = useState<RouteData | null>(null);
  const [bucket, setBucket] = useState(DEFAULT_BUCKET);
  const [month, setMonth] = useState<number | null>(null);
  const [route, setRoute] = useState<GlobeRoute | null>(null);
  const [sel, setSel] = useState<GlobePlace | null>(null);
  const [close, setClose] = useState(false);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const openRef = useRef(false);
  const routeOpen = useRef(false);
  routeOpen.current = !!route;
  const refreshMarkers = useRef(() => {});
  openRef.current = !!(sel || route);
  // the map's handlers live in the map effect; these let React state reach them
  const handlers = useRef({ pickPlace: (_p: GlobePlace) => {}, pickRoute: (_id: string) => {}, clear: () => {} });
  const spin = useRef({ hold: () => {}, resume: () => {} });

  useEffect(() => {
    loadPlaces().then(setData).catch(() => setFailed(true));
    loadRoutes().then(setRdata).catch(() => setRdata({ buckets: [], routes: [] }));
  }, []);

  const fits = (r: GlobeRoute) => month === null || r.best_months.includes(month);
  const shown = useMemo(() => rdata?.routes.filter((r) => r.bucket === bucket && (month === null || r.best_months.includes(month))) ?? [],
    [rdata, bucket, month]);
  const shownRef = useRef(shown);
  shownRef.current = shown;

  useEffect(() => {
    const el = box.current;
    if (!el || !data) return;
    const c = mapColors();
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: el,
        style: baseStyle(c, { globe: true }),
        center: [15, 18],
        zoom: fitZoom(el),
        minZoom: 0,
        maxZoom: 16,
        maxPitch: 60,
        renderWorldCopies: false,
        attributionControl: { compact: true },
        pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
        fadeDuration: 150,
      });
    } catch {
      setFailed(true);
      return;
    }
    mapRef.current = map;
    if (new URLSearchParams(location.search).has("mapdebug")) (window as unknown as { __map: unknown }).__map = map;
    map.setPadding({ top: topPad(el), left: 0, right: 0, bottom: 0 });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");

    const markers: { m: maplibregl.Marker; at: [number, number]; on: boolean }[] = [];
    map.on("load", () => {
      // small screens: credits behind the (i) button, so they don't cover the globe
      if (narrow(el)) el.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      map.addSource("places", { type: "geojson", data: placesGeoJSON(data.places) });
      for (const l of placeLayers(c)) {
        const f = (l as { filter: maplibregl.FilterSpecification }).filter;
        map.addLayer({ ...l, filter: ["all", f, [">=", ["zoom"], PLACES_FROM_ZOOM]] } as maplibregl.LayerSpecification);
      }
      map.addLayer({ id: "pl-sel", type: "circle", source: "places", filter: ["==", ["get", "i"], -1],
        paint: { "circle-radius": 13, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": c.ink, "circle-stroke-width": 2.5 } });

      // routes: a soft white casing so lines read on any ground, the open one in the accent
      const round = { "line-cap": "round", "line-join": "round" } as const;
      map.addSource("routes", { type: "geojson", data: routeLines(shownRef.current) });
      map.addSource("route-labels", { type: "geojson", data: routeLabels(shownRef.current) });
      map.addSource("route-stops", { type: "geojson", data: routeStops(null) });
      map.addLayer({ id: "rt-case", type: "line", source: "routes", layout: round, paint: { "line-color": c.halo, "line-width": 6 } }, "pl-dot");
      map.addLayer({ id: "rt", type: "line", source: "routes", layout: round,
        paint: { "line-color": c.ink, "line-width": ["case", ["boolean", ["feature-state", "hover"], false], 4, 2.6], "line-opacity": 0.9 } }, "pl-dot");
      map.addLayer({ id: "rt-hit", type: "line", source: "routes", layout: round, paint: { "line-color": "rgba(0,0,0,0)", "line-width": 18 } });
      map.addLayer({ id: "rt-on-case", type: "line", source: "routes", filter: ["==", ["get", "id"], ""], layout: round,
        paint: { "line-color": c.ink, "line-width": 8 } });
      map.addLayer({ id: "rt-on", type: "line", source: "routes", filter: ["==", ["get", "id"], ""], layout: round,
        paint: { "line-color": c.accent, "line-width": 4.5 } });
      map.addLayer({ id: "rt-label", type: "symbol", source: "route-labels", maxzoom: 5,
        layout: { "text-field": ["get", "t"], "text-font": ["Noto Sans Bold"], "text-size": 12.5, "text-max-width": 8,
          "text-variable-anchor": ["left", "right", "top", "bottom"], "text-radial-offset": 1.1 },
        paint: { "text-color": c.ink, "text-halo-color": c.halo, "text-halo-width": 2.2 } });
      map.addLayer({ id: "st", type: "circle", source: "route-stops",
        paint: { "circle-radius": ["case", [">", ["get", "w"], 1], 14, 10.5], "circle-color": c.ink, "circle-stroke-color": c.halo, "circle-stroke-width": 2 } });
      map.addLayer({ id: "st-n", type: "symbol", source: "route-stops",
        layout: { "text-field": ["get", "n"], "text-font": ["Noto Sans Bold"], "text-size": ["case", [">", ["get", "w"], 1], 9.5, 11.5], "text-allow-overlap": true, "text-ignore-placement": true },
        paint: { "text-color": c.halo } });
      map.addLayer({ id: "st-name", type: "symbol", source: "route-stops",
        layout: { "text-field": ["get", "name"], "text-font": ["Noto Sans Bold"], "text-size": 13, "text-optional": true,
          "text-variable-anchor": ["left", "right", "top", "bottom"], "text-radial-offset": ["case", [">", ["get", "w"], 1], 1.5, 1.15] },
        paint: { "text-color": c.ink, "text-halo-color": c.halo, "text-halo-width": 2 } });

      // one picture per scene, on the most visited place it shows (Machu Picchu, not Aguas Calientes)
      const drawn = new Set<string>();
      for (const p of data.places) {
        if (!p.art || drawn.has(p.art)) continue;
        drawn.add(p.art);
        markers.push({ m: artMarker(p, () => handlers.current.pickPlace(p)), at: [p.lon, p.lat], on: false });
      }
      showMarkers();
      refreshMarkers.current = showMarkers;
      setReady(true);
    });

    // pictures once you are close, never on top of each other: where two would overlap, the
    // more visited place keeps its picture (markers are in that order). Only pictures on the
    // side of the globe you see and on screen: a hidden one on the far side still took taps
    // (Ho Chi Minh City sits right behind Cusco).
    const GAP_PX = 54;
    function showMarkers() {
      const far = map.getZoom() < PLACES_FROM_ZOOM || routeOpen.current;
      const kept: { x: number; y: number }[] = [];
      const c = map.getCenter();
      const { clientWidth: w, clientHeight: h } = map.getContainer();
      for (const k of markers) {
        let want = !far && km(c.lat, c.lng, k.at[1], k.at[0]) < 7000;
        if (want) {
          const pt = map.project(k.at);
          want = pt.x > -GAP_PX && pt.y > -GAP_PX && pt.x < w + GAP_PX && pt.y < h + GAP_PX
            && !kept.some((o) => Math.abs(o.x - pt.x) < GAP_PX && Math.abs(o.y - pt.y) < GAP_PX);
          if (want) kept.push(pt);
        }
        if (want !== k.on) { if (want) k.m.addTo(map); else k.m.remove(); k.on = want; }
      }
    }

    // a tap right on a place opens the place, a tap on a line the route; nothing: close
    const around = (e: maplibregl.MapMouseEvent, r: number): [maplibregl.PointLike, maplibregl.PointLike] =>
      [[e.point.x - r, e.point.y - r], [e.point.x + r, e.point.y + r]];
    map.on("click", (e) => {
      const place = map.queryRenderedFeatures(around(e, 5), { layers: ["pl-dot", "pl-name"] }).at(0);
      const line = place ? undefined : map.queryRenderedFeatures(around(e, 9), { layers: ["rt-hit", "rt-label"] }).at(0);
      const near = place || line ? undefined : map.queryRenderedFeatures(around(e, 12), { layers: ["pl-dot", "pl-name"] }).at(0);
      if (place || near) handlers.current.pickPlace(data.places[(place ?? near)!.properties.i as number]);
      else if (line) handlers.current.pickRoute(line.properties.id as string);
      else if (openRef.current) handlers.current.clear();
    });
    let hovered: number | null = null;
    map.on("mousemove", "rt-hit", (e) => {
      const id = e.features?.[0]?.id as number | undefined;
      if (id === undefined || id === hovered) return;
      if (hovered !== null) map.setFeatureState({ source: "routes", id: hovered }, { hover: false });
      hovered = id;
      map.setFeatureState({ source: "routes", id }, { hover: true });
    });
    map.on("mouseleave", "rt-hit", () => {
      if (hovered !== null) map.setFeatureState({ source: "routes", id: hovered }, { hover: false });
      hovered = null;
    });
    for (const l of ["pl-dot", "pl-name", "rt-hit", "rt-label"]) {
      map.on("mouseenter", l, () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", l, () => { map.getCanvas().style.cursor = ""; });
    }

    // Slow spin: paused while you touch the globe, while it glides after a flick, when you
    // are zoomed in, when a route or a place is open, when the globe is off screen and when
    // the system asks for reduced motion.
    let busyUntil = 0;
    let onScreen = true;
    const still = reducedMotion();
    const hold = () => { busyUntil = Infinity; };
    const release = () => { if (!openRef.current) busyUntil = performance.now() + RESUME_AFTER_MS; };
    spin.current = { hold, resume: () => { busyUntil = performance.now() + RESUME_AFTER_MS; } };
    map.on("mousedown", hold); map.on("touchstart", hold); map.on("wheel", hold);
    map.on("moveend", (e) => { if ((e as { originalEvent?: Event }).originalEvent || busyUntil === Infinity) release(); });
    map.on("zoom", () => setClose(map.getZoom() >= SPIN_UNTIL_ZOOM));
    map.on("moveend", showMarkers);
    const io = new IntersectionObserver(([en]) => { onScreen = en.isIntersecting; });
    io.observe(el);

    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (!still && onScreen && !document.hidden && now > busyUntil && !map.isMoving()
        && map.getZoom() < SPIN_UNTIL_ZOOM && map.loaded()) {
        const ctr = map.getCenter();
        map.jumpTo({ center: [ctr.lng - SPIN_DEG_PER_S * dt, ctr.lat] });
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      for (const k of markers) k.m.remove();
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, [data]);

  // the routes of the chosen length
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    (map.getSource("routes") as maplibregl.GeoJSONSource | undefined)?.setData(routeLines(shown));
    (map.getSource("route-labels") as maplibregl.GeoJSONSource | undefined)?.setData(routeLabels(shown));
  }, [shown, ready]);

  // the open route: accent line, numbered stops, the other routes fade
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setFilter("rt-on", ["==", ["get", "id"], route?.id ?? ""]);
    map.setFilter("rt-on-case", ["==", ["get", "id"], route?.id ?? ""]);
    map.setPaintProperty("rt", "line-opacity", route ? 0.22 : 0.9);
    map.setLayoutProperty("rt-label", "visibility", route ? "none" : "visible");
    map.setLayoutProperty("pl-name", "visibility", route ? "none" : "visible");
    map.setPaintProperty("pl-dot", "circle-opacity", route ? 0.3 : 1);
    map.setPaintProperty("pl-dot", "circle-stroke-opacity", route ? 0.3 : 1);
    refreshMarkers.current();
    (map.getSource("route-stops") as maplibregl.GeoJSONSource).setData(routeStops(route));
  }, [route, ready]);

  // ring around the open place
  useEffect(() => {
    const map = mapRef.current;
    if (ready && map) map.setFilter("pl-sel", ["==", ["get", "i"], sel && data ? data.places.indexOf(sel) : -1]);
  }, [sel, data, ready]);

  function frame(r: GlobeRoute) {
    const map = mapRef.current;
    const el = box.current;
    if (!map || !el) return;
    const b = new maplibregl.LngLatBounds();
    r.stops.forEach((s) => b.extend([s.lon, s.lat]));
    if (narrow(el)) {
      // phone: the route sits between the heading and the card that covers the lower half.
      // fitBounds on the globe misplaces it when the map has its own top padding, so the zoom
      // and the shift are worked out here, in Web Mercator pixels.
      const w = el.clientWidth, h = el.clientHeight;
      const top = topPad(el) + 10, bottom = h * 0.43;
      const [x0, y0] = merc(b.getWest(), b.getNorth()), [x1, y1] = merc(b.getEast(), b.getSouth());
      const zoom = Math.min(7.5, Math.log2(Math.min((w - 72) / Math.max(x1 - x0, 1e-6), (bottom - top) / Math.max(y1 - y0, 1e-6))));
      const centreY = topPad(el) + (h - topPad(el)) / 2; // where the map puts its centre
      map.flyTo({ center: b.getCenter(), zoom, offset: [0, (top + bottom) / 2 - centreY], speed: 1.4, essential: true });
      return;
    }
    const pad = { top: 110, bottom: 60, left: 80, right: Math.min(480, el.clientWidth * 0.4) };
    map.fitBounds(b, { padding: pad, maxZoom: 7.5, speed: 1.4, essential: true });
  }

  function openRoute(r: GlobeRoute) {
    if (r.bucket !== bucket) setBucket(r.bucket);
    setSel(null);
    setRoute(r);
    spin.current.hold();
    frame(r);
  }

  handlers.current = {
    pickPlace: (p) => { setRoute(null); setSel(p); spin.current.hold(); },
    pickRoute: (id) => { const r = shownRef.current.find((x) => x.id === id); if (r) openRoute(r); },
    clear: () => { setRoute(null); setSel(null); spin.current.resume(); },
  };

  function backToGlobe() {
    const map = mapRef.current;
    if (!map || !box.current) return;
    setSel(null);
    setRoute(null);
    spin.current.resume();
    map.flyTo({ zoom: fitZoom(box.current), pitch: 0, bearing: 0, speed: 1.6 });
  }

  function pickBucket(k: string) {
    setBucket(k);
    if (route && route.bucket !== k) { setRoute(null); spin.current.resume(); }
  }

  function pickMonth(m: number | null) {
    setMonth(m);
    if (route && m !== null && !route.best_months.includes(m)) { setRoute(null); spin.current.resume(); }
  }

  if (failed) return null;
  const through = sel && rdata ? routesThrough(sel, rdata.routes.filter(fits)) : [];
  const empty = !!rdata && rdata.routes.length > 0 && shown.length === 0;
  const open = !!(sel || route);

  return (
    <section className={`globe${close ? " close" : ""}${open ? " open" : ""}`} aria-label="Find your trip">
      <div className="globe-map" ref={box}>
        {!data && <p className="globe-wait"><span className="spin" /></p>}
      </div>
      <div className="globe-head">
        <h2 className="globe-title">Where to <span className="hl">next?</span></h2>
        {rdata && rdata.buckets.length > 0 && (
          <div className="globe-len" role="group" aria-label="How long is your trip?">
            <span className="label">How long?</span>
            {rdata.buckets.map((b) => (
              <button key={b.key} type="button" className="fchip" aria-pressed={b.key === bucket} onClick={() => pickBucket(b.key)}>{b.label}</button>
            ))}
            <span className="globe-sep" aria-hidden="true" />
            <label className="globe-when">
              <span className="label">When?</span>
              <select className={`fchip${month ? " on" : ""}`} value={month ?? ""} aria-label="Month of your trip"
                onChange={(e) => pickMonth(e.target.value ? Number(e.target.value) : null)}>
                <option value="">Any month</option>
                {MONTH_LONG.map((n, i) => <option key={n} value={i + 1}>{n}</option>)}
              </select>
            </label>
          </div>
        )}
      </div>
      <div className="globe-tools">
        {close
          ? <button type="button" className="btn sm" onClick={backToGlobe}>Back to the globe</button>
          : empty
            ? <span className="globe-hint small on">No route of this length has good weather in {MONTH_LONG[(month ?? 1) - 1]}. Try another length or month.</span>
            : <span className="globe-hint small">{month
              ? `Routes with good weather in ${MONTH_LONG[month - 1]}. Tap one, or zoom in anywhere.`
              : "Every line is a route travellers follow. Tap one, or zoom in anywhere."}</span>}
      </div>
      {route && (
        <div className="globe-card">
          <RouteCard key={route.id} route={route} month={month} onClose={handlers.current.clear} />
        </div>
      )}
      {sel && data && (
        <div className="globe-card">
          <PlaceCard place={sel} routes={through} onRoute={openRoute} onClose={handlers.current.clear}
            onZoom={mapRef.current && mapRef.current.getZoom() < 8 ? () => mapRef.current?.flyTo({ center: [sel.lon, sel.lat], zoom: 9, speed: 1.4, essential: true }) : undefined} />
        </div>
      )}
    </section>
  );
}
