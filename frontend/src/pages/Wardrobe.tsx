import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ProductArt } from "../components/ProductArt";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import type { ModelMatch, PhotoReading, WardrobeItem } from "../lib/types";

const CATS: [string, string][] = [
  ["shell_top", "Rain / shell jacket"], ["insulation_top", "Insulated jacket (down, synthetic)"], ["mid_top", "Fleece / mid layer"],
  ["base_top", "Base layer top / T-shirt"], ["base_bottom", "Base layer bottom / leggings"], ["trousers", "Trousers / shorts"],
  ["shell_bottom", "Rain trousers"], ["headwear", "Beanie"], ["gloves", "Gloves"], ["sun_hat", "Sun hat"], ["socks", "Socks"], ["footwear", "Shoes / boots"],
];
const CAT_LABEL = Object.fromEntries(CATS);
const WARMTH: [string, string][] = [["light", "Light"], ["medium", "Medium"], ["warm", "Warm"], ["very_warm", "Very warm"]];
const WARMTH_SAY: Record<string, string> = { light: "light", medium: "medium warmth", warm: "warm", very_warm: "very warm" };
const MATERIALS = ["", "merino", "synthetic", "fleece", "down", "cotton", "other"];
const FOOT: [string, string][] = [["sandal", "Sandals"], ["sneaker", "Sneakers / city shoes"], ["trail_runner", "Trail runners / hiking shoes"], ["hiking_boot", "Hiking boots"], ["mountaineering_boot", "Mountaineering boots"]];

type Form = Omit<WardrobeItem, "id">;
const blank = (): Form => ({
  category: "shell_top", name: "", brand: "", warmth: "medium", clo_override: null, waterproof: false, windproof: false,
  material: null, footwear_type: null, ankle_support: false, notes: null, model_ref: null, added_via: "hand",
});

/** What the tool asks for: how many photos, and how to take each one. */
const KINDS: { key: string; label: string; shots: { title: string; how: string; optional?: boolean }[] }[] = [
  { key: "top", label: "Jacket or top", shots: [
    { title: "The whole item", how: "Lay it flat on a bed or the floor in daylight, zipped up, all of it in the frame." },
    { title: "The logo", how: "Close-up of the brand logo on the chest, sleeve or back. Fill the frame." },
    { title: "The label inside", how: "The small label in the collar or the side seam, with the name and the style number. Flat, sharp, no flash." },
    { title: "The inside or the fabric label", how: "Optional: the lining, the fill, or the label that lists the fabric.", optional: true },
  ] },
  { key: "bottom", label: "Trousers", shots: [
    { title: "The whole item", how: "Laid flat, front side up, in daylight." },
    { title: "The label inside", how: "The label inside the waistband with the name or style number. Flat and sharp." },
    { title: "The logo", how: "Optional: close-up of the logo, often on a pocket or the hip.", optional: true },
  ] },
  { key: "shoes", label: "Shoes or boots", shots: [
    { title: "The side", how: "One shoe from the outer side, at shoe height, the whole shoe in the frame." },
    { title: "The tongue label", how: "Open the laces: the label inside the tongue has the model and an article code." },
    { title: "The sole", how: "The sole from below: the brand of the rubber (e.g. Vibram) helps.", optional: true },
  ] },
  { key: "small", label: "Hat, gloves, socks", shots: [
    { title: "The whole item", how: "Flat, in daylight." },
    { title: "The label", how: "The sewn-in label or the logo, close-up." },
  ] },
];

function summary(i: Pick<WardrobeItem, "warmth" | "material" | "waterproof" | "windproof" | "footwear_type" | "ankle_support" | "category">) {
  return [CAT_LABEL[i.category], WARMTH_SAY[i.warmth], i.material !== "other" && i.material,
    i.waterproof && "waterproof", !i.waterproof && i.windproof && "windproof",
    i.footwear_type && FOOT.find((f) => f[0] === i.footwear_type)?.[1], i.ankle_support && "ankle support"].filter(Boolean).join(" · ");
}

function SourceTag({ m }: { m: ModelMatch }) {
  if (m.source === "shop") return <span className="tag">On sale now</span>;
  if (m.source === "estimate" || m.source === "photo") return <span className="tag src-estimate">Estimate: check it</span>;
  if (!m.brand) return <span className="tag">Everyday piece</span>;
  return m.older ? <span className="tag src-climate">Older model</span> : <span className="tag">Known model</span>;
}

/** Shrink a phone photo to at most 1280 px JPEG (~200-400 KB) before it leaves the device. */
async function shrink(file: File): Promise<Blob> {
  const bmp = await createImageBitmap(file);
  const k = Math.min(1, 1280 / Math.max(bmp.width, bmp.height));
  const c = document.createElement("canvas");
  c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
  c.getContext("2d")!.drawImage(bmp, 0, 0, c.width, c.height);
  return new Promise((ok, no) => c.toBlob((b) => (b ? ok(b) : no(new Error("Could not read the photo"))), "image/jpeg", 0.85));
}

function MatchList({ list, onPick }: { list: ModelMatch[]; onPick: (m: ModelMatch) => void }) {
  return (
    <ul className="matches">
      {list.map((m) => (
        <li key={(m.ref ?? "") + m.name}>
          <button type="button" className="match" onClick={() => onPick(m)}>
            <span className="ph-s s"><ProductArt slot={m.category} /></span>
            <span>
              <b>{m.brand ? `${m.brand} ` : ""}{m.name}</b> <SourceTag m={m} />
              <span className="small muted" style={{ display: "block" }}>{summary(m)}</span>
              {m.note && <span className="small muted" style={{ display: "block" }}>{m.note}</span>}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function SearchByName({ onPick, seed = "" }: { onPick: (m: ModelMatch) => void; seed?: string }) {
  const [q, setQ] = useState(seed);
  const [res, setRes] = useState<ModelMatch[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    const t = q.trim();
    if (t.length < 2) { setRes(null); return; }
    const n = ++seq.current;
    const h = setTimeout(async () => {
      try { const r = await api.findModel(t); if (n === seq.current) setRes(r.results); } catch { if (n === seq.current) setRes([]); }
    }, 250);
    return () => clearTimeout(h);
  }, [q]);

  async function estimate() {
    setBusy(true); setErr(null);
    try {
      const r = await api.guessModel(q.trim());
      if (r.result) onPick(r.result); else setErr("We can't tell what this is from the name. Describe it instead: it takes 20 seconds.");
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="stack">
      <div className="field"><label>Brand and model, as you remember them</label>
        <input type="search" autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Torrentshell, Quechua MH500" /></div>
      <p className="small muted">Older and discontinued models count too: a model line keeps its warmth across versions.</p>
      {res && res.length > 0 && <MatchList list={res} onPick={onPick} />}
      {res && q.trim().length >= 3 && (
        <div className="row" style={{ alignItems: "center", flexWrap: "wrap" }}>
          <span className="small muted">{res.length ? "Not in the list?" : "Not in our list."}</span>
          <button type="button" className="btn sm" disabled={busy} onClick={estimate}>{busy ? <span className="spin" /> : "Estimate it from the name"}</button>
        </div>
      )}
      {err && <p className="err">{err}</p>}
    </div>
  );
}

function FromPhotos({ onPick, onSearch }: { onPick: (m: ModelMatch) => void; onSearch: (q: string) => void }) {
  const [status, setStatus] = useState<{ available: boolean } | null>(null);
  const [kind, setKind] = useState<string | null>(null);
  const [shots, setShots] = useState<(Blob | null)[]>([]);
  const [previews, setPreviews] = useState<(string | null)[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [reading, setReading] = useState<PhotoReading | null>(null);

  useEffect(() => { api.photoStatus().then(setStatus).catch(() => setStatus({ available: false })); }, []);
  useEffect(() => () => previews.forEach((u) => u && URL.revokeObjectURL(u)), [previews]);

  const guide = KINDS.find((k) => k.key === kind);
  const required = guide ? guide.shots.filter((s) => !s.optional).length : 0;
  const have = shots.filter(Boolean).length;
  const ready = guide && guide.shots.every((s, i) => s.optional || shots[i]);

  function choose(k: string) {
    setKind(k); setReading(null); setErr(null);
    const n = KINDS.find((x) => x.key === k)!.shots.length;
    setShots(Array(n).fill(null)); setPreviews(Array(n).fill(null));
  }

  async function take(i: number, f: File | undefined) {
    if (!f) return;
    setErr(null);
    try {
      const b = await shrink(f);
      setShots((s) => s.map((x, j) => (j === i ? b : x)));
      setPreviews((p) => p.map((x, j) => (j === i ? URL.createObjectURL(b) : x)));
    } catch { setErr("That file isn't a photo we can read. Use a JPEG or PNG."); }
  }

  async function recognize() {
    setBusy(true); setErr(null); setReading(null);
    try { setReading(await api.recognize(shots.filter(Boolean) as Blob[], kind!)); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  if (status && !status.available) {
    return <div className="empty small">Photo recognition is not switched on on this server yet. Search by name instead: it finds the same models.</div>;
  }

  return (
    <div className="stack">
      <div className="field"><label>What is it?</label>
        <div className="chips">{KINDS.map((k) => (
          <button key={k.key} type="button" className={`chip-btn${kind === k.key ? " on" : ""}`} onClick={() => choose(k.key)}>{k.label}</button>
        ))}</div>
      </div>
      {guide && (
        <>
          <p className="small"><b>Take {required === guide.shots.length ? required : `${required} or ${guide.shots.length}`} photos.</b>{" "}
            The label is what names the model: without it we can tell the kind and the warmth, not the exact model.</p>
          <ol className="shots">
            {guide.shots.map((s, i) => (
              <li key={s.title} className={shots[i] ? "done" : ""}>
                <label className="shot">
                  {previews[i] ? <img src={previews[i]!} alt="" /> : <span className="shot-ph">{i + 1}</span>}
                  <span>
                    <b>{s.title}</b>{s.optional && <span className="small muted"> (optional)</span>}
                    <span className="small muted" style={{ display: "block" }}>{s.how}</span>
                    <span className="small"><u>{shots[i] ? "Retake" : "Take or choose photo"}</u></span>
                  </span>
                  <input type="file" accept="image/*" capture="environment" hidden onChange={(e) => take(i, e.target.files?.[0])} />
                </label>
              </li>
            ))}
          </ol>
          <button type="button" className="btn primary" disabled={!ready || busy} onClick={recognize}>
            {busy ? <><span className="spin" /> Reading the photos…</> : `Recognise it (${have} photo${have === 1 ? "" : "s"})`}
          </button>
          {busy && <p className="small muted">On a home computer this can take up to a minute.</p>}
          <p className="small muted">Your photos are only read to recognise the item. We don't keep them.</p>
        </>
      )}
      {err && <p className="err">{err}</p>}
      {reading && (
        <div className="stack">
          {reading.seen.text.length > 0 ? (
            <div className="chips small"><span className="muted">We read:</span>{reading.seen.text.map((t) => <span key={t} className="tag">{t}</span>)}</div>
          ) : <p className="small muted">We couldn't read any text on the label.</p>}
          {reading.results.length > 0 ? (
            <>
              <h3 style={{ fontSize: 16 }}>{reading.seen.model ? "Is it this one?" : "Is it one of these?"}</h3>
              <MatchList list={reading.results} onPick={onPick} />
            </>
          ) : (
            <p className="small">{reading.seen.label_readable ? "We read the label but this model isn't in our list yet." : "Without a readable label we can't name the exact model."}{" "}
              Here is what the photos show: check it and add it.</p>
          )}
          {/* a logo alone does not name the model: the traveller often remembers it */}
          <button type="button" className="btn" onClick={() => onSearch(reading.seen.brand ?? "")}>
            {reading.seen.brand ? `Not here? Search ${reading.seen.brand} models by name` : "Search by name instead"}
          </button>
          {reading.described && (
            <button type="button" className="btn" onClick={() => onPick(reading.described!)}>
              {reading.results.length ? "None of these: use what the photos show" : `Use: ${reading.described.name}, ${summary(reading.described).toLowerCase()}`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/** The board behind the panel: every layer slot of the plan, what you own for it, what's missing.
 *  It plays the map's part on the other pages (Manu 2026-11-16: the Closet in the same panel style). */
const BOARD: [string, string[]][] = [
  ["Upper body", ["shell_top", "insulation_top", "mid_top", "base_top"]],
  ["Legs", ["trousers", "shell_bottom", "base_bottom"]],
  ["Head, hands, feet", ["headwear", "gloves", "sun_hat", "footwear", "socks"]],
];
const SHORT: Record<string, string> = {
  shell_top: "Rain jacket", insulation_top: "Insulated jacket", mid_top: "Fleece", base_top: "Base layer top",
  trousers: "Trousers", shell_bottom: "Rain trousers", base_bottom: "Base layer bottom", headwear: "Beanie",
  gloves: "Gloves", sun_hat: "Sun hat", footwear: "Shoes / boots", socks: "Socks",
};

/** The Closet, map-first like the rest (Manu 2026-11-16): the panel on the left lists what you own
 *  or adds a piece, a picked piece opens its card beside it, and the board behind shows every layer
 *  slot of the plan, filled or still empty. Phone: the board on top, the panel below. */
export default function Wardrobe() {
  const { ensureUser, toast, user } = useApp();
  const [items, setItems] = useState<WardrobeItem[] | null>(null);
  const [params] = useSearchParams();
  const slotParam = params.get("slot");
  // "Check mine" from a kit card opens the form on that piece
  const [form, setForm] = useState(() => slotParam && CATS.some(([k]) => k === slotParam) ? { ...blank(), category: slotParam } : blank());
  const [tab, setTab] = useState<"own" | "add">(slotParam ? "add" : "own");
  const [mode, setMode] = useState<"name" | "photo" | "hand">(slotParam ? "hand" : "name");
  const [picked, setPicked] = useState<ModelMatch | null>(null);
  const [nameSeed, setNameSeed] = useState({ q: "", n: 0 });
  const [editId, setEditId] = useState<string | null>(null);
  const [selId, setSelId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [desk, setDesk] = useState(() => typeof matchMedia === "undefined" || matchMedia("(min-width: 900px)").matches);

  useEffect(() => {
    const mq = matchMedia("(min-width: 900px)");
    const f = () => setDesk(mq.matches);
    mq.addEventListener("change", f);
    return () => mq.removeEventListener("change", f);
  }, []);

  const load = async () => { await ensureUser(); setItems(await api.wardrobe()); };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // nothing owned yet: the panel opens on adding the first piece
  useEffect(() => { if (items && !items.length && !slotParam) setTab("add"); }, [items === null]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (p: Partial<Form>) => setForm((f) => ({ ...f, ...p }));

  function pick(m: ModelMatch, via: "search" | "photo") {
    setPicked(m); setEditId(null); setErr(null);
    setForm({
      ...blank(), category: m.category, name: m.name, brand: m.brand ?? "", warmth: m.warmth, waterproof: m.waterproof,
      windproof: m.windproof, material: m.material, footwear_type: m.footwear_type, ankle_support: m.ankle_support,
      model_ref: m.ref, added_via: via,
    });
    setMode("hand");
  }

  function reset() { setForm(blank()); setEditId(null); setPicked(null); }

  function edit(i: WardrobeItem) {
    const { id: _id, created_at: _c, specs: _s, ...rest } = i as WardrobeItem & { created_at?: string };
    void _id; void _c; void _s;
    setEditId(i.id); setPicked(null); setForm(rest); setMode("hand"); setTab("add"); setSelId(null);
  }

  async function remove(i: WardrobeItem) {
    await api.deleteWardrobe(i.id);
    if (selId === i.id) setSelId(null);
    load();
  }

  /** a slot on the board: its piece opens, or the form opens on it */
  function slot(k: string) {
    const mine = (items ?? []).filter((i) => i.category === k);
    if (mine.length) { setTab("own"); setSelId(mine[0].id); return; }
    reset(); setForm({ ...blank(), category: k }); setMode("hand"); setTab("add"); setSelId(null);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      const body = { ...form, brand: form.brand || null, notes: form.notes || null };
      if (body.category !== "footwear") { body.footwear_type = null; body.ankle_support = false; }
      if (editId) await api.updateWardrobe(editId, body); else await api.addWardrobe(body);
      toast(editId ? "Item updated." : "Added. Every trip will use it where it fits.");
      reset(); setMode("name"); setTab("own"); load();
    } catch (e2) { setErr((e2 as Error).message); }
  }

  const grouped = CATS.map(([k, l]) => [k, l, (items ?? []).filter((i) => i.category === k)] as const).filter(([, , v]) => v.length);
  const sel = selId ? (items ?? []).find((i) => i.id === selId) ?? null : null;
  const covered = new Set((items ?? []).map((i) => i.category));
  const slots = BOARD.flatMap(([, ks]) => ks);

  const board = (
    <div className={`mf-map cl-board${sel && desk ? " with-card" : ""}`}>
      <div className="cl-board-in">
        <div className="cl-board-h">
          <b>Your layers</b>
          <span className="mf-k">{items === null ? "" : `${slots.filter((k) => covered.has(k)).length} of ${slots.length} covered by what you own`}</span>
        </div>
        {BOARD.map(([g, ks]) => (
          <section key={g} className="cl-group" aria-label={g}>
            <h2 className="cl-gh">{g}</h2>
            <div className="cl-tiles">
              {ks.map((k) => {
                const mine = (items ?? []).filter((i) => i.category === k);
                const on = !!sel && sel.category === k;
                return (
                  <button key={k} type="button" className={`cl-tile${mine.length ? " have" : ""}${on ? " sel" : ""}`} onClick={() => slot(k)}
                    aria-label={`${SHORT[k]}: ${mine.length ? mine.map((i) => i.name).join(", ") : "nothing yet, add one"}`}>
                    <span className="cl-art"><ProductArt slot={k} /></span>
                    <span className="cl-tn">{SHORT[k]}</span>
                    <span className="cl-ts">{mine.length ? `${mine[0].brand ? `${mine[0].brand} ` : ""}${mine[0].name}${mine.length > 1 ? ` +${mine.length - 1}` : ""}` : "+ Add yours"}</span>
                  </button>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );

  const card = sel && (
    <div className={desk ? "mf-float mf-card cl-card" : "cl-card in"}>
      <button type="button" className="mf-x" onClick={() => setSelId(null)} aria-label="Close"><X /></button>
      <div className="cl-card-art"><ProductArt slot={sel.category} /></div>
      <div className="mf-card-in">
        <span className="mf-k">{CAT_LABEL[sel.category]}</span>
        <h3>{sel.brand ? `${sel.brand} ` : ""}{sel.name}</h3>
        <p className="mf-k cl-sum">{summary(sel)}</p>
        {sel.model_ref && <p className="mf-k">{sel.added_via === "photo" ? "Recognised from your photos" : "Matched to a known model"}</p>}
        <p className="cl-use">Every trip puts this in your kit first, at no cost, wherever it does the job.</p>
        <div className="mf-acts">
          <button type="button" className="mf-btn go" onClick={() => edit(sel)}>Edit</button>
          <button type="button" className="mf-btn cl-del" onClick={() => remove(sel)}>Remove</button>
        </div>
      </div>
    </div>
  );

  const own = (
    <div className="mf-scroll">
      {items === null ? <div className="loading"><span className="spin" /></div> : grouped.length === 0 ? (
        <div className="mf-empty"><p>Nothing here yet. Search your rain jacket by name, or snap its label: it takes a minute.</p>
          <button type="button" className="mf-btn go" onClick={() => setTab("add")}>Add your first piece</button></div>
      ) : grouped.map(([k, l, list]) => (
        <section key={k} className="cl-sec">
          <b className="mf-sub">{l}</b>
          <ul className="mf-treks">
            {list.map((i) => (
              <li key={i.id}>
                <button type="button" className={`mf-trow${selId === i.id ? " sel" : ""}`} onClick={() => setSelId(selId === i.id ? null : i.id)}>
                  <span className="mf-thumb cl-thumb"><ProductArt slot={i.category} /></span>
                  <span className="mf-nm">
                    <b>{i.brand ? `${i.brand} ` : ""}{i.name}</b>
                    <small className="mf-base">{summary(i)}</small>
                  </span>
                </button>
                {!desk && selId === i.id && card}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );

  const add = (
    <div className="mf-scroll cl-add">
      <b className="mf-sub">{editId ? "Edit item" : picked ? "Is this right?" : "Add something you own"}</b>
      {!editId && !picked && (
        <div className="mf-chips" role="tablist" aria-label="How do you want to add it?">
          {([["name", "By name"], ["photo", "From photos"], ["hand", "By hand"]] as const).map(([k, l]) => (
            <button key={k} type="button" role="tab" aria-selected={mode === k} className={mode === k ? "on" : ""}
              onClick={() => { setMode(k); if (k === "hand") setForm((f) => ({ ...blank(), category: f.category })); }}>{l}</button>
          ))}
        </div>
      )}
      {/* kept mounted, so "Back" returns to the same results and photos */}
      <div hidden={mode !== "name" || !!picked || !!editId}><SearchByName key={nameSeed.n} seed={nameSeed.q} onPick={(m) => pick(m, "search")} /></div>
      {mode === "photo" || picked?.source === "photo" || form.added_via === "photo" ? (
        <div hidden={mode !== "photo" || !!picked || !!editId}><FromPhotos onPick={(m) => pick(m, "photo")} onSearch={(q) => { setNameSeed((s) => ({ q: q ? `${q} ` : "", n: s.n + 1 })); setMode("name"); }} /></div>
      ) : null}
      {mode === "hand" && (
        <form className="form" onSubmit={save}>
          {picked && (
            <p className="small">
              {picked.source === "estimate" || picked.source === "photo"
                ? "This is our estimate. Fix anything that's wrong, then add it."
                : "We filled this in from the model. Change anything that's different on yours, then add it."}
              {picked.note && <><br /><span className="muted">{picked.note}</span></>}
            </p>
          )}
          <div className="grid2">
            <div className="field"><label>Type</label>
              <select value={form.category} onChange={(e) => set({ category: e.target.value })}>{CATS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
            <div className="field"><label>Warmth</label>
              <select value={form.warmth} onChange={(e) => set({ warmth: e.target.value })}>{WARMTH.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
          </div>
          <div className="field"><label>Name</label><input type="text" required value={form.name} onChange={(e) => set({ name: e.target.value })} placeholder="e.g. Old blue rain jacket" /></div>
          <div className="grid2">
            <div className="field"><label>Brand</label><input type="text" value={form.brand ?? ""} onChange={(e) => set({ brand: e.target.value })} /></div>
            <div className="field"><label>Material</label>
              <select value={form.material ?? ""} onChange={(e) => set({ material: e.target.value || null })}>{MATERIALS.map((m) => <option key={m} value={m}>{m || "Not sure"}</option>)}</select></div>
          </div>
          {form.category === "footwear" && (
            <div className="grid2">
              <div className="field"><label>Kind of shoe</label>
                <select value={form.footwear_type ?? "sneaker"} onChange={(e) => set({ footwear_type: e.target.value })}>{FOOT.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
              <label className="check" style={{ alignSelf: "end" }}><input type="checkbox" checked={form.ankle_support} onChange={(e) => set({ ankle_support: e.target.checked })} /> Ankle support</label>
            </div>
          )}
          <div className="row">
            <label className="check"><input type="checkbox" checked={form.waterproof} onChange={(e) => set({ waterproof: e.target.checked })} /> Waterproof</label>
            <label className="check"><input type="checkbox" checked={form.windproof} onChange={(e) => set({ windproof: e.target.checked })} /> Windproof</label>
          </div>
          {err && <p className="err">{err}</p>}
          <div className="row">
            <button className="mf-btn go" type="submit">{editId ? "Save" : picked ? "Yes, add it" : "Add to my closet"}</button>
            {(editId || picked) && <button className="mf-btn" type="button" onClick={() => { const back = picked ? (form.added_via === "photo" ? "photo" : "name") : "name"; reset(); setMode(back); if (!picked) setTab("own"); }}>{picked ? "Back" : "Cancel"}</button>}
          </div>
          <p className="small muted">Warmth is an estimate for this type of piece. You can always override the pick on a trip.</p>
        </form>
      )}
    </div>
  );

  return (
    <main className="trk closet-mf">
      <div className="mf">
        {board}
        <section className="mf-float mf-panel" aria-label="Closet">
          <div className="mf-thead"><h1>Closet</h1>{items && <span className="mf-k">{items.length} piece{items.length === 1 ? "" : "s"}</span>}</div>
          <p className="mf-k cl-lede">Add what you own once. Every trip uses it first, for free.</p>
          <div className="mf-seg" role="tablist" aria-label="Closet">
            <button type="button" role="tab" aria-selected={tab === "own"} className={tab === "own" ? "on" : ""} onClick={() => { setTab("own"); reset(); setMode("name"); }}>What I own</button>
            <button type="button" role="tab" aria-selected={tab === "add"} className={tab === "add" ? "on" : ""} onClick={() => setTab("add")}>Add a piece</button>
          </div>
          {tab === "own" ? own : add}
          {user?.is_guest && (
            <p className="mf-k cl-guest"><b>Keep your closet.</b> As a guest it lives only in this browser. <Link to="/register">Create a free account</Link>.</p>
          )}
        </section>
        {desk && card}
      </div>
    </main>
  );
}

const X = () => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>;
