import { maplibregl } from "../lib/maplibre";
import { useEffect, useRef, useState } from "react";
import { baseStyle, mapColors } from "../lib/worldmap";
import type { TrailPoint } from "../lib/types";

/** One trail on the map: its path, every other footpath around it (so you see the junctions),
 *  and its key points numbered in walking order. Tap a number to zoom in. */
export default function TrailMap({ line, points, focus, onFocus }: {
  line: [number, number][]; points: TrailPoint[]; focus: number | null; onFocus: (i: number | null) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [failed, setFailed] = useState(false);
  const coords: [number, number][] = [...line, ...points.map((p): [number, number] => [p.lon, p.lat])];

  useEffect(() => {
    const el = box.current;
    if (!el || coords.length === 0) return;
    const c = mapColors();
    let map: maplibregl.Map;
    try {
      const style = baseStyle(c, { globe: false });
      // footpaths and tracks: the walking network around the trail
      style.layers.push({
        id: "paths", type: "line", source: "omt", "source-layer": "transportation", minzoom: 11,
        filter: ["in", ["get", "class"], ["literal", ["path", "track"]]],
        paint: { "line-color": c.line, "line-width": 1, "line-dasharray": [2, 2], "line-opacity": 0.8 },
      });
      map = new maplibregl.Map({
        container: el, style, bounds: bounds(coords),
        fitBoundsOptions: { padding: 36, maxZoom: 14 },
        maxZoom: 16, cooperativeGestures: true, attributionControl: { compact: true },
        pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
      });
    } catch {
      setFailed(true);
      return;
    }
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    const markers: maplibregl.Marker[] = [];
    map.on("load", () => {
      if (line.length) {
        map.addSource("trail", { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: line } } });
        map.addLayer({ id: "trail-casing", type: "line", source: "trail", layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": c.halo, "line-width": 7 } });
        map.addLayer({ id: "trail", type: "line", source: "trail", layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": "#D2452B", "line-width": 3.5 } });
      }
      points.forEach((p, i) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = `rpin tpin ${p.role}`;
        b.textContent = String(i + 1);
        b.title = p.name;
        b.setAttribute("aria-label", `${i + 1}: ${p.name}`);
        b.addEventListener("click", (e) => { e.stopPropagation(); onFocus(i); });
        markers.push(new maplibregl.Marker({ element: b }).setLngLat([p.lon, p.lat]).addTo(map));
      });
    });
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);
    return () => { ro.disconnect(); for (const m of markers) m.remove(); map.remove(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [line, points]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (focus === null) map.fitBounds(bounds(coords), { padding: 36, maxZoom: 14 });
    else map.flyTo({ center: [points[focus].lon, points[focus].lat], zoom: 14.5, speed: 1.4, essential: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus]);

  if (failed) return null;
  return <div className="tmap" ref={box} role="region" aria-label="Map of the trail" />;
}

function bounds(cs: [number, number][]): maplibregl.LngLatBoundsLike {
  const lons = cs.map((c) => c[0]), lats = cs.map((c) => c[1]);
  return [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]];
}
