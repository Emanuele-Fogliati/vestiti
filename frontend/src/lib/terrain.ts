import type { Stop } from "./types";

export type Terrain = "alpine" | "hills" | "glacier" | "coast" | "city" | "snow" | "desert" | "savanna";

/** Pick an illustration for a stop from what we know: activities, altitude, latitude. */
export function terrainFor(stop: Pick<Stop, "activities" | "elevation_m" | "latitude">, seed = 0): Terrain {
  const types = stop.activities.map((a) => a.type);
  const top = Math.max(stop.elevation_m || 0, ...stop.activities.map((a) => a.max_altitude_m || 0));
  const lat = Math.abs(stop.latitude);
  if (types.includes("ski")) return "snow";
  if (types.includes("safari")) return "savanna";
  if (types.includes("desert")) return "desert";
  if (types.includes("beach") || types.includes("boat")) return "coast";
  if (types.some((t) => t === "hiking" || t === "trek_multiday" || t === "unknown")) {
    if (top >= 2500) return lat > 45 ? "glacier" : "alpine";
    return top >= 1200 ? "alpine" : "hills";
  }
  if (lat < 32 && lat > 15 && (stop.elevation_m || 0) > 300) return "desert";
  if ((stop.elevation_m || 0) > 1000) return "alpine";
  return seed % 7 === 3 ? "coast" : "city";
}
