import type { PlaceGuide as Guide } from "../lib/types";

function Bulb() {
  return (
    <svg className="bulb" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2.5a6.5 6.5 0 0 0-3.9 11.7c.6.5 1 1.2 1.1 2l.1.8h5.4l.1-.8c.1-.8.5-1.5 1.1-2A6.5 6.5 0 0 0 12 2.5Z" fill="var(--accent)" stroke="var(--ink)" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M9.5 19h5M10.2 21.5h3.6" stroke="var(--ink)" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

/** What the place is, in one line that makes you want to go, and a fun fact with its source. */
export function PlaceGuide({ guide }: { guide?: Guide | null }) {
  if (!guide) return null;
  return (
    <div className="pguide">
      <p className="pg-blurb">{guide.blurb}</p>
      <p className="pg-fact"><Bulb /><span><b>Fun fact</b> {guide.fun_fact}{" "}
        <a className="pg-src" href={guide.source} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}>source</a></span></p>
    </div>
  );
}
