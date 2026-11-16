import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { Illustration } from "./Illustration";
import { onArt, useAbout, type ArtOpen } from "../lib/artcard";
import { countryName } from "../lib/worldmap";

/** The small card of a drawing tapped on a map: the drawing bigger, the name, what the place is in
 *  a sentence or two (Wikipedia, credited), or what the drawing shows when Wikipedia has no page. */
export function ArtCard() {
  const [open, setOpen] = useState<ArtOpen | null>(null);
  const loc = useLocation();
  const about = useAbout(open?.id);
  useEffect(() => onArt(setOpen), []);
  useEffect(() => { setOpen(null); }, [loc.pathname]);
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(null); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [open]);
  if (!open) return null;
  return (
    <aside className="artcard" role="dialog" aria-label={open.name} key={open.id}>
      <button type="button" className="mf-x" onClick={() => setOpen(null)} aria-label="Close">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
      </button>
      <div className="artcard-pic"><Illustration art={{ kind: "landmark", id: open.id, label: open.name }} /></div>
      <div className="artcard-in">
        {about && <span className="mf-k">{countryName(about.country)}</span>}
        <h3>{open.name}</h3>
        {about === undefined ? <p className="artcard-t wait"><span /><span /></p>
          : <p className="artcard-t">{about?.text ?? about?.shows}</p>}
        {about?.source && <a className="artcard-src" href={about.source.url} target="_blank" rel="noopener">Wikipedia ↗</a>}
      </div>
    </aside>
  );
}

/** The same sentence inside the cards that already show a place's drawing (the globe's place card,
 *  the "Add as stop" card), so every drawing says what the place is. */
export function AboutLine({ id }: { id: string | null | undefined }) {
  const about = useAbout(id);
  if (!id || !about) return null;
  return (
    <p className="artcard-t about-line">{about.text ?? about.shows}
      {about.source && <> <a className="artcard-src" href={about.source.url} target="_blank" rel="noopener">Wikipedia ↗</a></>}
    </p>
  );
}
