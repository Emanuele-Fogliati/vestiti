import { useState } from "react";

/** Tap the brands you like; type one we don't list. Empty = any brand. */
export function BrandPicker({ catalog, value, onChange }: {
  catalog: string[]; value: string[]; onChange: (v: string[]) => void;
}) {
  const [other, setOther] = useState("");
  const has = (b: string) => value.some((v) => v.toLowerCase() === b.toLowerCase());
  const toggle = (b: string) => onChange(has(b) ? value.filter((v) => v.toLowerCase() !== b.toLowerCase()) : [...value, b].slice(0, 8));
  const extra = value.filter((v) => !catalog.some((c) => c.toLowerCase() === v.toLowerCase()));
  function add() {
    const b = other.trim();
    if (b && !has(b)) onChange([...value, b].slice(0, 8));
    setOther("");
  }
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="quiz-chips">
        {[...catalog, ...extra].map((b) => {
          const on = has(b);
          return <button key={b} type="button" aria-pressed={on} className={`qchip${on ? " on" : ""}`} onClick={() => toggle(b)}>{on ? "♥ " : ""}{b}</button>;
        })}
      </div>
      <form className="row" onSubmit={(e) => { e.preventDefault(); add(); }}>
        <input value={other} maxLength={60} placeholder="Another brand" aria-label="Another brand" onChange={(e) => setOther(e.target.value)} />
        <button type="submit" className="btn sm ghost" disabled={!other.trim()}>Add</button>
      </form>
    </div>
  );
}
