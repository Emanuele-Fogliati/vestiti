import type { HourStep } from "../lib/types";

/** A day as a good local guide runs it, hour by hour, and what tour programmes leave out
 * (Manu, 2026-11-12: "quasi ora per ora ... con tutti i fuori programma"). Folded: one click
 * opens it, so the plan stays short. */
export default function HourByHour({ steps, extras, book, label = "Hour by hour" }: {
  steps?: HourStep[]; extras?: string[]; book?: string; label?: string;
}) {
  if (!steps?.length && !extras?.length) return null;
  return (
    <details className="hours">
      <summary>{label}</summary>
      <div className="hours-body">
        {!!steps?.length && (
          <ol className="hours-steps">
            {steps.map((x, i) => (
              <li key={i}>
                <time>{x.at}</time>
                <span><b>{x.what}</b>{x.note && <span className="hours-note">{x.note}</span>}</span>
              </li>
            ))}
          </ol>
        )}
        {(book || !!extras?.length) && (
          <aside className="hours-side">
            {book && <p className="hours-book"><b>Book</b>{book}</p>}
            {!!extras?.length && (
              <div className="hours-extras">
                <b>Off the programme</b>
                <ul>{extras.map((e, i) => <li key={i}>{e}</li>)}</ul>
              </div>
            )}
          </aside>
        )}
      </div>
    </details>
  );
}
