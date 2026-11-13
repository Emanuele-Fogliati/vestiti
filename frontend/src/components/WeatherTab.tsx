import { useEffect, useMemo, useRef, useState } from "react";
import { dayMonth, minus } from "../lib/format";
import type { Strategy } from "../lib/types";

const deg = (n: number) => `${minus(Math.round(n))}°`;
const reduced = () => typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Wind streaks behind the coldest-hour number: they move as fast as the chosen day's wind. */
function WindStreaks({ kmh }: { kmh: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const speed = useRef(kmh);
  speed.current = kmh;
  useEffect(() => {
    const c = ref.current;
    const ctx = c?.getContext("2d");
    if (!c || !ctx) return;
    const rm = reduced();
    const P = Array.from({ length: 56 }, () => ({ x: Math.random(), y: Math.random(), l: 0.04 + Math.random() * 0.12, s: 0.5 + Math.random() }));
    let W = 0, H = 0, raf = 0;
    const dpr = Math.min(2, devicePixelRatio || 1);
    const size = () => { W = c.width = c.clientWidth * dpr; H = c.height = c.clientHeight * dpr; };
    const ro = new ResizeObserver(size);
    ro.observe(c);
    size();
    const col = getComputedStyle(c).color;
    const draw = () => {
      raf = requestAnimationFrame(draw);
      if (document.hidden || !W) return;
      const v = Math.max(4, speed.current);
      ctx.clearRect(0, 0, W, H);
      ctx.strokeStyle = col;
      ctx.lineWidth = 1.4 * dpr;
      ctx.lineCap = "round";
      for (const p of P) {
        if (!rm) p.x += (p.s * v) / 9000;
        if (p.x - p.l > 1) { p.x = -0.05; p.y = Math.random(); }
        const y = p.y * H + Math.sin((p.x + p.y) * 9) * 6 * dpr;
        ctx.globalAlpha = 0.25 + 0.35 * p.s / 1.5;
        ctx.beginPath();
        ctx.moveTo((p.x - (p.l * v) / 45) * W, y);
        ctx.lineTo(p.x * W, y);
        ctx.stroke();
      }
    };
    draw();
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, []);
  return <canvas ref={ref} className="x-wind" aria-hidden="true" />;
}

export function WeatherTab({ strategy }: { strategy: Strategy }) {
  const days = useMemo(() => strategy.stages.flatMap((s, si) => s.days.map((d) => ({ ...d, si }))), [strategy]);
  const coldest = useMemo(() => {
    let best: { si: number; c: Strategy["stages"][number]["modes"]["rest"]["condition"] } | null = null;
    strategy.stages.forEach((s, si) => {
      const c = s.modes.rest.condition;
      if (!best || c.feels_like_c < best.c.feels_like_c) best = { si, c };
    });
    return best as { si: number; c: Strategy["stages"][number]["modes"]["rest"]["condition"] } | null;
  }, [strategy]);
  const coldIdx = Math.max(0, days.findIndex((d) => coldest && d.date === coldest.c.date && d.si === coldest.si));
  const [sel, setSel] = useState(coldIdx);
  useEffect(() => { setSel(coldIdx); }, [coldIdx]);
  if (!days.length || !coldest) return null;

  const d = days[Math.min(sel, days.length - 1)];
  const lo = Math.floor(Math.min(...days.map((x) => x.tmin), coldest.c.feels_like_c, 0) / 5) * 5;
  const hi = Math.ceil(Math.max(...days.map((x) => x.tmax), lo + 10) / 5) * 5;
  const pct = (t: number) => ((t - lo) / (hi - lo)) * 100;
  const coldOn = new Map(strategy.stages.map((s, si) => [`${si}:${s.modes.rest.condition.date}`, s.modes.rest.condition.feels_like_c]));
  const sources = new Set(strategy.stages.flatMap((s) => s.weather_sources));
  const srcText = sources.has("estimate") ? "rough estimate" : sources.has("forecast") ? "real forecast" : "climate averages";
  const wide = days.length > 18;

  return (
    <div className="x-weather">
      <div className="x-cold x-rise">
        <WindStreaks kmh={d.wind_kmh} />
        <div className="x-cold-in">
          <div className="x-cold-n">{deg(coldest.c.feels_like_c)}</div>
          <div className="x-cold-t">
            <b>The coldest hour</b>
            <span>{strategy.stages[coldest.si].name}{coldest.c.where && coldest.c.where !== strategy.stages[coldest.si].name ? ` (${coldest.c.where})` : ""}, {dayMonth(coldest.c.date)}. Feels {deg(coldest.c.feels_like_c)} with {Math.round(coldest.c.wind_kmh)} km/h wind. Your bag is sized for this.</span>
          </div>
        </div>
      </div>

      <div className="x-rise">
        <div className={`x-days-scroll${wide ? " wide" : ""}`}>
          <div className="x-days" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(${wide ? "30px" : "0"}, 1fr))` }}>
            {days.map((x, i) => {
              const cold = coldOn.get(`${x.si}:${x.date}`);
              return (
                <button key={`${x.si}-${x.date}`} type="button" className="x-day" style={{ gridColumn: i + 1, gridRow: 1 }} aria-pressed={i === sel} onClick={() => setSel(i)}
                  aria-label={`${dayMonth(x.date)}, ${strategy.stages[x.si].name}: ${deg(x.tmin)} to ${deg(x.tmax)}, wind ${Math.round(x.wind_kmh)} km/h`}>
                  <span className="dn">{Number(x.date.slice(8))}</span>
                  <span className="bw">
                    <span className="bar" style={{ bottom: `${pct(x.tmin)}%`, height: `${Math.max(2, pct(x.tmax) - pct(x.tmin))}%`, animationDelay: `${i * 30}ms` }} />
                    {cold !== undefined && <span className="feel" style={{ bottom: `calc(${pct(cold)}% - 4px)`, animationDelay: `${300 + i * 30}ms` }} />}
                  </span>
                  <span className="w"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M3 8h10a3 3 0 1 0-3-3M3 13h15a3 3 0 1 1-3 3M3 18h7" /></svg>{Math.round(x.wind_kmh)}</span>
                </button>
              );
            })}
            {strategy.stages.map((s, si) => {
              const a = days.findIndex((x) => x.si === si), n = s.days.length;
              return a < 0 ? null : <span key={s.index} className="x-band" style={{ gridColumn: `${a + 1} / span ${n}`, gridRow: 2 }} title={s.name}>{s.name}</span>;
            })}
          </div>
        </div>
        <div className="x-legend">
          <span><i className="lg-range" />Low to high</span>
          <span><i className="lg-feel" />Coldest feels-like at each place</span>
          <span className="x-tag">{srcText}</span>
        </div>
        <div className="x-stats" aria-live="polite">
          <div><b>{dayMonth(d.date)}</b><span>{strategy.stages[d.si].name}</span></div>
          <div><b>{deg(d.tmin)} / {deg(d.tmax)}</b><span>Low / high</span></div>
          <div><b>{Math.round(d.wind_kmh)} km/h</b><span>Wind</span></div>
          <div><b>{d.precip_mm.toFixed(1)} mm</b><span>Rain · {Math.round(d.precip_prob)}% chance</span></div>
        </div>
      </div>
    </div>
  );
}
