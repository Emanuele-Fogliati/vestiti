import { useEffect, useMemo, useRef } from "react";
import { reducedMotion } from "../lib/worldmap";
import type { StopArt } from "../lib/types";
import { Illustration, useLandmark } from "./Illustration";

const MAX_LAYERS = 7;

/** A landmark drawing as a paper-cut diorama (prototype motion 1, Manu 2026-11-15): the scene's
 *  layers fly in apart in 3D, then settle into the flat picture; drag to tilt it.
 *  Each layer is the same SVG frame holding a slice of the drawing's shapes, back to front,
 *  so at rest it looks exactly like the plain drawing. No drawing: nothing, like Illustration. */
export function Diorama({ art, label }: { art?: StopArt | null; label?: string }) {
  const id = art?.kind === "landmark" ? art.id : undefined;
  const svg = useLandmark(id);
  const layers = useMemo(() => (svg ? split(svg) : null), [svg]);
  const stage = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const st = stage.current;
    if (!st || !layers || reducedMotion()) return;
    const ls = [...st.children] as HTMLElement[];
    const ease = "cubic-bezier(.2,.8,.2,1)";
    st.animate([
      { transform: "rotateX(50deg) rotateZ(-12deg) scale(.82)" },
      { transform: "rotateX(50deg) rotateZ(-12deg) scale(.82)", offset: 0.45 },
      { transform: "rotateX(0) rotateZ(0) scale(1)" },
    ], { duration: 2200, easing: ease, fill: "backwards" });
    ls.forEach((l, i) => l.animate([
      { transform: `translateZ(${i * 36 + 60}px)`, opacity: 0 },
      { transform: `translateZ(${i * 36}px)`, opacity: 1, offset: 0.35 },
      { transform: `translateZ(${i * 36}px)`, offset: 0.5 },
      { transform: `translateZ(${i * 1.5}px)`, opacity: 1 },
    ], { duration: 2200, delay: i * 70, easing: ease, fill: "backwards" }));
  }, [layers]);

  if (!id) return null;
  if (!layers) return <Illustration art={art} label={label} />;

  // drag (or move the mouse) to tilt the paper layers
  function tilt(e: React.PointerEvent) {
    const r = box.current!.getBoundingClientRect(), st = stage.current!;
    const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
    st.style.transform = `rotateX(${(-y * 22).toFixed(1)}deg) rotateY(${(x * 28).toFixed(1)}deg)`;
    [...st.children].forEach((l, i) => { (l as HTMLElement).style.transform = `translateZ(${i * 10}px)`; });
  }
  function rest() {
    const st = stage.current!;
    st.style.transform = "";
    [...st.children].forEach((l, i) => { (l as HTMLElement).style.transform = `translateZ(${i * 1.5}px)`; });
  }

  return (
    <figure className="dio" ref={box} onPointerMove={tilt} onPointerLeave={rest} role="img" aria-label={label ?? art?.label}>
      <div className="dio-stage" ref={stage}>
        {layers.map((html, i) => (
          <svg key={i} className="dio-l" viewBox="0 0 300 200" preserveAspectRatio="xMidYMid slice" aria-hidden="true"
            style={{ transform: `translateZ(${i * 1.5}px)` }} dangerouslySetInnerHTML={{ __html: html }} />
        ))}
      </div>
      <figcaption className="dio-hint">Move over the drawing to tilt it</figcaption>
    </figure>
  );
}

/** The drawing's shapes in up to MAX_LAYERS slices, back to front, each with the drawing's defs and colours. */
function split(svg: string): string[] | null {
  try {
    const doc = new DOMParser().parseFromString(`<svg xmlns="http://www.w3.org/2000/svg">${svg}</svg>`, "image/svg+xml");
    const root = doc.documentElement;
    const defs = root.querySelector("defs");
    const g = [...root.children].find((c) => c.tagName === "g");
    if (!g || g.children.length < 2) return null;
    const kids = [...g.children].map((c) => c.outerHTML);
    const n = Math.min(MAX_LAYERS, kids.length);
    const per = Math.ceil(kids.length / n);
    const style = (g.getAttribute("style") ?? "").replace(/"/g, "&quot;");
    const d = defs ? defs.outerHTML : "";
    const out: string[] = [];
    for (let i = 0; i < kids.length; i += per) out.push(`${d}<g style="${style}">${kids.slice(i, i + per).join("")}</g>`);
    return out;
  } catch {
    return null;
  }
}
