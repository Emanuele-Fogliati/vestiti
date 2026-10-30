import { maplibregl } from "../lib/maplibre";
import { useEffect, useRef, useState } from "react";
import { loadLandmark } from "./Illustration";
import { PlaceCard } from "./PlaceCard";
import type { GlobeData, GlobePlace } from "../lib/worldmap";
import {
  baseStyle, km, loadPlaces, mapColors, placeLayers, placesGeoJSON, reducedMotion,
} from "../lib/worldmap";

const SPIN_DEG_PER_S = 3; // one turn in two minutes
const RESUME_AFTER_MS = 1500; // the globe starts turning again this long after you let go
const SPIN_UNTIL_ZOOM = 3; // closer than this you are exploring: the globe stays still
const PICTURES_FROM_ZOOM = 2.2; // from space only the names of the big places; pictures once you get closer

const narrow = (el: HTMLElement) => el.clientWidth < 600;

/** Room the title takes at the top, so the globe sits below it. */
function topPad(el: HTMLElement): number {
  return narrow(el) ? 70 : 100;
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

/** The home's centrepiece: a globe of places, no routes. It turns slowly by itself; zoom in
 *  anywhere and the places worth seeing appear, the most visited first, with their pictures. */
export default function Globe() {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [data, setData] = useState<GlobeData | null>(null);
  const [sel, setSel] = useState<GlobePlace | null>(null);
  const [close, setClose] = useState(false);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const openRef = useRef(false);
  openRef.current = !!sel;
  // the map's handlers live in the map effect; these let React state reach them
  const handlers = useRef({ pickPlace: (_p: GlobePlace) => {}, clear: () => {} });
  const spin = useRef({ hold: () => {}, resume: () => {} });

  useEffect(() => {
    loadPlaces().then(setData).catch(() => setFailed(true));
  }, []);

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
      // from space only the big places have a name; more appear as you get closer
      for (const l of placeLayers(c)) map.addLayer(l);
      map.addLayer({ id: "pl-sel", type: "circle", source: "places", filter: ["==", ["get", "i"], -1],
        paint: { "circle-radius": 13, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": c.ink, "circle-stroke-width": 2.5 } });

      // one picture per scene, on the most visited place it shows (Machu Picchu, not Aguas Calientes)
      const drawn = new Set<string>();
      for (const p of data.places) {
        if (!p.art || drawn.has(p.art)) continue;
        drawn.add(p.art);
        markers.push({ m: artMarker(p, () => handlers.current.pickPlace(p)), at: [p.lon, p.lat], on: false });
      }
      showMarkers();
      setReady(true);
    });

    // pictures once you are close, never on top of each other: where two would overlap, the
    // more visited place keeps its picture (markers are in that order). Only pictures on the
    // side of the globe you see and on screen: a hidden one on the far side still took taps
    // (Ho Chi Minh City sits right behind Cusco).
    const GAP_PX = 54;
    function showMarkers() {
      const far = map.getZoom() < PICTURES_FROM_ZOOM;
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

    // a tap on a place (or right next to one) opens it; on nothing: close
    const around = (e: maplibregl.MapMouseEvent, r: number): [maplibregl.PointLike, maplibregl.PointLike] =>
      [[e.point.x - r, e.point.y - r], [e.point.x + r, e.point.y + r]];
    map.on("click", (e) => {
      const place = map.queryRenderedFeatures(around(e, 5), { layers: ["pl-dot", "pl-name"] }).at(0);
      const near = place ? undefined : map.queryRenderedFeatures(around(e, 12), { layers: ["pl-dot", "pl-name"] }).at(0);
      if (place || near) handlers.current.pickPlace(data.places[(place ?? near)!.properties.i as number]);
      else if (openRef.current) handlers.current.clear();
    });
    for (const l of ["pl-dot", "pl-name"]) {
      map.on("mouseenter", l, () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", l, () => { map.getCanvas().style.cursor = ""; });
    }

    // Slow spin: paused while you touch the globe, while it glides after a flick, when you
    // are zoomed in, when a place is open, when the globe is off screen and when
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

  // ring around the open place
  useEffect(() => {
    const map = mapRef.current;
    if (ready && map) map.setFilter("pl-sel", ["==", ["get", "i"], sel && data ? data.places.indexOf(sel) : -1]);
  }, [sel, data, ready]);

  handlers.current = {
    pickPlace: (p) => { setSel(p); spin.current.hold(); },
    clear: () => { setSel(null); spin.current.resume(); },
  };

  function backToGlobe() {
    const map = mapRef.current;
    if (!map || !box.current) return;
    setSel(null);
    spin.current.resume();
    map.flyTo({ zoom: fitZoom(box.current), pitch: 0, bearing: 0, speed: 1.6 });
  }

  if (failed) return null;
  const open = !!sel;

  return (
    <section className={`globe${close ? " close" : ""}${open ? " open" : ""}`} aria-label="Explore the world">
      <div className="globe-map" ref={box}>
        {!data && <p className="globe-wait"><span className="spin" /></p>}
      </div>
      <div className="globe-head">
        <h2 className="globe-title">Where to <span className="hl">next?</span></h2>
      </div>
      <div className="globe-tools">
        {close
          ? <button type="button" className="btn sm" onClick={backToGlobe}>Back to the globe</button>
          : <span className="globe-hint small">Drag to spin · zoom in anywhere to see the places worth visiting</span>}
      </div>
      {sel && data && (
        <div className="globe-card">
          <PlaceCard place={sel} onClose={handlers.current.clear}
            onZoom={mapRef.current && mapRef.current.getZoom() < 8 ? () => mapRef.current?.flyTo({ center: [sel.lon, sel.lat], zoom: 9, speed: 1.4, essential: true }) : undefined} />
        </div>
      )}
    </section>
  );
}
