import { useEffect, useState } from "react";

/** A drawing tapped on any map (Manu 2026-11-16: "cliccando su ognuna delle immagini ... una
 *  piccola descrizione sulla destra ... con l'immagine più in grande"): one card for the whole
 *  app, opened from wherever the drawing is. */
export interface ArtOpen { id: string; name: string }

const EV = "artcard:open";
export function openArt(a: ArtOpen): void {
  window.dispatchEvent(new CustomEvent<ArtOpen>(EV, { detail: a }));
}
export function onArt(f: (a: ArtOpen) => void): () => void {
  const h = (e: Event) => f((e as CustomEvent<ArtOpen>).detail);
  window.addEventListener(EV, h);
  return () => window.removeEventListener(EV, h);
}

export interface About { id: string; country: string; shows: string; text: string | null; source: { title: string; url: string } | null }
const cache = new Map<string, Promise<About | null>>();
export function loadAbout(id: string): Promise<About | null> {
  let p = cache.get(id);
  if (!p) {
    p = fetch(`/api/art/landmarks/${encodeURIComponent(id)}/about`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    cache.set(id, p);
  }
  return p;
}
export function useAbout(id: string | null | undefined): About | null | undefined {
  const [a, setA] = useState<About | null | undefined>(undefined);
  useEffect(() => {
    setA(undefined);
    if (!id) return;
    let live = true;
    loadAbout(id).then((x) => { if (live) setA(x); });
    return () => { live = false; };
  }, [id]);
  return a;
}
