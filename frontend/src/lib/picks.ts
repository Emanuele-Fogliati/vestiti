// The places you pick on the globe for your own trip: whole cities ("Florence") and single
// sights inside them ("Uffizi Gallery"). Kept in this browser only, so a pick survives a reload.
import { useSyncExternalStore } from "react";

const KEY = "thruwear.picks";
const MAX = 60; // the API takes up to 60 places

function read(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x) => typeof x === "string").slice(0, MAX) : [];
  } catch {
    return [];
  }
}

let picks: string[] = read();
const subs = new Set<() => void>();

function set(next: string[]) {
  picks = next.slice(0, MAX);
  try { localStorage.setItem(KEY, JSON.stringify(picks)); } catch { /* private mode: memory only */ }
  subs.forEach((f) => f());
}

export const pickStore = {
  get: () => picks,
  has: (id: string) => picks.includes(id),
  toggle: (id: string) => set(picks.includes(id) ? picks.filter((x) => x !== id) : [...picks, id]),
  remove: (ids: string[]) => set(picks.filter((x) => !ids.includes(x))),
  clear: () => set([]),
  subscribe: (f: () => void) => { subs.add(f); return () => { subs.delete(f); }; },
};

export function usePicks(): string[] {
  return useSyncExternalStore(pickStore.subscribe, pickStore.get, pickStore.get);
}

export interface PickedStop {
  /** The city or town you sleep in (or a place on its own: Machu Picchu). */
  id: string;
  /** Picked as a whole: "Florence" rather than only its sights. */
  whole: boolean;
  /** Sights picked inside it, in the order picked. */
  inside: string[];
}

/** Picks grouped as the trip's stops: a sight goes under the city it is in, cities keep the
 *  order of the first pick. Same rule as the server (app.globe.trip_stops). */
export function groupPicks(ids: string[], parentOf: (id: string) => string | null | undefined): PickedStop[] {
  const out: PickedStop[] = [];
  const at = new Map<string, PickedStop>();
  for (const id of ids) {
    const root = parentOf(id) ?? id;
    let s = at.get(root);
    if (!s) { s = { id: root, whole: false, inside: [] }; at.set(root, s); out.push(s); }
    if (root === id) s.whole = true; else if (!s.inside.includes(id)) s.inside.push(id);
  }
  return out;
}
