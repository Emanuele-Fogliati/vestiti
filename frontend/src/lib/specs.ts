import type { Item } from "./types";

export function specRows(item: Item, slot: string): [string, string][] {
  const s = item.specs || {};
  const est = new Set(s.estimated || []);
  const rows: [string, string][] = [];
  if (slot !== "sun_hat" && s.clo !== undefined) rows.push(["Warmth", `${s.clo.toFixed(2)} clo${est.has("clo") || item.source === "owned" ? " (est.)" : ""}`]);
  if (s.waterproof_mm) rows.push(["Waterproof", `${s.waterproof_mm.toLocaleString("en-US")} mm${est.has("waterproof_mm") ? " (est.)" : ""}`]);
  else if (s.waterproof) rows.push(["Waterproof", "yes"]);
  if (s.breathability_g) rows.push(["Breathes", `${s.breathability_g.toLocaleString("en-US")} g/m²`]);
  if (s.insulation) rows.push(["Material", s.insulation.replace("_base", "").replace("synthetic", "synthetic")]);
  if (s.fill_power) rows.push(["Fill", `${s.fill_power} FP`]);
  if (s.footwear_type) rows.push(["Type", s.footwear_type.replace("_", " ") + (s.ankle_support ? ", ankle support" : "")]);
  if (s.weight_g) rows.push(["Weight", `${s.weight_g} g`]);
  if (s.features?.length) rows.push(["Extra", s.features.join(", ")]);
  return rows.slice(0, 5);
}
