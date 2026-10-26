import { maplibregl } from "../lib/maplibre";
import { useEffect, useMemo, useRef, useState } from "react";
import { PlaceCard } from "./PlaceCard";
import type { GlobeData, GlobePlace } from "../lib/worldmap";
import { baseStyle, loadPlaces, mapColors, placeLayers, placesGeoJSON } from "../lib/worldmap";

export interface RouteStop {
  name: string;
  latitude: number;
  longitude: number;
  country_code?: string | null;
  visits?: { name: string }[];
}

const norm = (s: string) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

/** The trip on a map: the route from stop to stop, numbered. Tap a stop (on the map or in the
 *  row above it) to zoom in, and the places worth seeing around it appear. */
export default function RouteMap({ stops }: { stops: RouteStop[] }) {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [data, setData] = useState<GlobeData | null>(null);
  const [sel, setSel] = useState<GlobePlace | null>(null);
  const [focus, setFocus] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);

  // only stops we can place on the map, each with its number in the trip
  const pts = useMemo(() => stops.map((s, i) => ({ ...s, n: i + 1 }))
    .filter((s) => Number.isFinite(s.latitude) && Number.isFinite(s.longitude) && !(s.latitude === 0 && s.longitude === 0)), [stops]);
  const key = pts.map((s) => `${s.latitude.toFixed(3)},${s.longitude.toFixed(3)}`).join("|");

  useEffect(() => { loadPlaces().then(setData).catch(() => setData({ itineraries: [], places: [] })); }, []);

  useEffect(() => {
    const el = box.current;
    if (!el || !data || pts.length === 0) return;
    const c = mapColors();
    const countries = new Set(pts.map((s) => s.country_code?.toUpperCase()).filter(Boolean) as string[]);
    const onTrip = new Set(pts.flatMap((s) => [s.name, ...(s.visits ?? []).map((v) => v.name)]).map(norm));
    // places of this trip always show; the rest of its countries show sooner than on the globe
    const boost = (p: GlobePlace) => (onTrip.has(norm(p.name)) && (!countries.size || countries.has(p.country)) ? 99
      : countries.has(p.country) ? 2 : 0);

    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: el,
        style: baseStyle(c, { globe: false }),
        bounds: bounds(pts),
        fitBoundsOptions: { padding: pad(el), maxZoom: 9 },
        maxZoom: 16,
        cooperativeGestures: true,
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
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const markers: maplibregl.Marker[] = [];
    map.on("load", () => {
      if (el.clientWidth < 600) el.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      map.addSource("route", { type: "geojson", data: {
        type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: pts.map((s) => [s.longitude, s.latitude]) } } });
      map.addLayer({ id: "route-casing", type: "line", source: "route", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": c.halo, "line-width": 6 } });
      map.addLayer({ id: "route", type: "line", source: "route", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": c.ink, "line-width": 2.5, "line-dasharray": [2, 1.6] } });
      map.addSource("places", { type: "geojson", data: placesGeoJSON(data.places, { boost }) });
      for (const l of placeLayers(c)) map.addLayer(l);
      // stops on top: numbered pins, same order as the list below
      const seen = new Map<string, HTMLButtonElement>();
      pts.forEach((s, i) => {
        const at = `${s.latitude.toFixed(3)},${s.longitude.toFixed(3)}`;
        const twin = seen.get(at);
        if (twin) { twin.textContent = `${twin.textContent}·${s.n}`; return; } // back at the same place
        const b = document.createElement("button");
        b.type = "button";
        b.className = "rpin";
        b.textContent = String(s.n);
        b.title = s.name;
        b.setAttribute("aria-label", `Stop ${s.n}: ${s.name}`);
        b.addEventListener("click", (e) => { e.stopPropagation(); zoomStop(i); });
        seen.set(at, b);
        markers.push(new maplibregl.Marker({ element: b }).setLngLat([s.longitude, s.latitude]).addTo(map));
      });
    });

    const layers = ["pl-dot", "pl-name"];
    map.on("click", (e) => {
      const f = map.queryRenderedFeatures([[e.point.x - 8, e.point.y - 8], [e.point.x + 8, e.point.y + 8]], { layers }).at(0);
      setSel(f ? data.places[f.properties.i as number] : null);
    });
    for (const l of layers) {
      map.on("mouseenter", l, () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", l, () => { map.getCanvas().style.cursor = ""; });
    }
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);

    return () => {
      ro.disconnect();
      for (const m of markers) m.remove();
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, key]);

  function zoomStop(i: number) {
    const s = pts[i];
    setFocus(i);
    setSel(null);
    mapRef.current?.flyTo({ center: [s.longitude, s.latitude], zoom: 10.5, speed: 1.3, essential: true });
  }

  function whole() {
    const map = mapRef.current;
    if (!map || !box.current) return;
    setFocus(null);
    setSel(null);
    map.fitBounds(bounds(pts), { padding: pad(box.current), maxZoom: 9 });
  }

  if (failed || pts.length === 0) return null;

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
            <PlaceCard place={sel} planLink={false} onClose={() => setSel(null)}
              onZoom={() => mapRef.current?.flyTo({ center: [sel.lon, sel.lat], zoom: 12, speed: 1.3 })} />
          </div>
        )}
      </div>
      <p className="small muted">Tap a stop to zoom in: the places worth seeing around it appear on the map.</p>
    </div>
  );
}

function bounds(pts: RouteStop[]): maplibregl.LngLatBoundsLike {
  const lons = pts.map((s) => s.longitude), lats = pts.map((s) => s.latitude);
  const [w, e, s, n] = [Math.min(...lons), Math.max(...lons), Math.min(...lats), Math.max(...lats)];
  // one stop only: show its surroundings, not a single point at max zoom
  const padDeg = w === e && s === n ? 0.6 : 0;
  return [[w - padDeg, s - padDeg], [e + padDeg, n + padDeg]];
}

function pad(el: HTMLElement): number {
  return Math.round(Math.min(56, Math.min(el.clientWidth, el.clientHeight) / 6));
}
