import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { ChatReply, Tier } from "../lib/types";
import { PlanChange } from "./PlanChange";

type Msg = { id: number; from: "you" | "app"; text: string; reply?: ChatReply; undone?: boolean };

const SUGGEST = ["I'm always cold", "I rarely feel the cold", "I have an old Decathlon fleece", "I walk slowly, lots of photos", "Do I need rain trousers?"];

/** Optional chat: tell the app about yourself ("I'm always cold", "I have hiking boots")
 *  and the kit is recomputed, or ask a question about the plan. */
export function TailorChat({ tripId, tier, onChanged }: { tripId: string; tier: Tier; onChanged: () => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const seq = useRef(0);

  useEffect(() => { if (msgs.length) end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [msgs]);

  async function send(t: string) {
    const m = t.trim();
    if (m.length < 2 || busy) return;
    setText("");
    setMsgs((x) => [...x, { id: ++seq.current, from: "you", text: m }]);
    setBusy(true);
    try {
      const r = await api.chat(tripId, m, tier);
      setMsgs((x) => [...x, { id: ++seq.current, from: "app", text: r.text, reply: r }]);
      if (r.kind === "update" && r.changes.length) onChanged();
    } catch (e) {
      setMsgs((x) => [...x, { id: ++seq.current, from: "app", text: (e as Error).message }]);
    } finally { setBusy(false); }
  }

  async function undo(msg: Msg) {
    if (!msg.reply || msg.reply.kind !== "update") return;
    const u = msg.reply.undo;
    await api.updateMe(u.profile);
    await Promise.all(u.wardrobe_ids.map((id) => api.deleteWardrobe(id).catch(() => undefined)));
    setMsgs((x) => x.map((y) => (y.id === msg.id ? { ...y, undone: true } : y)));
    onChanged();
  }

  return (
    <div className="tchat">
      {msgs.length > 0 && (
        <div className="tc-log" aria-live="polite">
          {msgs.map((m) => (
            <div key={m.id} className={`tc-msg ${m.from}${m.undone ? " undone" : ""}`}>
              <div className="tc-bubble">
                {m.reply?.kind === "answer" && <span className="ai-src">{m.reply.source === "llm" ? "Local AI" : "AI offline: from the plan's notes"}</span>}
                <p>{m.text}</p>
                {m.reply?.kind === "update" && m.reply.changes.length > 0 && (
                  <>
                    <PlanChange changes={m.reply.changes} plan={m.reply.plan} />
                    <div className="row small">
                      <span className="ai-src">{m.reply.reader === "llm" ? "Read by the local AI" : "Read by the rule-based reader"}</span>
                      <span className="spacer" />
                      {m.undone ? <span className="muted">Undone</span>
                        : <button type="button" className="link small" onClick={() => undo(m)}>Undo</button>}
                    </div>
                  </>
                )}
              </div>
            </div>
          ))}
          {busy && <div className="tc-msg app"><div className="tc-bubble"><span className="spin" /></div></div>}
          <div ref={end} />
        </div>
      )}
      <form className="tc-form" onSubmit={(e) => { e.preventDefault(); send(text); }}>
        <input type="text" value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} aria-label="Tell us about you or ask a question"
          placeholder="I'm always cold, and I have an old Decathlon fleece" />
        <button className="btn primary" type="submit" disabled={busy || text.trim().length < 2}>{busy ? <span className="spin" /> : "Send"}</button>
      </form>
      {msgs.length === 0 && (
        <div className="tc-sugg">{SUGGEST.map((s) => <button key={s} type="button" className="qchip" onClick={() => send(s)}>{s}</button>)}</div>
      )}
    </div>
  );
}
