import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { Illustration } from "./Illustration";
import { onArt, useAbout, useGuide, type ArtOpen, type PlaceText } from "../lib/artcard";
import { countryName } from "../lib/worldmap";

/** The small card of a drawing tapped on a map: the drawing bigger, the name, what the place is in
 *  a sentence or two (Wikipedia, credited), or what the drawing shows when Wikipedia has no page. */
export function ArtCard() {
  const [open, setOpen] = useState<ArtOpen | null>(null);
  const loc = useLocation();
  const about = useAbout(open?.id);
  const guide = useGuide(open?.name, about?.country);
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
        {about === undefined || (about && guide === undefined) ? <p className="artcard-t wait"><span /><span /></p>
          : guide ? <GuideText g={guide} />
          : <p className="artcard-t">{about?.text ?? about?.shows}</p>}
        {!guide && about?.source && <a className="artcard-src" href={about.source.url} target="_blank" rel="noopener">Wikipedia ↗</a>}
      </div>
    </aside>
  );
}

/** The place's own text: what it is in a line, and a fun fact with its source. */
function GuideText({ g, cls = "" }: { g: PlaceText; cls?: string }) {
  return (
    <>
      <p className={`artcard-t ${cls}`}>{g.blurb}</p>
      <p className={`artcard-t artcard-fact ${cls}`}><b>Fun fact</b> {g.fun_fact}{" "}
        <a className="artcard-src" href={g.source} target="_blank" rel="noopener noreferrer">source</a></p>
    </>
  );
}

/** The same text inside the cards that show a place (the globe's place card, the "Add as stop"
 *  card): the place's own description and fun fact when we have written one, otherwise what its
 *  drawing is, from Wikipedia. */
export function AboutLine({ id, name, country }: { id: string | null | undefined; name?: string; country?: string }) {
  const guide = useGuide(name, country);
  const about = useAbout(guide ? null : id);
  if (guide) return <GuideText g={guide} cls="about-line" />;
  if (!id || !about) return null;
  return (
    <p className="artcard-t about-line">{about.text ?? about.shows}
      {about.source && <> <a className="artcard-src" href={about.source.url} target="_blank" rel="noopener">Wikipedia ↗</a></>}
    </p>
  );
}
