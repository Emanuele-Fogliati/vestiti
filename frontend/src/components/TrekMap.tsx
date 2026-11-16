import { maplibregl } from "../lib/maplibre";
import { useEffect, useRef, useState } from "react";
import { baseStyle, mapColors, phoneGestures, worldZoom } from "../lib/worldmap";
import type { TrailCard } from "../lib/types";

export const LEVEL_COLOR = { easy: "#2F55D4", moderate: "#1D6B37", hard: "#C2541B", technical: "#9B1C1C" } as const;
/** City walks are not a level of difficulty: their own colour (Manu 2026-11-16). */
export const CITY_COLOR = "#7B4FB0";
const LEVELS = ["easy", "moderate", "hard", "technical"] as const;

const NONE = { top: 0, right: 0, bottom: 0, left: 0 };
type Inset = { top: number; right: number; bottom: number; left: number };

/** The Treks page's map: every trek of the list as a dot coloured by how hard it is; the chosen
 *  one larger, ringed. The map frames the list when the filters change, and the chosen trek when
 *  one is picked (beside the panels, never under them). */
export default function TrekMap({ trails, selected, onPick, inset, fitKey, line, onView, around }: {
  trails: TrailCard[]; selected: string | null; onPick: (id: string) => void; inset?: Inset; fitKey: string;
  /** the chosen hike's path ([lon, lat]), drawn as soon as it is picked */
  line?: [number, number][] | null;
  /** what the map shows now: the list follows it (null = the whole globe) */
  onView?: (b: { w: number; s: number; e: number; n: number } | null) => void;
  /** a search by zone: the map frames this circle, not every match of the words */
  around?: { lat: number; lon: number; km: number } | null;
}) {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  const waiting = useRef<(() => void)[]>([]);
  const when = (f: () => void) => { if (ready.current) f(); else waiting.current.push(f); };
  const [failed, setFailed] = useState(false);
  const cb = useRef({ onPick, inset, onView, around });
  cb.current = { onPick, inset, onView, around };
  const pts = trails.filter((t) => t.lat != null && t.lon != null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: el, style: baseStyle(mapColors(), { globe: true, photo: false }), center: [10, 30], zoom: worldZoom(el), renderWorldCopies: false, minZoom: Math.max(0, worldZoom(el) - 1), // never smaller than the globe
        maxZoom: 15, cooperativeGestures: phoneGestures(), attributionControl: { compact: true },
        pixelRatio: Math.min(window.devicePixelRatio || 1, 2), fadeDuration: 150,
      });
    } catch { setFailed(true); return; }
    mapRef.current = map;
    if (new URLSearchParams(location.search).has("mapdebug")) (window as unknown as { __map: unknown }).__map = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      el.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show"); // the "i" opens it
      map.addSource("route", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "route-casing", type: "line", source: "route", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#FFFFFF", "line-width": 7 } });
      map.addLayer({ id: "route-line", type: "line", source: "route", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#D2452B", "line-width": 3.5 } });
      map.addSource("treks", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "trek-dot", type: "circle", source: "treks", layout: { "circle-sort-key": ["get", "s"] }, paint: {
        "circle-color": ["case", ["==", ["get", "c"], 1], CITY_COLOR,
          ["match", ["get", "d"], 0, LEVEL_COLOR.easy, 1, LEVEL_COLOR.moderate, 2, LEVEL_COLOR.hard, LEVEL_COLOR.technical]],
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, ["case", ["==", ["get", "s"], 1], 8, 3.2],
          6, ["case", ["==", ["get", "s"], 1], 9, 5], 10, ["case", ["==", ["get", "s"], 1], 11, 7]],
        "circle-stroke-color": "#FFFFFF",
        "circle-stroke-width": ["case", ["==", ["get", "s"], 1], 3, 1.2],
      } });
      map.addLayer({ id: "trek-name", type: "symbol", source: "treks", minzoom: 7,
        layout: { "text-field": ["get", "n"], "text-font": ["Noto Sans Regular"], "text-size": 11.5, "text-anchor": "left",
          "text-offset": [0.9, 0], "text-optional": true },
        paint: { "text-color": "#1F201D", "text-halo-color": "#FFFFFF", "text-halo-width": 1.4 } });
      map.on("click", "trek-dot", (e) => {
        const f = e.features?.[0];
        if (f) cb.current.onPick(String(f.properties.id));
      });
      map.on("mouseenter", "trek-dot", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "trek-dot", () => { map.getCanvas().style.cursor = ""; });
      // the list on the left shows the hikes in view; on the whole globe, all of them
      const view = () => {
        if (map.getZoom() < worldZoom(el, cb.current.inset) + 1.2) { cb.current.onView?.(null); return; }
        const b = map.getBounds();
        cb.current.onView?.({ w: b.getWest(), s: b.getSouth(), e: b.getEast(), n: b.getNorth() });
      };
      map.on("moveend", view);
      ready.current = true;
      for (const f of waiting.current.splice(0)) f();
    });
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);
    return () => { ro.disconnect(); ready.current = false; map.remove(); mapRef.current = null; };
  }, []);

  // the chosen hike's path: drawn at once, and the map frames it
  useEffect(() => {
    when(() => {
      const map = mapRef.current;
      if (!map) return;
      const src = map.getSource("route") as maplibregl.GeoJSONSource | undefined;
      const ok = !!line && line.length > 1;
      src?.setData(ok ? { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: line! } } : { type: "FeatureCollection", features: [] });
      if (!ok) return;
      const lons = line!.map((c) => c[0]), lats = line!.map((c) => c[1]);
      // a padding left by flyTo would add to the one fitBounds is given
      map.setPadding(NONE).fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
        { padding: room(box.current!, cb.current.inset), maxZoom: 14, duration: 800 });
    });
  }, [line]); // eslint-disable-line react-hooks/exhaustive-deps

  // the dots
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const put = () => {
      const src = map.getSource("treks") as maplibregl.GeoJSONSource | undefined;
      src?.setData({ type: "FeatureCollection", features: pts.map((t) => ({ type: "Feature", properties: {
        id: t.id, n: t.name, d: LEVELS.indexOf(t.difficulty), c: t.style === "city" ? 1 : 0, s: t.id === selected ? 1 : 0 },
        geometry: { type: "Point", coordinates: [t.lon!, t.lat!] } })) });
    };
    when(put);
  }, [trails, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  // frame the list, or the chosen trek
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const go = () => {
      const el = box.current!;
      const p = room(el, cb.current.inset);
      const t = selected ? pts.find((x) => x.id === selected) : null;
      if (t) { map.flyTo({ center: [t.lon!, t.lat!], zoom: Math.max(map.getZoom(), 9), padding: p, speed: 1.4, essential: true }); return; }
      const a = cb.current.around;
      if (a) {
        const dl = a.km / 111, dn = a.km / (111 * Math.max(0.2, Math.cos(a.lat * Math.PI / 180)));
        map.setPadding(NONE).fitBounds([[a.lon - dn, a.lat - dl], [a.lon + dn, a.lat + dl]], { padding: p, maxZoom: 12, duration: 800 });
        return;
      }
      if (!pts.length) return;
      const lons = pts.map((x) => x.lon!), lats = pts.map((x) => x.lat!);
      // the whole world's treks: no box can frame that well; a plain world view instead
      if (Math.max(...lons) - Math.min(...lons) > 200) { map.easeTo({ center: [15, 25], zoom: worldZoom(el, cb.current.inset), padding: p, duration: 600 }); return; }
      map.setPadding(NONE).fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: p, maxZoom: 10, duration: 700 });
    };
    when(go);
  }, [fitKey, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  if (failed) return null;
  return <div className="rmap rmap-bare"><div className="rmap-map" ref={box} role="region" aria-label="Map of the walks" /></div>;
}

function room(el: HTMLElement, inset?: Inset) {
  const p = Math.round(Math.min(48, Math.min(el.clientWidth, el.clientHeight) / 8));
  if (!inset) return { top: p, right: p, bottom: p, left: p };
  const left = Math.min(inset.left, Math.max(0, el.clientWidth - 160 - inset.right));
  return { top: inset.top + p, right: inset.right + p, bottom: inset.bottom + p, left: left + p };
}
