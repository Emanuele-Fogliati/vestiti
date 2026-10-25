import { maplibregl } from "../lib/maplibre";
import { useEffect, useRef, useState } from "react";
import { loadLandmark } from "./Illustration";
import { PlaceCard } from "./PlaceCard";
import type { GlobeData, GlobePlace } from "../lib/worldmap";
import { baseStyle, loadPlaces, mapColors, placeLayers, placesGeoJSON, reducedMotion } from "../lib/worldmap";

const SPIN_DEG_PER_S = 3; // one turn in two minutes
const RESUME_AFTER_MS = 1500; // the globe starts turning again this long after you let go
const SPIN_UNTIL_ZOOM = 3; // closer than this you are exploring: the globe stays still

/** On wide screens the globe sits right of the headline: the map's centre moves right. */
function leftPad(el: HTMLElement): number {
  return el.clientWidth >= 900 ? Math.round(el.clientWidth * 0.36) : 0;
}

/** The zoom at which the whole globe fits the box with some air around it. */
function fitZoom(el: HTMLElement): number {
  const side = Math.min(el.clientWidth - leftPad(el), el.clientHeight);
  return Math.max(0.2, Math.log2(side / 520) + (el.clientWidth < 600 ? 1.75 : 1.5));
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

/** The home's centrepiece: a 3D globe that turns slowly by itself. Drag it to spin it faster,
 *  zoom in anywhere and the places worth seeing there appear, the most visited first. */
export default function Globe() {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [data, setData] = useState<GlobeData | null>(null);
  const [sel, setSel] = useState<GlobePlace | null>(null);
  const [close, setClose] = useState(false);
  const [failed, setFailed] = useState(false);
  const selRef = useRef<GlobePlace | null>(null);
  selRef.current = sel;
  // the spin loop lives in the map effect; these let the buttons pause and resume it
  const spin = useRef({ hold: () => {}, resume: () => {} });

  useEffect(() => { loadPlaces().then(setData).catch(() => setFailed(true)); }, []);

  useEffect(() => {
    const el = box.current;
    if (!el || !data) return;
    const c = mapColors();
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: el,
        style: baseStyle(c, { globe: true }),
        center: [-30, 12],
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
    map.setPadding({ left: leftPad(el), top: 0, right: 0, bottom: 0 });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");

    const markers: { m: maplibregl.Marker; z: number; on: boolean }[] = [];
    map.on("load", () => {
      // small screens: credits behind the (i) button, so they don't cover the globe
      if (el.clientWidth < 600) el.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      map.addSource("places", { type: "geojson", data: placesGeoJSON(data.places) });
      for (const l of placeLayers(c)) map.addLayer(l);
      map.addLayer({ id: "pl-sel", type: "circle", source: "places", filter: ["==", ["get", "i"], -1],
        paint: { "circle-radius": 13, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": c.ink, "circle-stroke-width": 2.5 } });
      // one picture per scene, on the most visited place it shows (Machu Picchu, not Aguas Calientes)
      const drawn = new Set<string>();
      for (const p of data.places) {
        if (!p.art || drawn.has(p.art)) continue;
        drawn.add(p.art);
        markers.push({ m: artMarker(p, () => pick(p)), z: 2.2, on: false });
      }
      showMarkers();
    });

    function showMarkers() {
      const z = map.getZoom();
      for (const k of markers) {
        const want = z >= k.z;
        if (want !== k.on) { if (want) k.m.addTo(map); else k.m.remove(); k.on = want; }
      }
    }

    function pick(p: GlobePlace) {
      setSel(p);
      hold();
    }

    const layers = ["pl-dot", "pl-name"];
    map.on("click", (e) => {
      const f = map.queryRenderedFeatures(e.point, { layers }).at(0)
        ?? map.queryRenderedFeatures([[e.point.x - 10, e.point.y - 10], [e.point.x + 10, e.point.y + 10]], { layers }).at(0);
      if (f) pick(data.places[f.properties.i as number]);
      else if (selRef.current) { selRef.current = null; setSel(null); release(); }
    });
    for (const l of layers) {
      map.on("mouseenter", l, () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", l, () => { map.getCanvas().style.cursor = ""; });
    }

    // Slow spin: paused while you touch the globe, while it glides after a flick, when you
    // are zoomed in, when a place is open, when the globe is off screen and when the
    // system asks for reduced motion.
    let busyUntil = 0;
    let onScreen = true;
    const still = reducedMotion();
    const hold = () => { busyUntil = Infinity; };
    const release = () => { if (!selRef.current) busyUntil = performance.now() + RESUME_AFTER_MS; };
    spin.current = { hold, resume: () => { busyUntil = performance.now() + RESUME_AFTER_MS; } };
    map.on("mousedown", hold); map.on("touchstart", hold); map.on("wheel", hold);
    map.on("moveend", (e) => { if ((e as { originalEvent?: Event }).originalEvent || busyUntil === Infinity) release(); });
    map.on("zoom", () => { setClose(map.getZoom() >= SPIN_UNTIL_ZOOM); showMarkers(); });
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
    };
  }, [data]);

  // ring around the open place
  useEffect(() => {
    const map = mapRef.current;
    if (map?.getLayer("pl-sel")) map.setFilter("pl-sel", ["==", ["get", "i"], sel ? data!.places.indexOf(sel) : -1]);
  }, [sel, data]);

  const zoomTo = (p: GlobePlace, zoom = 9) => mapRef.current?.flyTo({ center: [p.lon, p.lat], zoom, speed: 1.4, essential: true });

  function surprise() {
    if (!data) return;
    const pool = data.places.filter((p) => p.trips >= 15 && p.kind !== "city" && p.kind !== "town");
    const p = pool[Math.floor(Math.random() * pool.length)];
    setSel(p);
    spin.current.hold();
    zoomTo(p, 6.5);
  }

  function backToGlobe() {
    const map = mapRef.current;
    if (!map || !box.current) return;
    setSel(null);
    spin.current.resume();
    map.flyTo({ zoom: fitZoom(box.current), pitch: 0, bearing: 0, speed: 1.6 });
  }

  if (failed) return null;

  return (
    <section className={`globe${close ? " close" : ""}`} aria-label="Explore the world">
      <div className="globe-head wrap">
        <p className="kicker">Explore</p>
        <h2 className="globe-title">Where to <span className="hl">next?</span></h2>
        <p className="lede">Spin the globe and zoom in anywhere. The places organised trips visit most show up first, and more appear as you get closer.</p>
      </div>
      <div className="globe-map" ref={box}>
        {!data && <p className="globe-wait"><span className="spin" /></p>}
      </div>
      <div className="globe-tools">
        {close
          ? <button type="button" className="btn sm" onClick={backToGlobe}>Back to the globe</button>
          : <span className="globe-hint small">Drag to spin · scroll or pinch to zoom</span>}
        <button type="button" className="btn sm primary" onClick={surprise} disabled={!data}>Surprise me</button>
      </div>
      {sel && data && (
        <div className="globe-card">
          <PlaceCard place={sel} data={data}
            onClose={() => { setSel(null); spin.current.resume(); }}
            onZoom={mapRef.current && mapRef.current.getZoom() < 8 ? () => zoomTo(sel) : undefined} />
        </div>
      )}
    </section>
  );
}
