import { maplibregl } from "../lib/maplibre";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { artPin } from "../lib/artpin";
import type { StopArt } from "../lib/types";
import { baseStyle, mapColors, phoneGestures, worldZoom } from "../lib/worldmap";

type Inset = { top: number; right: number; bottom: number; left: number };
/** arts/names: the stops' drawings, shown on the map for the chosen trip in place of its dots */
export interface MapTrip { id: string; points: number[][]; arts?: (StopArt | null)[]; names?: string[] }

/** Trips on one map: every trip as its stops joined along the roads (Manu 2026-11-16: never a
 *  straight line), thin and grey; the chosen trip in ink, on top, and the map frames it beside the
 *  panels. With none chosen it frames them all. */
export default function TripsMap({ trips, selected, onPick, inset }: {
  trips: MapTrip[]; selected: string | null; onPick: (id: string) => void; inset?: Inset;
}) {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  const waiting = useRef<(() => void)[]>([]);
  const when = (f: () => void) => { if (ready.current) f(); else waiting.current.push(f); };
  const [failed, setFailed] = useState(false);
  const pins = useRef<maplibregl.Marker[]>([]);
  const cb = useRef({ onPick, inset });
  cb.current = { onPick, inset };
  const shown = trips.filter((t) => t.points.length > 0);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: el, style: baseStyle(mapColors(), { globe: true, photo: false }), center: [0, 20], zoom: worldZoom(el), renderWorldCopies: false, minZoom: Math.max(0, worldZoom(el) - 1), // never smaller than the globe
        maxZoom: 14, cooperativeGestures: phoneGestures(), attributionControl: { compact: true },
        pixelRatio: Math.min(window.devicePixelRatio || 1, 2), fadeDuration: 150,
      });
    } catch { setFailed(true); return; }
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      el.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      map.addSource("trips", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "trip-line", type: "line", source: "trips", filter: ["==", ["geometry-type"], "LineString"],
        layout: { "line-join": "round", "line-cap": "round", "line-sort-key": ["get", "s"] },
        paint: { "line-color": ["case", ["==", ["get", "s"], 1], "#1F201D", "#7C7C78"],
          "line-width": ["case", ["==", ["get", "s"], 1], 3, 1.6], "line-opacity": ["case", ["==", ["get", "s"], 1], 1, 0.55] } });
      map.addLayer({ id: "trip-stop", type: "circle", source: "trips", filter: ["all", ["==", ["geometry-type"], "Point"], ["!=", ["get", "a"], 1]],
        layout: { "circle-sort-key": ["get", "s"] },
        paint: { "circle-color": ["case", ["==", ["get", "s"], 1], "#1F201D", "#7C7C78"],
          "circle-radius": ["case", ["==", ["get", "s"], 1], 6, 3.5],
          "circle-stroke-color": "#FFFFFF", "circle-stroke-width": ["case", ["==", ["get", "s"], 1], 2.5, 1.2] } });
      for (const l of ["trip-line", "trip-stop"]) {
        map.on("click", l, (e) => { const f = e.features?.[0]; if (f) cb.current.onPick(String(f.properties.id)); });
        map.on("mouseenter", l, () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", l, () => { map.getCanvas().style.cursor = ""; });
      }
      ready.current = true;
      for (const f of waiting.current.splice(0)) f();
    });
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);
    return () => { ro.disconnect(); ready.current = false; map.remove(); mapRef.current = null; };
  }, []);

  const key = shown.map((t) => `${t.id}:${t.points.map((p) => p.join(",")).join(";")}`).join("|");
  // each trip's legs along the roads, asked once per trip (the server keeps them)
  const [roads, setRoads] = useState<Record<string, number[][][]>>({});
  const asked = useRef(new Set<string>());
  useEffect(() => {
    for (const t of shown) {
      const k = `${t.id}:${t.points.map((p) => p.join(",")).join(";")}`;
      if (t.points.length < 2 || t.points.length > 40 || asked.current.has(k)) continue;
      asked.current.add(k);
      api.roads(t.points.map(([la, lo]) => [la, lo])).then(({ legs }) => setRoads((r) => ({ ...r, [k]: legs.map((l) => l.line) })))
        .catch(() => undefined);
    }
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const roadKey = Object.keys(roads).join("|");
  const framed = useRef("");
  useEffect(() => {
    when(() => {
      const map = mapRef.current;
      if (!map) return;
      const feats = shown.flatMap((t) => {
        const s = t.id === selected ? 1 : 0;
        const coords = t.points.map(([la, lo]) => [lo, la]);
        const way = roads[`${t.id}:${t.points.map((p) => p.join(",")).join(";")}`] ?? (coords.length > 1 ? [coords] : []);
        return [
          ...way.map((line) => ({ type: "Feature" as const, properties: { id: t.id, s }, geometry: { type: "LineString" as const, coordinates: line } })),
          ...coords.map((c, i) => ({ type: "Feature" as const, properties: { id: t.id, s, a: s && t.arts?.[i] ? 1 : 0 },
            geometry: { type: "Point" as const, coordinates: c } })),
        ];
      });
      // the chosen trip's stops as their drawings, numbered, over the road
      for (const m of pins.current.splice(0)) m.remove();
      const chosen = shown.find((t) => t.id === selected);
      const seen = new Set<string>();
      chosen?.points.forEach(([la, lo], i) => {
        const at = `${la.toFixed(2)},${lo.toFixed(2)}`;
        if (seen.has(at)) return; // back where it started
        seen.add(at);
        const el = artPin(chosen.arts?.[i], i + 1, chosen.names?.[i] ?? "");
        if (el) pins.current.push(new maplibregl.Marker({ element: el }).setLngLat([lo, la]).addTo(map));
      });
      (map.getSource("trips") as maplibregl.GeoJSONSource | undefined)?.setData({ type: "FeatureCollection", features: feats });
      if (framed.current === `${key}#${selected}`) return; // the roads came in: the frame stays
      framed.current = `${key}#${selected}`;
      const pick = selected ? shown.filter((t) => t.id === selected) : shown;
      const pts = pick.flatMap((t) => t.points);
      if (!pts.length) return;
      const lats = pts.map((p) => p[0]), lons = pts.map((p) => p[1]);
      const pad = room(box.current!, cb.current.inset);
      const one = Math.max(...lats) - Math.min(...lats) < 0.2 && Math.max(...lons) - Math.min(...lons) < 0.2;
      const d = one ? 0.5 : 0;
      map.fitBounds([[Math.min(...lons) - d, Math.min(...lats) - d], [Math.max(...lons) + d, Math.max(...lats) + d]],
        { padding: pad, maxZoom: 9, duration: 700 });
    });
  }, [key, selected, roadKey]); // eslint-disable-line react-hooks/exhaustive-deps

  if (failed) return null;
  return <div className="rmap rmap-bare"><div className="rmap-map" ref={box} role="region" aria-label="Map of your trips" /></div>;
}

function room(el: HTMLElement, inset?: Inset) {
  const p = Math.round(Math.min(48, Math.min(el.clientWidth, el.clientHeight) / 8));
  if (!inset) return { top: p, right: p, bottom: p, left: p };
  const left = Math.min(inset.left, Math.max(0, el.clientWidth - 160 - inset.right));
  return { top: inset.top + p, right: inset.right + p, bottom: inset.bottom + p, left: left + p };
}
