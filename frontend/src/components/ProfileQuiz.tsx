import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Cold, Evenings, Pace, Profile, QuizResult, Tier } from "../lib/types";

type Answers = { cold: Cold | null; pace: Pace | null; evenings: Evenings | null; owned: string[] | null };

const STEPS: { key: "cold" | "pace" | "evenings"; q: string; why: string; options: [string, string][] }[] = [
  {
    key: "cold", q: "Do you feel the cold easily?", why: "We add or take away a little warmth on every layer.",
    options: [["very_cold", "Yes, I'm always cold"], ["bit_cold", "A bit"], ["average", "About average"], ["warm", "No, I rarely get cold"]],
  },
  {
    key: "pace", q: "How do you walk on hikes and city days?", why: "Slow walkers make less heat, so they need a bit more on.",
    options: [["relaxed", "Slow, lots of photo stops"], ["average", "Average"], ["brisk", "Fast, I rarely stop"]],
  },
  {
    key: "evenings", q: "In the evening, are you out or in?", why: "Decides whether we buy warmth for cold evenings or tell you to head inside.",
    options: [["early", "Back inside after dinner"], ["sometimes", "Out some evenings"], ["late", "Out late: drinks, stars, night walks"]],
  },
];

/** Four tap-to-answer questions before the plan. Every one can be skipped. */
export function ProfileQuiz({ tripId, tier, onDone }: {
  tripId?: string; tier?: Tier; onDone: (r: QuizResult) => void;
}) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [step, setStep] = useState(0);
  const [a, setA] = useState<Answers>({ cold: null, pace: null, evenings: null, owned: null });
  const [owned, setOwned] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.profile().then((p) => { setProfile(p); setOwned(p.owned); }).catch(() => undefined); }, []);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") skipAll(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }); // eslint-disable-line react-hooks/exhaustive-deps

  async function finish(ans: Answers) {
    setBusy(true);
    try { onDone(await api.quiz(ans, tripId, tier)); } finally { setBusy(false); }
  }
  function skipAll() { if (!busy) finish({ cold: null, pace: null, evenings: null, owned: null }); }
  function answer(key: "cold" | "pace" | "evenings", v: string | null) {
    const next = { ...a, [key]: v };
    setA(next);
    setStep(step + 1);
  }

  const total = STEPS.length + 1;
  const cur = STEPS[step];
  const current = profile && cur ? (profile[cur.key] as string) : null;

  return (
    <>
      <div className="scrim" onClick={skipAll} />
      <div className="quiz" role="dialog" aria-modal="true" aria-labelledby="quiz-q">
        <div className="quiz-top">
          <span className="kicker">Tailor the kit · {Math.min(step + 1, total)} of {total}</span>
          <button type="button" className="link small" onClick={skipAll} disabled={busy}>Skip all</button>
        </div>
        <div className="quiz-dots" aria-hidden>{Array.from({ length: total }, (_, i) => <span key={i} className={i <= step ? "on" : ""} />)}</div>
        {cur ? (
          <>
            <h2 id="quiz-q">{cur.q}</h2>
            <p className="muted">{cur.why}</p>
            <div className="quiz-opts">
              {cur.options.map(([v, label]) => (
                <button key={v} type="button" className={`qopt${profile?.done && current === v ? " was" : ""}`} onClick={() => answer(cur.key, v)}>{label}</button>
              ))}
            </div>
            <div className="quiz-foot">
              {step > 0 && <button type="button" className="btn sm ghost" onClick={() => setStep(step - 1)}>← Back</button>}
              <span className="spacer" />
              <button type="button" className="btn sm ghost" onClick={() => answer(cur.key, null)}>Skip this one</button>
            </div>
          </>
        ) : (
          <>
            <h2 id="quiz-q">What do you already have?</h2>
            <p className="muted">Tap all that apply. We check each one against the trip and tell you if it isn't warm enough. Beanie, gloves and socks are already counted as yours.</p>
            <div className="quiz-chips">
              {(profile?.basics ?? []).map((b) => {
                const on = owned.includes(b.key);
                return <button key={b.key} type="button" aria-pressed={on} className={`qchip${on ? " on" : ""}`}
                  onClick={() => setOwned(on ? owned.filter((k) => k !== b.key) : [...owned, b.key])}>{on ? "✓ " : ""}{b.label}</button>;
              })}
            </div>
            <div className="quiz-foot">
              <button type="button" className="btn sm ghost" onClick={() => setStep(step - 1)}>← Back</button>
              <span className="spacer" />
              <button type="button" className="btn sm ghost" disabled={busy} onClick={() => finish({ ...a, owned: null })}>Skip</button>
              <button type="button" className="btn primary" disabled={busy} onClick={() => finish({ ...a, owned })}>{busy ? <span className="spin" /> : "Tailor my kit"}</button>
            </div>
          </>
        )}
      </div>
    </>
  );
}
