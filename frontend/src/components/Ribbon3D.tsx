import { useEffect, useRef, useState } from "react";
import { buildProfile, niceMax, sampleProfile } from "../lib/elevation";
import type { Stop } from "../lib/types";
import { ElevationProfile } from "./ElevationProfile";

const reduced = () => typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** The trip's altitude profile as a 3D ribbon: one slab along the days, a pin per place.
 *  The camera glides to the selected place. Without WebGL it falls back to the flat profile. */
export function Ribbon3D({ stops, active, onPick }: { stops: Stop[]; active: number; onPick: (i: number) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const marks = useRef<HTMLDivElement>(null);
  const activeRef = useRef(active);
  const [flat, setFlat] = useState(false);
  activeRef.current = active;
  const onPickRef = useRef(onPick);
  onPickRef.current = onPick;

  const key = stops.map((s) => `${s.id}:${s.start_date}:${s.end_date}:${s.elevation_m}:${s.activities.map((a) => a.max_altitude_m ?? 0).join(",")}`).join("|");

  useEffect(() => {
    let dead = false;
    let cleanup = () => {};
    (async () => {
      const el = box.current, cv = canvas.current, mk = marks.current;
      if (!el || !cv || !mk) return;
      const { points, bands, days, maxE } = buildProfile(stops);
      if (!points.length) return;
      let T: typeof import("three");
      try { T = await import("three"); } catch { setFlat(true); return; }
      if (dead) return;
      let renderer: import("three").WebGLRenderer;
      try { renderer = new T.WebGLRenderer({ canvas: cv, antialias: true, alpha: true }); } catch { setFlat(true); return; }
      renderer.setPixelRatio(Math.min(2, devicePixelRatio));
      const css = getComputedStyle(el);
      const col = (name: string, fb: string) => new T.Color((css.getPropertyValue(name) || fb).trim() || fb);

      const scene = new T.Scene();
      const cam = new T.PerspectiveCamera(34, 1, 0.1, 800);
      const SPAN = Math.max(40, Math.min(110, days * 4.2));
      const X = (d: number) => (d / Math.max(days, 1) - 0.5) * SPAN;
      const top = niceMax(maxE);
      const H = 9;
      const Y = (e: number) => 0.25 + Math.max(0, e) / top * H;
      const DEPTH = 7;
      const N = Math.max(120, Math.round(days * 24));
      const prof = Array.from({ length: N + 1 }, (_, k) => { const d = (k / N) * days; return [d, sampleProfile(points, d)] as const; });

      const shape = new T.Shape();
      shape.moveTo(X(0), 0);
      prof.forEach(([d, e]) => shape.lineTo(X(d), Y(e)));
      shape.lineTo(X(days), 0);
      shape.lineTo(X(0), 0);
      const geo = new T.ExtrudeGeometry(shape, { depth: DEPTH, bevelEnabled: false, steps: 1 });
      geo.translate(0, 0, -DEPTH / 2);
      const accent = col("--accent", "#FFD60A");
      const side = accent.clone().offsetHSL(0, 0, -0.06);
      const ink = col("--ink", "#0D0D0D");
      const capMat = new T.MeshStandardMaterial({ color: accent, roughness: 0.65 });
      const sideMat = new T.MeshStandardMaterial({ color: side, roughness: 0.8 });
      scene.add(new T.Mesh(geo, [capMat, sideMat]));

      const line = new T.LineBasicMaterial({ color: ink });
      [DEPTH / 2 + 0.01, -DEPTH / 2 - 0.01].forEach((z) => {
        scene.add(new T.Line(new T.BufferGeometry().setFromPoints(prof.map(([d, e]) => new T.Vector3(X(d), Y(e), z))), line));
      });
      bands.slice(1).forEach((b) => {
        const x = X(b.x0), y = Y(sampleProfile(points, b.x0));
        scene.add(new T.Line(new T.BufferGeometry().setFromPoints([
          new T.Vector3(x, y + 0.02, DEPTH / 2 + 0.02), new T.Vector3(x, y + 0.02, -DEPTH / 2 - 0.02), new T.Vector3(x, 0, -DEPTH / 2 - 0.02)]), line));
      });
      const ticks: import("three").Vector3[] = [];
      for (let d = 0; d <= days; d++) ticks.push(new T.Vector3(X(d), 0, DEPTH / 2 + 1), new T.Vector3(X(d), 0, DEPTH / 2 + 2.2));
      scene.add(new T.LineSegments(new T.BufferGeometry().setFromPoints(ticks), new T.LineBasicMaterial({ color: col("--ink-3", "#9A9A92") })));

      const pinGeo = new T.SphereGeometry(0.42, 20, 14);
      const pins = bands.map((b) => {
        const p = new T.Vector3(X(b.peak.x), Y(sampleProfile(points, b.peak.x)) + 0.05, 0);
        const m = new T.Mesh(pinGeo, new T.MeshStandardMaterial({ color: ink, roughness: 0.4 }));
        m.position.copy(p);
        scene.add(m);
        return { p, m };
      });
      scene.add(new T.HemisphereLight(0xffffff, 0xd9d6c8, 0.9 * Math.PI));
      const sun = new T.DirectionalLight(0xffffff, 0.8 * Math.PI);
      sun.position.set(-20, 30, 25);
      scene.add(sun);

      mk.innerHTML = "";
      const labels = bands.map((b, i) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "x-mark";
        btn.textContent = b.name.replace(/\s*\(.*\)$/, "");
        btn.addEventListener("click", () => onPickRef.current(i));
        mk.appendChild(btn);
        return btn;
      });

      const camPos = new T.Vector3(0, 30, 70), look = new T.Vector3(0, 2, 0);
      const want = new T.Vector3(), wantLook = new T.Vector3(), v = new T.Vector3();
      let px = 0, py = 0;
      const move = (e: PointerEvent) => { const r = el.getBoundingClientRect(); px = (e.clientX - r.left) / r.width - 0.5; py = (e.clientY - r.top) / r.height - 0.5; };
      const leave = () => { px = py = 0; };
      el.addEventListener("pointermove", move);
      el.addEventListener("pointerleave", leave);
      const size = () => {
        const w = el.clientWidth, h = el.clientHeight;
        if (!w || !h) return;
        renderer.setSize(w, h, false);
        cam.aspect = w / h;
        cam.updateProjectionMatrix();
      };
      const ro = new ResizeObserver(size);
      ro.observe(el);
      size();
      let visible = true;
      const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; });
      io.observe(el);
      const rm = reduced();
      const t0 = performance.now();
      let first = true, raf = 0;
      const frame = (now: number) => {
        raf = requestAnimationFrame(frame);
        if (!visible || document.hidden || !el.clientWidth) return;
        const t = (now - t0) / 1000;
        const ai = Math.min(activeRef.current, pins.length - 1);
        const a = pins[Math.max(0, ai)];
        const narrow = el.clientWidth < 560;
        const sway = rm ? 0 : Math.sin(t * 0.35) * 2.2;
        wantLook.set(a.p.x * 0.6, a.p.y * 0.6 + 1, 0);
        want.set(a.p.x * 0.6 + 9 + sway + px * 10, 13 + a.p.y * 0.55 - py * 6, narrow ? 50 : 44);
        const k = first || rm ? 1 : 0.045;
        first = false;
        camPos.lerp(want, k);
        look.lerp(wantLook, k);
        cam.position.copy(camPos);
        cam.lookAt(look);
        pins.forEach((q, i) => {
          q.m.scale.setScalar(i === ai ? 1.5 + (rm ? 0 : Math.sin(t * 3) * 0.12) : 1);
        });
        renderer.render(scene, cam);
        const w = el.clientWidth, h = el.clientHeight;
        pins.forEach((q, i) => {
          v.copy(q.p);
          v.y += 0.9;
          v.project(cam);
          const lb = labels[i];
          lb.style.left = `${((v.x + 1) / 2) * w}px`;
          lb.style.top = `${((1 - v.y) / 2) * h}px`;
          lb.style.opacity = v.z < 1 && Math.abs(v.x) < 1.05 && Math.abs(v.y) < 1.05 ? "1" : "0";
          lb.classList.toggle("on", i === ai);
        });
      };
      raf = requestAnimationFrame(frame);
      cleanup = () => {
        cancelAnimationFrame(raf);
        ro.disconnect();
        io.disconnect();
        el.removeEventListener("pointermove", move);
        el.removeEventListener("pointerleave", leave);
        scene.traverse((o) => {
          const m = o as import("three").Mesh;
          m.geometry?.dispose?.();
          const mat = m.material as import("three").Material | import("three").Material[] | undefined;
          if (Array.isArray(mat)) mat.forEach((x) => x.dispose()); else mat?.dispose?.();
        });
        renderer.dispose();
        mk.innerHTML = "";
      };
      if (dead) cleanup();
    })();
    return () => { dead = true; cleanup(); };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const { bands } = buildProfile(stops);
  const b = bands[Math.min(active, bands.length - 1)];
  if (!b) return null;
  if (flat) return <div className="x-ribbon flat"><ElevationProfile stops={stops} selected={active} onSelect={onPick} /></div>;
  return (
    <div className="x-ribbon" ref={box}>
      <canvas ref={canvas} aria-label="Your trip's altitude, day by day, in 3D" role="img" />
      <div className="x-marks" ref={marks} />
      <div className="x-alt">
        <span className="x-k">{b.name}</span>
        <b>{Math.round(b.peak.e).toLocaleString("en-US")} m</b>
      </div>
    </div>
  );
}
