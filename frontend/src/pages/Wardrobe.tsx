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

function SearchByName({ onPick }: { onPick: (m: ModelMatch) => void }) {
  const [q, setQ] = useState("");
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
        <input type="search" autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Torrentshell, Quechua MH500, old Merrell Moab" /></div>
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

function FromPhotos({ onPick }: { onPick: (m: ModelMatch) => void }) {
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

export default function Wardrobe() {
  const { ensureUser, toast, user } = useApp();
  const [items, setItems] = useState<WardrobeItem[] | null>(null);
  const [params] = useSearchParams();
  // "Check mine" from a kit card opens the form on that piece
  const [form, setForm] = useState(() => {
    const slot = params.get("slot");
    return slot && CATS.some(([k]) => k === slot) ? { ...blank(), category: slot } : blank();
  });
  const [mode, setMode] = useState<"name" | "photo" | "hand">(params.get("slot") ? "hand" : "name");
  const [picked, setPicked] = useState<ModelMatch | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => { await ensureUser(); setItems(await api.wardrobe()); };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

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

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      const body = { ...form, brand: form.brand || null, notes: form.notes || null };
      if (body.category !== "footwear") { body.footwear_type = null; body.ankle_support = false; }
      if (editId) await api.updateWardrobe(editId, body); else await api.addWardrobe(body);
      toast(editId ? "Item updated." : "Added. Every trip will use it where it fits.");
      reset(); setMode("name"); load();
    } catch (e2) { setErr((e2 as Error).message); }
  }

  const grouped = CATS.map(([k, l]) => [k, l, (items ?? []).filter((i) => i.category === k)] as const).filter(([, , v]) => v.length);

  return (
    <main className="page">
      <div className="wrap">
        <div className="page-head"><div><p className="kicker">What you already own</p><h1>Wardrobe</h1></div></div>
        <p className="muted" style={{ maxWidth: "64ch", marginBottom: 16 }}>
          Add the clothes you have once. Every trip uses them first, at zero cost, and tells you honestly if they're up to it.
          Start with the pieces that save the most: rain jacket, warm jacket, fleece, shoes.
        </p>
        {user?.is_guest && (
          <div className="panel row" style={{ marginBottom: 20, justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
            <span className="small" style={{ maxWidth: "60ch" }}><b>Keep your wardrobe.</b> You're on a guest account that lives only in this browser.
              Create a free account and your clothes are there for every trip, on any device. What you added so far comes with you.</span>
            <Link className="btn sm primary" to="/register">Create account</Link>
          </div>
        )}
        <div className="cols">
          <div className="stack">
            {items === null ? <p className="loading"><span className="spin" /></p> : grouped.length === 0 ? (
              <div className="empty">Nothing here yet. Search your rain jacket by name, or snap its label: it takes a minute.</div>
            ) : grouped.map(([k, l, list]) => (
              <section key={k}>
                <h2 className="label" style={{ margin: "8px 0" }}>{l}</h2>
                <div className="wgrid">
                  {list.map((i) => (
                    <div className="witem" key={i.id}>
                      <div className="row"><span className="ph-s s"><ProductArt slot={i.category} /></span><h3>{i.brand ? `${i.brand} ` : ""}{i.name}</h3></div>
                      <span className="small muted">{summary(i)}</span>
                      {i.model_ref && <span className="small muted">{i.added_via === "photo" ? "Recognised from your photos" : "Matched to a known model"}</span>}
                      <div className="row">
                        <button className="btn sm" type="button" onClick={() => {
                          const { id: _id, created_at: _c, specs: _s, ...rest } = i as WardrobeItem & { created_at?: string };
                          void _id; void _c; void _s;
                          setEditId(i.id); setPicked(null); setForm(rest); setMode("hand");
                        }}>Edit</button>
                        <button className="btn sm danger" type="button" onClick={async () => { await api.deleteWardrobe(i.id); load(); }}>Remove</button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>
          <div className="panel stack">
            <h2 style={{ fontSize: 20 }}>{editId ? "Edit item" : picked ? "Is this right?" : "Add something you own"}</h2>
            {!editId && !picked && (
              <div className="seg" role="tablist">
                {([["name", "By name"], ["photo", "From photos"], ["hand", "By hand"]] as const).map(([k, l]) => (
                  <button key={k} type="button" role="tab" aria-selected={mode === k} onClick={() => { setMode(k); if (k === "hand") setForm(blank()); }}>{l}</button>
                ))}
              </div>
            )}
            {/* kept mounted, so "Back" returns to the same results and photos */}
            <div hidden={mode !== "name" || !!picked || !!editId}><SearchByName onPick={(m) => pick(m, "search")} /></div>
            {mode === "photo" || picked?.source === "photo" || form.added_via === "photo" ? (
              <div hidden={mode !== "photo" || !!picked || !!editId}><FromPhotos onPick={(m) => pick(m, "photo")} /></div>
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
                <div className="field"><label>Type</label>
                  <select value={form.category} onChange={(e) => set({ category: e.target.value })}>{CATS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
                <div className="field"><label>Name</label><input type="text" required value={form.name} onChange={(e) => set({ name: e.target.value })} placeholder="e.g. Old blue rain jacket" /></div>
                <div className="grid2">
                  <div className="field"><label>Brand</label><input type="text" value={form.brand ?? ""} onChange={(e) => set({ brand: e.target.value })} /></div>
                  <div className="field"><label>Warmth</label>
                    <select value={form.warmth} onChange={(e) => set({ warmth: e.target.value })}>{WARMTH.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
                </div>
                <div className="field"><label>Material</label>
                  <select value={form.material ?? ""} onChange={(e) => set({ material: e.target.value || null })}>{MATERIALS.map((m) => <option key={m} value={m}>{m || "Not sure"}</option>)}</select></div>
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
                  <button className="btn primary" type="submit">{editId ? "Save" : picked ? "Yes, add it" : "Add to wardrobe"}</button>
                  {(editId || picked) && <button className="btn" type="button" onClick={() => { const back = picked ? (form.added_via === "photo" ? "photo" : "name") : "name"; reset(); setMode(back); }}>{picked ? "Back" : "Cancel"}</button>}
                </div>
                <p className="small muted">Warmth is an estimate for a {CAT_LABEL[form.category]?.toLowerCase()}. You can always override the pick on a trip.</p>
              </form>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
