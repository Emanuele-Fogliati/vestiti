import { maplibregl } from "../lib/maplibre";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { loadLandmark } from "./Illustration";
import { PlaceCard } from "./PlaceCard";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import { groupPicks, pickStore, usePicks } from "../lib/picks";
import { DRESS_ME } from "../pages/Start";
import type { GlobeData, GlobePlace } from "../lib/worldmap";
import {
  baseStyle, insideOf, insideZoom, km, loadPlaces, mapColors, placeLayers, placesGeoJSON, reducedMotion, sceneAnchor,
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

/** A round thumbnail of one landmark scene, pinned on the globe. */
function artMarker(art: string, onClick: () => void): { m: maplibregl.Marker; el: HTMLButtonElement } {
  const el = document.createElement("button");
  el.type = "button";
  el.className = "gmark";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "50 0 200 200");
  svg.setAttribute("preserveAspectRatio", "xMidYMid slice");
  el.appendChild(svg);
  loadLandmark(art).then((s) => { if (s) svg.innerHTML = s; });
  el.addEventListener("click", (e) => { e.stopPropagation(); onClick(); });
  return { m: new maplibregl.Marker({ element: el, anchor: "bottom", opacityWhenCovered: "0" }), el };
}

/** One landmark scene and the places it shows (Rome and the Colosseum share one). */
interface Scene { owners: GlobePlace[]; m: maplibregl.Marker; el: HTMLButtonElement; opens: GlobePlace | null; on: boolean }

/** The home's centrepiece: a globe of places, no routes. It turns slowly by itself; zoom in
 *  anywhere and the places worth seeing appear, the most visited first, with their pictures.
 *  From far away a city stands for everything in it (Florence); zoomed on it, its places show
 *  (the Uffizi, Ponte Vecchio). Pick whole cities or single places for your own trip. */
export default function Globe() {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [data, setData] = useState<GlobeData | null>(null);
  const [sel, setSel] = useState<GlobePlace | null>(null);
  const [close, setClose] = useState(false);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [tripErr, setTripErr] = useState<string | null>(null);
  const picks = usePicks();
  const { ensureUser } = useApp();
  const nav = useNavigate();
  const byId = useMemo(() => new Map((data?.places ?? []).map((p) => [p.id, p])), [data]);
  const inside = useMemo(() => insideOf(data?.places ?? []), [data]);
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

    const scenes: Scene[] = [];
    const places = new Map(data.places.map((p) => [p.id, p]));
    map.on("load", () => {
      // small screens: credits behind the (i) button, so they don't cover the globe
      if (narrow(el)) el.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      map.addSource("places", { type: "geojson", data: placesGeoJSON(data.places) });
      // from space only the big places have a name; more appear as you get closer
      for (const l of placeLayers(c)) map.addLayer(l);
      map.addLayer({ id: "pl-sel", type: "circle", source: "places", filter: ["==", ["get", "i"], -1],
        paint: { "circle-radius": 13, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": c.ink, "circle-stroke-width": 2.5 } });

      // one picture per scene; its owners most visited first (Machu Picchu, not Aguas Calientes)
      const byArt = new Map<string, GlobePlace[]>();
      for (const p of data.places) {
        if (!p.art) continue;
        const l = byArt.get(p.art);
        if (l) l.push(p); else byArt.set(p.art, [p]);
      }
      for (const owners of byArt.values()) {
        const s = { owners, opens: null, on: false } as unknown as Scene;
        Object.assign(s, artMarker(owners[0].art!, () => { if (s.opens) handlers.current.pickPlace(s.opens); }));
        scenes.push(s);
      }
      showMarkers();
      setReady(true);
    });

    // pictures once you are close, never on top of each other: where two would overlap, the
    // place's own picture beats one shown for a place inside it, then the more visited place
    // wins. Only pictures on the side of the globe you see and on screen: a hidden one on the
    // far side still took taps (Ho Chi Minh City sits right behind Cusco).
    const GAP_PX = 54;
    function showMarkers() {
      const z = map.getZoom();
      const far = z < PICTURES_FROM_ZOOM;
      const kept: { x: number; y: number }[] = [];
      const c = map.getCenter();
      const { clientWidth: w, clientHeight: h } = map.getContainer();
      const placed = scenes.map((s) => ({ s, a: far ? null : sceneAnchor(s.owners, z, places) }))
        .sort((x, y) => (x.a && y.a ? Number(y.a.own) - Number(x.a.own) || y.a.at.level - x.a.at.level : 0));
      for (const { s, a } of placed) {
        let want = !!a && km(c.lat, c.lng, a.at.lat, a.at.lon) < 7000;
        if (want && a) {
          const pt = map.project([a.at.lon, a.at.lat]);
          want = pt.x > -GAP_PX && pt.y > -GAP_PX && pt.x < w + GAP_PX && pt.y < h + GAP_PX
            && !kept.some((o) => Math.abs(o.x - pt.x) < GAP_PX && Math.abs(o.y - pt.y) < GAP_PX);
          if (want) {
            kept.push(pt);
            s.m.setLngLat([a.at.lon, a.at.lat]);
            if (s.opens !== a.opens) {
              s.opens = a.opens;
              s.el.setAttribute("aria-label", a.opens.name);
              s.el.title = a.opens.name;
            }
          }
        }
        if (want !== s.on) { if (want) s.m.addTo(map); else s.m.remove(); s.on = want; }
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
      for (const s of scenes) s.m.remove();
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

  /** Zoom on a city until the places inside it show, all of them on screen. */
  function zoomInside(city: GlobePlace) {
    const map = mapRef.current;
    const el = box.current;
    const kids = inside.get(city.id) ?? [];
    if (!map || !el || !kids.length) return;
    const b = new maplibregl.LngLatBounds([city.lon, city.lat], [city.lon, city.lat]);
    kids.forEach((p) => b.extend([p.lon, p.lat]));
    const pad = narrow(el)
      ? { top: topPad(el) + 10, bottom: el.clientHeight * 0.5, left: 30, right: 30 }
      : { top: 110, bottom: 60, left: 60, right: Math.min(460, el.clientWidth * 0.4) };
    const cam = map.cameraForBounds(b, { padding: pad, maxZoom: 15 });
    const need = insideZoom(kids[0].level) + 0.3; // at least the most visited ones show
    map.flyTo({ center: b.getCenter(), zoom: Math.min(15, Math.max(need, cam?.zoom ?? need)), speed: 1.4, essential: true });
  }

  /** Open another place from a card (a place inside the city, or the city) and go there. */
  function openPlace(p: GlobePlace) {
    const map = mapRef.current;
    setSel(p);
    spin.current.hold();
    if (!map) return;
    if (inside.has(p.id)) zoomInside(p);
    else if (p.parent) map.flyTo({ center: [p.lon, p.lat], zoom: Math.max(map.getZoom(), insideZoom(p.level) + 1.5), speed: 1.4, essential: true });
  }

  async function dressPicked() {
    setBusy(true); setTripErr(null);
    try {
      await ensureUser();
      const t = await api.pickedTrip(picks.filter((id) => byId.has(id)));
      pickStore.clear();
      nav(`/trips/${t.id}`);
    } catch (e) {
      setTripErr((e as Error).message);
      setBusy(false);
    }
  }

  function backToGlobe() {
    const map = mapRef.current;
    if (!map || !box.current) return;
    setSel(null);
    spin.current.resume();
    map.flyTo({ zoom: fitZoom(box.current), pitch: 0, bearing: 0, speed: 1.6 });
  }

  if (failed) return null;
  const open = !!sel;
  const trip = groupPicks(picks.filter((id) => byId.has(id)), (id) => byId.get(id)?.parent);
  const selInside = sel ? inside.get(sel.id) ?? [] : [];
  const zoomNow = mapRef.current?.getZoom() ?? 0;
  const selZoom = !sel ? undefined
    : selInside.length ? () => zoomInside(sel)
      : sel.parent ? (zoomNow < 14 ? () => mapRef.current?.flyTo({ center: [sel.lon, sel.lat], zoom: 15, speed: 1.4, essential: true }) : undefined)
        : zoomNow < 8 ? () => mapRef.current?.flyTo({ center: [sel.lon, sel.lat], zoom: 9, speed: 1.4, essential: true }) : undefined;

  return (
    <section className={`globe${close ? " close" : ""}${open ? " open" : ""}${trip.length ? " has-trip" : ""}`} aria-label="Explore the world">
      <div className="globe-map" ref={box}>
        {!data && <p className="globe-wait"><span className="spin" /></p>}
      </div>
      <div className="globe-head">
        <h2 className="globe-title">Where to <span className="hl">next?</span></h2>
      </div>
      <div className="globe-tools">
        {close
          ? <button type="button" className="btn sm" onClick={backToGlobe}>Back to the globe</button>
          : <span className="globe-hint small">Drag to spin · zoom in anywhere, or on a city to see the places inside it</span>}
      </div>
      {sel && data && (
        <div className="globe-card">
          <PlaceCard key={sel.id} place={sel} onClose={handlers.current.clear}
            inside={selInside} parent={sel.parent ? byId.get(sel.parent) ?? null : null} onPlace={openPlace} pickable
            onZoom={selZoom} zoomLabel={selInside.length ? "Show the places inside" : undefined} />
        </div>
      )}
      {trip.length > 0 && (
        <div className="globe-trip" aria-label="Your trip">
          <p className="label">Your trip</p>
          <ol>
            {trip.map((s) => {
              const city = byId.get(s.id)!;
              return (
                <li key={s.id}>
                  <span>
                    <button type="button" className="linkish" onClick={() => openPlace(city)}>{city.name}</button>
                    {s.inside.length > 0 && (
                      <span className="small muted">{s.whole ? " · all, with " : ": "}{s.inside.map((id) => byId.get(id)!.name).join(", ")}</span>
                    )}
                  </span>
                  <button type="button" className="pcard-add on" aria-label={`Remove ${city.name} from my trip`}
                    onClick={() => pickStore.remove([s.id, ...s.inside])}>✕</button>
                </li>
              );
            })}
          </ol>
          <p className="globe-trip-sum">{trip.map((s) => byId.get(s.id)!.name + (s.inside.length ? ` (+${s.inside.length})` : "")).join(" · ")}</p>
          {tripErr && <p className="err small">{tripErr}</p>}
          <div className="row">
            <button type="button" className="btn sm primary" disabled={busy} onClick={dressPicked}>{busy ? <span className="spin" /> : DRESS_ME}</button>
            <button type="button" className="btn sm ghost" onClick={() => pickStore.clear()}>Clear</button>
          </div>
        </div>
      )}
    </section>
  );
}
