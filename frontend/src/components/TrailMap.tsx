import { maplibregl } from "../lib/maplibre";
import { useEffect, useRef, useState } from "react";
import { baseStyle, blockPins, mapColors, phoneGestures, reducedMotion, worldZoom } from "../lib/worldmap";
import { addContours } from "../lib/contours";
import type { TrailPoint } from "../lib/types";

/** One trail on the map: its path, every other footpath around it (so you see the junctions),
 *  and its key points numbered in walking order. Tap a number to zoom in. */
export default function TrailMap({ line, points, focus, onFocus, inset }: {
  line: [number, number][]; points: TrailPoint[]; focus: number | null; onFocus: (i: number | null) => void;
  /** room the floating panels take over the map (the map-first trek page) */
  inset?: { top: number; right: number; bottom: number; left: number };
}) {
  const padding = inset ? { top: inset.top + 36, right: inset.right + 36, bottom: inset.bottom + 36, left: inset.left + 36 } : 36;
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
      const style = baseStyle(c, { globe: true, photo: false }); // the globe like Explore, flat once zoomed in
      // a topographic map, as the trekking sites have: contour lines with their heights...
      addContours(style, "#8A6A45");
      // ...footpaths and tracks, the walking network around the trail (junctions, other ways)...
      style.layers.push({
        id: "paths", type: "line", source: "omt", "source-layer": "transportation", minzoom: 11,
        filter: ["in", ["get", "class"], ["literal", ["path", "track"]]],
        paint: { "line-color": "#6B4E2E", "line-width": ["interpolate", ["linear"], ["zoom"], 11, 0.8, 15, 1.8],
          "line-dasharray": [2, 1.5], "line-opacity": 0.85 },
      }, {
        id: "path-names", type: "symbol", source: "omt", "source-layer": "transportation_name", minzoom: 13,
        filter: ["in", ["get", "class"], ["literal", ["path", "track"]]],
        layout: { "symbol-placement": "line", "text-field": ["coalesce", ["get", "name:en"], ["get", "name"]],
          "text-font": ["Noto Sans Italic"], "text-size": 10.5 },
        paint: { "text-color": "#6B4E2E", "text-halo-color": "#FFFFFF", "text-halo-width": 1.2 },
      }, {
        // ...and the huts, shelters, springs and viewpoints on the way
        id: "trek-pois", type: "symbol", source: "omt", "source-layer": "poi", minzoom: 12,
        filter: ["in", ["get", "subclass"], ["literal", ["alpine_hut", "wilderness_hut", "shelter", "drinking_water", "spring", "viewpoint", "camp_site", "information"]]],
        layout: { "text-field": ["concat", ["match", ["get", "subclass"], "viewpoint", "◉ ", "drinking_water", "◦ ", "spring", "◦ ", "camp_site", "△ ", "■ "],
            ["coalesce", ["get", "name:en"], ["get", "name"], ""]],
          "text-font": ["Noto Sans Regular"], "text-size": 11, "text-anchor": "left", "text-offset": [0.3, 0] },
        paint: { "text-color": c.ink, "text-halo-color": "#FFFFFF", "text-halo-width": 1.4 },
      });
      map = new maplibregl.Map({
        container: el, style, center: mid(coords), zoom: worldZoom(el, inset), renderWorldCopies: false, minZoom: Math.max(0, worldZoom(el) - 1), // never smaller than the globe
        maxZoom: 16, cooperativeGestures: phoneGestures(), attributionControl: { compact: true },
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
      if (inset) el.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
      if (line.length) {
        map.addSource("trail", { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: line } } });
        map.addLayer({ id: "trail-casing", type: "line", source: "trail", layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": c.halo, "line-width": 7 } });
        map.addLayer({ id: "trail", type: "line", source: "trail", layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": "#D2452B", "line-width": 3.5 } });
      }
      blockPins(map, points.map((p) => [p.lon, p.lat]));
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
      // from the globe down onto the trail
      map.fitBounds(bounds(coords), { padding, maxZoom: 14, duration: reducedMotion() ? 0 : 2000, essential: true });
    });
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);
    return () => { ro.disconnect(); for (const m of markers) m.remove(); map.remove(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [line, points]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (focus === null) map.fitBounds(bounds(coords), { padding, maxZoom: 14 });
    else map.flyTo({ center: [points[focus].lon, points[focus].lat], zoom: 14.5, speed: 1.4, essential: true, padding: typeof padding === "number" ? undefined : padding });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus]);

  if (failed) return null;
  return <div className="tmap" ref={box} role="region" aria-label="Map of the trail" />;
}

function mid(cs: [number, number][]): [number, number] {
  const lons = cs.map((c) => c[0]), lats = cs.map((c) => c[1]);
  return [(Math.min(...lons) + Math.max(...lons)) / 2, (Math.min(...lats) + Math.max(...lats)) / 2];
}

function bounds(cs: [number, number][]): maplibregl.LngLatBoundsLike {
  const lons = cs.map((c) => c[0]), lats = cs.map((c) => c[1]);
  return [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]];
}
