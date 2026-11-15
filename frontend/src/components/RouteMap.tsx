import { maplibregl } from "../lib/maplibre";
import { api } from "../lib/api";
import { useEffect, useMemo, useRef, useState } from "react";
import { PlaceCard } from "./PlaceCard";
import type { GlobeData, GlobePlace } from "../lib/worldmap";
import { baseStyle, loadPlaces, mapColors, placeLayers, placesGeoJSON, reducedMotion } from "../lib/worldmap";

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
export default function RouteMap({ stops, focusIndex }: { stops: RouteStop[]; focusIndex?: number | null }) {
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
      const straight: LineFeature[] = [{ type: "Feature", properties: { air: 0 }, geometry: { type: "LineString", coordinates: pts.map((s) => [s.longitude, s.latitude]) } }];
      map.addSource("route", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "route-casing", type: "line", source: "route", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": c.halo, "line-width": 6 } });
      map.addLayer({ id: "route", type: "line", source: "route", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": c.ink, "line-width": 2.5, "line-dasharray": [2, 1.6] } });
      // then the real way (Manu, 2026-11-14): along the roads like Google Maps, flights as arcs
      if (pts.length > 1 && pts.length <= 40) {
        api.roads(pts.map((s) => [s.latitude, s.longitude])).then(({ legs }) => {
          if (!map.getSource("route")) return;
          const feats = legs.map((l) => ({ type: "Feature" as const, properties: { air: l.mode === "air" ? 1 : 0 },
            geometry: { type: "LineString" as const, coordinates: l.line } }));
          drawIn(map.getSource("route") as maplibregl.GeoJSONSource, feats);
          map.setPaintProperty("route", "line-dasharray", ["case", ["==", ["get", "air"], 1], ["literal", [2, 1.6]], ["literal", [1, 0]]]);
          map.setPaintProperty("route", "line-width", ["case", ["==", ["get", "air"], 1], 2, 3.2]);
        }).catch(() => { if (map.getSource("route")) drawIn(map.getSource("route") as maplibregl.GeoJSONSource, straight); }); // straight lines then
      } else drawIn(map.getSource("route") as maplibregl.GeoJSONSource, straight);
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
        b.style.setProperty("--d", `${300 + i * 160}ms`); // pins pop up in order while the line reaches them
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

  // the trip page's timeline drives the map: a stop opened there flies the map to it
  useEffect(() => {
    if (focusIndex === undefined || !mapRef.current) return;
    const i = focusIndex === null ? -1 : pts.findIndex((p) => p.n === focusIndex + 1);
    if (i < 0) whole(); else zoomStop(i);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusIndex]);

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
            <PlaceCard place={sel} onClose={() => setSel(null)}
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
