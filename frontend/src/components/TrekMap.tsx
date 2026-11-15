import { maplibregl } from "../lib/maplibre";
import { useEffect, useRef, useState } from "react";
import { baseStyle, mapColors } from "../lib/worldmap";
import type { TrailCard } from "../lib/types";

export const LEVEL_COLOR = { easy: "#2F55D4", moderate: "#1D6B37", hard: "#C2541B", technical: "#9B1C1C" } as const;
const LEVELS = ["easy", "moderate", "hard", "technical"] as const;

type Inset = { top: number; right: number; bottom: number; left: number };

/** The Treks page's map: every trek of the list as a dot coloured by how hard it is; the chosen
 *  one larger, ringed. The map frames the list when the filters change, and the chosen trek when
 *  one is picked (beside the panels, never under them). */
export default function TrekMap({ trails, selected, onPick, inset, fitKey }: {
  trails: TrailCard[]; selected: string | null; onPick: (id: string) => void; inset?: Inset; fitKey: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  const waiting = useRef<(() => void)[]>([]);
  const when = (f: () => void) => { if (ready.current) f(); else waiting.current.push(f); };
  const [failed, setFailed] = useState(false);
  const cb = useRef({ onPick, inset });
  cb.current = { onPick, inset };
  const pts = trails.filter((t) => t.lat != null && t.lon != null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: el, style: baseStyle(mapColors(), { globe: false }), center: [10, 30], zoom: 1.4,
        maxZoom: 15, cooperativeGestures: true, attributionControl: { compact: true },
        pixelRatio: Math.min(window.devicePixelRatio || 1, 2), fadeDuration: 150,
      });
    } catch { setFailed(true); return; }
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      el.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show"); // the "i" opens it
      map.addSource("treks", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "trek-dot", type: "circle", source: "treks", layout: { "circle-sort-key": ["get", "s"] }, paint: {
        "circle-color": ["match", ["get", "d"], 0, LEVEL_COLOR.easy, 1, LEVEL_COLOR.moderate, 2, LEVEL_COLOR.hard, LEVEL_COLOR.technical],
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
      ready.current = true;
      for (const f of waiting.current.splice(0)) f();
    });
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);
    return () => { ro.disconnect(); ready.current = false; map.remove(); mapRef.current = null; };
  }, []);

  // the dots
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const put = () => {
      const src = map.getSource("treks") as maplibregl.GeoJSONSource | undefined;
      src?.setData({ type: "FeatureCollection", features: pts.map((t) => ({ type: "Feature", properties: {
        id: t.id, n: t.name, d: LEVELS.indexOf(t.difficulty), s: t.id === selected ? 1 : 0 },
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
      if (!pts.length) return;
      const lons = pts.map((x) => x.lon!), lats = pts.map((x) => x.lat!);
      // the whole world's treks: no box can frame that well; a plain world view instead
      if (Math.max(...lons) - Math.min(...lons) > 200) { map.easeTo({ center: [0, 25], zoom: 1.2, padding: p, duration: 600 }); return; }
      map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: p, maxZoom: 10, duration: 700 });
    };
    when(go);
  }, [fitKey, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  if (failed) return null;
  return <div className="rmap rmap-bare"><div className="rmap-map" ref={box} role="region" aria-label="Map of the treks" /></div>;
}

function room(el: HTMLElement, inset?: Inset) {
  const p = Math.round(Math.min(48, Math.min(el.clientWidth, el.clientHeight) / 8));
  if (!inset) return { top: p, right: p, bottom: p, left: p };
  const left = Math.min(inset.left, Math.max(0, el.clientWidth - 160 - inset.right));
  return { top: inset.top + p, right: inset.right + p, bottom: inset.bottom + p, left: left + p };
}
