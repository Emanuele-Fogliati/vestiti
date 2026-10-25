import { ACTIVITY_LABEL } from "../lib/format";
import type { Activity } from "../lib/types";

const TYPES = ["city", "hiking", "trek_multiday", "beach", "ski", "cycling", "safari", "boat", "desert", "unknown"];
const DIFFS = ["easy", "moderate", "hard", "technical", "unknown"];
const DIFF_LABEL: Record<string, string> = { easy: "Easy", moderate: "Moderate", hard: "Hard", technical: "Technical", unknown: "Don't know yet" };

export function ActivityEditor({ value, onChange }: { value: Activity[]; onChange: (a: Activity[]) => void }) {
  const set = (i: number, patch: Partial<Activity>) => onChange(value.map((a, j) => (j === i ? { ...a, ...patch } : a)));
  return (
    <div className="stack">
      {value.map((a, i) => {
        const mountain = a.type === "hiking" || a.type === "trek_multiday" || a.type === "ski";
        return (
          <div className="actrow" key={i}>
            <div className="field"><label>Activity</label>
              <select value={a.type} onChange={(e) => set(i, {
                type: e.target.value,
                difficulty: e.target.value === "hiking" || e.target.value === "trek_multiday" ? a.difficulty ?? "moderate" : null,
              })}>
                {TYPES.map((t) => <option key={t} value={t}>{ACTIVITY_LABEL[t]}</option>)}
              </select>
            </div>
            <div className="field"><label>Difficulty</label>
              <select value={a.difficulty ?? ""} disabled={!(a.type === "hiking" || a.type === "trek_multiday")}
                onChange={(e) => set(i, { difficulty: e.target.value || null })}>
                <option value="">—</option>
                {DIFFS.map((d) => <option key={d} value={d}>{DIFF_LABEL[d]}</option>)}
              </select>
            </div>
            <div className="field"><label>Highest point (m)</label>
              <input type="number" min={0} max={9000} step={50} value={a.max_altitude_m ?? ""} disabled={!mountain}
                placeholder={mountain ? "e.g. 2400" : "—"}
                onChange={(e) => set(i, { max_altitude_m: e.target.value ? Number(e.target.value) : null })} />
            </div>
            <label className="check small" title="Walking on ice with crampons: changes boots and gloves">
              <input type="checkbox" checked={!!a.glacier} disabled={!mountain}
                onChange={(e) => set(i, { glacier: e.target.checked })} /> On a glacier
            </label>
            <button type="button" className="btn sm ghost" aria-label="Remove activity"
              disabled={value.length <= 1} onClick={() => onChange(value.filter((_, j) => j !== i))}>✕</button>
          </div>
        );
      })}
      <div><button type="button" className="btn sm" onClick={() => onChange([...value, { type: "city" }])}>+ Another activity</button></div>
      <p className="small muted">"Don't know yet" plans for both an easy and a technical day, so you're covered either way.</p>
    </div>
  );
}
