/* Getting from one stop to the next, as the board guesses it (backend app/travel guess()):
   same area, by road, by road or flight, flight; and how long. Every arrival day carries
   its travel, so a plan never forgets the time on the road (Manu, 2026-11-13). */

export type LegGuess = "local" | "road" | "road_or_flight" | "flight";
export interface Leg { guess: LegGuess; km: number | null; hours: number | null; border: boolean }
interface At { lat: number; lon: number; country?: string | null }

const ROAD_KMH = 60; // buses in Patagonia and the Andes, stops and borders included
const ROAD_FACTOR = 1.3; // roads are longer than the straight line
/** From this many hours on the road, the arrival is a travel day: nothing else planned. */
export const TRAVEL_DAY_H = 6;

export function km(a: At, b: At): number {
  const r = Math.PI / 180;
  const p1 = a.lat * r, p2 = b.lat * r;
  const h = Math.sin((p2 - p1) / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(((b.lon - a.lon) * r) / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(Math.min(1, h)));
}

/** How you probably go from a to b. null for a is home: a flight. */
export function guessLeg(a: At | null, b: At): Leg {
  if (!a) return { guess: "flight", km: null, hours: null, border: false };
  const d = km(a, b);
  const border = !!(a.country && b.country && a.country !== b.country);
  if (d <= 15) return { guess: "local", km: Math.round(d), hours: null, border };
  const h = Math.round(((d * ROAD_FACTOR) / ROAD_KMH + (border ? 1 : 0)) * 10) / 10;
  if (d <= 450) return { guess: "road", km: Math.round(d), hours: h, border };
  if (d <= 800) return { guess: "road_or_flight", km: Math.round(d), hours: h, border };
  return { guess: "flight", km: Math.round(d), hours: null, border };
}

const hrs = (h: number) => (h < 1 ? "under 1 h" : `≈ ${Math.round(h)} h`);

/** "Bus ≈ 4 h", "Bus ≈ 9 h or a flight", "Flight", "" when it is close by. */
export function legText(l: Pick<Leg, "guess" | "hours" | "border">): string {
  if (l.guess === "local") return "";
  if (l.guess === "flight" || !l.hours) return "Flight";
  const b = l.border ? " · border" : "";
  return l.guess === "road_or_flight" ? `Bus ${hrs(l.hours)}${b}, or a flight` : `Bus ${hrs(l.hours)}${b}`;
}

/** The leg takes the whole arrival day (a long road), half of it (a flight, 3 h or more), or little. */
export function legWeight(l: Pick<Leg, "guess" | "hours">, mode?: string): "full" | "half" | "light" {
  if (l.guess === "local") return "light";
  if (mode === "flight" || l.guess === "flight" || !l.hours) return "half";
  if (l.hours >= TRAVEL_DAY_H) return "full";
  return l.hours >= 3 ? "half" : "light";
}

const BY: Record<string, string> = { bus: "Bus", car: "Car", train: "Train", boat: "Boat", other: "Transfer" };

/** The way into a stop as the board has it (the traveller's mode, else the guess):
 * "Bus from Puno ≈ 9 h · travel day", "Flight from El Calafate", "" when close by. */
export function arrivalText(l: { mode: string; guess: LegGuess; hours: number | null; from_name: string; booked?: boolean; border?: boolean }): { text: string; full: boolean } {
  if (l.mode === "local" || (l.guess === "local" && l.mode !== "flight")) return { text: "", full: false };
  const from = l.from_name === "Home" ? "from home" : `from ${l.from_name}`;
  if (l.mode === "flight") return { text: `Flight ${from}${l.booked ? " · booked" : ""}`, full: false };
  const full = legWeight(l, l.mode) === "full";
  const h = l.hours ? ` ${hrs(l.hours)}` : "";
  const or = l.guess === "road_or_flight" && !l.booked ? " (or fly)" : "";
  return { text: `${BY[l.mode] ?? "Transfer"} ${from}${h}${or}${l.booked ? " · booked" : ""}${full ? " · travel day" : ""}`, full };
}
