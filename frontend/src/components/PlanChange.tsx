import { money } from "../lib/format";
import { TIER_LABEL, type PlanDiff } from "../lib/types";

/** What a profile change did to the kit: the settings that moved, then the pieces. */
export function PlanChange({ changes, plan }: { changes: string[]; plan: PlanDiff | null }) {
  const moved = plan?.totals.filter((t) => Math.abs(t.after - t.before) >= 0.5) ?? [];
  return (
    <div className="pchange">
      {changes.length > 0 && <ul className="pc-set">{changes.map((c, i) => <li key={i}>{c}</li>)}</ul>}
      {plan && (plan.pieces.length > 0 || plan.status) && (
        <div className="pc-kit">
          <p className="pc-h">{TIER_LABEL[plan.tier]} kit</p>
          {plan.status && <p className="pc-status">Warmth: {plan.status.before} → <b>{plan.status.after}</b></p>}
          <ul>
            {plan.pieces.map((p) => (
              <li key={p.slot}>
                <span className="pc-slot">{p.slot_name}</span>
                <span className="pc-was">{p.before}</span>
                <span className="pc-arrow" aria-hidden>→</span>
                <span className="pc-now">{p.after}</span>
                {Math.abs(p.cost_delta) >= 0.5 && <span className={`pc-delta ${p.cost_delta < 0 ? "down" : "up"}`}>{p.cost_delta < 0 ? "−" : "+"}{money(Math.abs(p.cost_delta))}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {moved.length > 0 && (
        <p className="pc-totals">{moved.map((t) => `${TIER_LABEL[t.tier]} ${money(t.before)} → ${money(t.after)}`).join(" · ")}</p>
      )}
      {plan && plan.owned.length > 0 && <ul className="pc-owned">{plan.owned.map((o, i) => <li key={i}>{o}</li>)}</ul>}
    </div>
  );
}
