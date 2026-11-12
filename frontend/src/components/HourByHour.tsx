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
      {!!steps?.length && (
        <ol className="hours-steps">
          {steps.map((x, i) => (
            <li key={i}>
              <time>{x.at}</time>
              <span><b>{x.what}</b>{x.note && <span className="small muted"> {x.note}</span>}</span>
            </li>
          ))}
        </ol>
      )}
      {book && <p className="small"><b>Book:</b> {book}</p>}
      {!!extras?.length && (
        <div className="hours-extras">
          <span className="label">Off the programme</span>
          <ul>{extras.map((e, i) => <li key={i} className="small">{e}</li>)}</ul>
        </div>
      )}
    </details>
  );
}
