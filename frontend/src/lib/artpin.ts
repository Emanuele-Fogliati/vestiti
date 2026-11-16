import { loadLandmark } from "./landmarks";
import type { StopArt } from "./types";

/** A stop on a map as its own drawing (Manu 2026-11-16: "al posto dei pallini neri mettici
 *  direttamente l'immaginina"), with its number in the corner. Null when the stop has no drawing:
 *  the map keeps its plain numbered pin there. */
export function artPin(art: StopArt | null | undefined, n: number | null, name: string): HTMLButtonElement | null {
  if (art?.kind !== "landmark") return null;
  const b = document.createElement("button");
  b.type = "button";
  b.className = "apin wait";
  b.title = name;
  b.setAttribute("aria-label", n ? `Stop ${n}: ${name}` : name);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 300 200");
  svg.setAttribute("preserveAspectRatio", "xMidYMid slice");
  svg.setAttribute("aria-hidden", "true");
  b.appendChild(svg);
  if (n) {
    const k = document.createElement("b");
    k.textContent = String(n);
    b.appendChild(k);
  }
  loadLandmark(art.id).then((s) => {
    if (s) svg.innerHTML = s;
    b.classList.remove("wait");
    b.classList.toggle("none", !s);
  });
  return b;
}
