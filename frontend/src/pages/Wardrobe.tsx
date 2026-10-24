import { useEffect, useState } from "react";
import { ProductArt } from "../components/ProductArt";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import type { WardrobeItem } from "../lib/types";

const CATS: [string, string][] = [
  ["shell_top", "Rain / shell jacket"], ["insulation_top", "Insulated jacket (down, synthetic)"], ["mid_top", "Fleece / mid layer"],
  ["base_top", "Base layer top / T-shirt"], ["base_bottom", "Base layer bottom / leggings"], ["trousers", "Trousers / shorts"],
  ["shell_bottom", "Rain trousers"], ["headwear", "Beanie"], ["gloves", "Gloves"], ["sun_hat", "Sun hat"], ["socks", "Socks"], ["footwear", "Shoes / boots"],
];
const CAT_LABEL = Object.fromEntries(CATS);
const WARMTH: [string, string][] = [["light", "Light"], ["medium", "Medium"], ["warm", "Warm"], ["very_warm", "Very warm"]];
const MATERIALS = ["", "merino", "synthetic", "fleece", "down", "cotton", "other"];
const FOOT: [string, string][] = [["sandal", "Sandals"], ["sneaker", "Sneakers / city shoes"], ["trail_runner", "Trail runners / hiking shoes"], ["hiking_boot", "Hiking boots"], ["mountaineering_boot", "Mountaineering boots"]];

const blank = (): Omit<WardrobeItem, "id"> => ({
  category: "shell_top", name: "", brand: "", warmth: "medium", clo_override: null, waterproof: false, windproof: false,
  material: null, footwear_type: null, ankle_support: false, notes: null,
});

export default function Wardrobe() {
  const { ensureUser, toast } = useApp();
  const [items, setItems] = useState<WardrobeItem[] | null>(null);
  const [form, setForm] = useState(blank());
  const [editId, setEditId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => { await ensureUser(); setItems(await api.wardrobe()); };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (p: Partial<typeof form>) => setForm((f) => ({ ...f, ...p }));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      const body = { ...form, brand: form.brand || null, notes: form.notes || null };
      if (body.category !== "footwear") { body.footwear_type = null; body.ankle_support = false; }
      if (editId) await api.updateWardrobe(editId, body); else await api.addWardrobe(body);
      toast(editId ? "Item updated." : "Added. Your trips will use it where it fits.");
      setForm(blank()); setEditId(null); load();
    } catch (e2) { setErr((e2 as Error).message); }
  }

  const grouped = CATS.map(([k, l]) => [k, l, (items ?? []).filter((i) => i.category === k)] as const).filter(([, , v]) => v.length);

  return (
    <main className="page">
      <div className="wrap">
        <div className="page-head"><div><p className="kicker">What you already own</p><h1>Wardrobe</h1></div></div>
        <p className="muted" style={{ maxWidth: "64ch", marginBottom: 24 }}>
          Add the outdoor clothes you have. Every trip uses them first, at zero cost, and tells you honestly if they're fine or not.
          Rough is fine: "medium warm fleece" is enough.
        </p>
        <div className="cols">
          <div className="stack">
            {items === null ? <p className="loading"><span className="spin" /></p> : grouped.length === 0 ? (
              <div className="empty">Nothing here yet. Add your rain jacket, fleece and shoes: they're the pieces that save the most.</div>
            ) : grouped.map(([k, l, list]) => (
              <section key={k}>
                <h2 className="label" style={{ margin: "8px 0" }}>{l}</h2>
                <div className="wgrid">
                  {list.map((i) => (
                    <div className="witem" key={i.id}>
                      <div className="row"><span className="ph-s s"><ProductArt slot={i.category} /></span><h3>{i.name}</h3></div>
                      <span className="small muted">{[i.brand, WARMTH.find((w) => w[0] === i.warmth)?.[1], i.material, i.waterproof && "waterproof", i.windproof && "windproof",
                        i.footwear_type && FOOT.find((f) => f[0] === i.footwear_type)?.[1], i.ankle_support && "ankle support"].filter(Boolean).join(" · ")}</span>
                      <div className="row">
                        <button className="btn sm" type="button" onClick={() => { setEditId(i.id); const { id: _id, ...rest } = i; void _id; setForm(rest); }}>Edit</button>
                        <button className="btn sm danger" type="button" onClick={async () => { await api.deleteWardrobe(i.id); load(); }}>Remove</button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>
          <form className="form panel" onSubmit={save}>
            <h2 style={{ fontSize: 20 }}>{editId ? "Edit item" : "Add an item"}</h2>
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
              <button className="btn primary" type="submit">{editId ? "Save" : "Add to wardrobe"}</button>
              {editId && <button className="btn" type="button" onClick={() => { setEditId(null); setForm(blank()); }}>Cancel</button>}
            </div>
            <p className="small muted">We estimate warmth from the level you pick ({CAT_LABEL[form.category]}). It's an estimate; you can always override the pick on a trip.</p>
          </form>
        </div>
      </div>
    </main>
  );
}
