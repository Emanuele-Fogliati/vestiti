import { useEffect, useState } from "react";
import type { Terrain } from "../lib/terrain";
import type { StopArt } from "../lib/types";

// Flat vector scenes drawn only with --il-* tokens, so they recolour with the theme.
// The first four come from the round-2 design (Patagonia stops); the rest follow the same style.
const ART: Record<Terrain, string> = {
  alpine:
    '<rect width="300" height="200" fill="var(--il-sky)"/><circle cx="236" cy="50" r="17" fill="var(--il-sun)"/><path d="M0 132L50 112L90 122L140 100L190 116L240 104L300 118V200H0Z" fill="var(--il-far)"/><path d="M0 200V136L40 116L70 124L100 84L112 98L128 42L140 72L150 28L162 76L180 62L200 102L240 92L300 124V200Z" fill="var(--il-mid)"/><path d="M128 42L140 72L132 78Z M150 28L162 76L154 72Z M100 84L112 98L104 102Z" fill="var(--il-ice)"/><path d="M70 160Q150 150 230 162Q150 172 70 160Z" fill="var(--il-water)"/><path d="M0 200V170Q80 156 150 174Q230 190 300 166V200Z" fill="var(--il-near)"/>',
  glacier:
    '<rect width="300" height="200" fill="var(--il-sky)"/><circle cx="60" cy="44" r="15" fill="var(--il-sun)"/><path d="M0 116L60 92L120 104L180 82L240 98L300 88V130H0Z" fill="var(--il-mid)"/><path d="M0 150H300V200H0Z" fill="var(--il-water)"/><path d="M0 118L300 108V150L280 140L265 152L248 141L230 153L212 142L195 152L178 140L160 152L140 141L122 153L104 142L86 152L68 141L50 153L32 142L14 152L0 144Z" fill="var(--il-ice)" stroke="var(--il-far)" stroke-width="1.2"/><path d="M40 124V146M90 122V148M150 120V146M210 118V148M260 116V146" stroke="var(--il-far)" stroke-width="1.2"/>',
  hills:
    '<rect width="300" height="200" fill="var(--il-sky)"/><circle cx="238" cy="46" r="16" fill="var(--il-sun)"/><path d="M0 200V150L60 130L90 140L110 120H190L210 135L250 125L300 145V200Z" fill="var(--il-mid)"/><path d="M112 122L118 50L126 44L132 122Z M138 122L146 30L154 26L160 122Z M166 122L172 56L180 52L186 122Z" fill="var(--il-near)"/><path d="M0 172Q150 160 300 176V200H0Z" fill="var(--il-water)"/>',
  coast:
    '<rect width="300" height="200" fill="var(--il-sky)"/><circle cx="70" cy="40" r="14" fill="var(--il-sun)"/><path d="M0 130L50 90L90 110L140 68L190 100L240 80L300 110V152H0Z" fill="var(--il-mid)"/><path d="M140 68L156 80L134 76Z M240 80L256 90L232 88Z M50 90L62 98L44 96Z" fill="var(--il-ice)"/><path d="M0 150H300V200H0Z" fill="var(--il-water)"/><path d="M190 160Q212 146 236 160Z" fill="var(--il-near)"/><rect x="208" y="130" width="8" height="24" fill="var(--il-near)"/><rect x="206" y="126" width="12" height="6" fill="var(--il-near)"/>',
  city:
    '<rect width="300" height="200" fill="var(--il-sky)"/><circle cx="232" cy="46" r="15" fill="var(--il-sun)"/><path d="M0 150L40 140L90 146L150 132L210 144L300 136V200H0Z" fill="var(--il-far)"/><path d="M20 200V112H48V96H62V112H76V200Z M92 200V84L110 70L128 84V200Z M144 200V104H160V60H176V104H192V200Z M206 200V120H226V100H244V120H262V200Z M272 200V128H296V200Z" fill="var(--il-mid)"/><path d="M168 60L168 44" stroke="var(--il-mid)" stroke-width="2"/><path d="M0 184H300V200H0Z" fill="var(--il-near)"/><path d="M100 98H120M100 116H120M100 134H120M152 118H184M152 136H184" stroke="var(--il-ice)" stroke-width="3"/>',
  snow:
    '<rect width="300" height="200" fill="var(--il-sky)"/><circle cx="64" cy="46" r="15" fill="var(--il-sun)"/><path d="M0 120L70 64L120 100L180 50L250 96L300 76V200H0Z" fill="var(--il-mid)"/><path d="M70 64L92 82L80 90L58 74Z M180 50L204 70L188 78L168 62Z M250 96L268 84L282 92L262 104Z" fill="var(--il-ice)"/><path d="M0 150Q80 128 160 150T300 140V200H0Z" fill="var(--il-ice)"/><path d="M40 170L120 150M150 186L250 156" stroke="var(--il-far)" stroke-width="2" stroke-dasharray="6 5"/><path d="M220 120V150M214 132H226" stroke="var(--il-near)" stroke-width="3"/>',
  desert:
    '<rect width="300" height="200" fill="var(--il-sky)"/><circle cx="228" cy="52" r="20" fill="var(--il-sun)"/><path d="M0 150Q60 120 120 146T240 132T300 140V200H0Z" fill="var(--il-far)"/><path d="M0 176Q90 150 170 172T300 164V200H0Z" fill="var(--il-mid)"/><path d="M60 150V118M60 128Q48 128 48 116M60 134Q72 134 72 122" stroke="var(--il-near)" stroke-width="5" stroke-linecap="round" fill="none"/><path d="M0 194H300V200H0Z" fill="var(--il-near)"/>',
  savanna:
    '<rect width="300" height="200" fill="var(--il-sky)"/><circle cx="210" cy="70" r="26" fill="var(--il-sun)"/><path d="M0 150Q150 136 300 150V200H0Z" fill="var(--il-far)"/><path d="M80 150V112M54 112Q80 92 106 112Z" fill="var(--il-near)" stroke="var(--il-near)" stroke-width="4"/><path d="M220 152V124M200 124Q220 108 240 124Z" fill="var(--il-near)" stroke="var(--il-near)" stroke-width="3"/><path d="M0 180Q150 168 300 182V200H0Z" fill="var(--il-mid)"/>',
};

// Landmark scenes (Machu Picchu, Cusco cathedral...) come from the API as SVG fragments drawn
// with the same --il-* tokens. Each one is fetched once per page load and shared by every card.
const landmarkCache = new Map<string, Promise<string | null>>();

export function loadLandmark(id: string): Promise<string | null> {
  let p = landmarkCache.get(id);
  if (!p) {
    p = fetch(`/api/art/landmarks/${encodeURIComponent(id)}.svg`)
      .then((r) => (r.ok ? r.text() : null))
      .catch(() => null);
    landmarkCache.set(id, p);
  }
  return p;
}

function useLandmark(id?: string): string | null {
  const [svg, setSvg] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setSvg(null);
    if (id) loadLandmark(id).then((s) => { if (live) setSvg(s); });
    return () => { live = false; };
  }, [id]);
  return svg;
}

/** A stop's scene: its landmark when we have one, otherwise (and while it loads) the generic terrain. */
export function Illustration({ terrain, art, label }: { terrain: Terrain; art?: StopArt | null; label?: string }) {
  const landmark = useLandmark(art?.kind === "landmark" ? art.id : undefined);
  const name = label ?? (landmark ? art?.label : undefined);
  return (
    <figure className="thumb">
      <svg viewBox="0 0 300 200" preserveAspectRatio="xMidYMid slice" role={name ? "img" : undefined}
        aria-label={name} aria-hidden={name ? undefined : true}
        dangerouslySetInnerHTML={{ __html: landmark ?? ART[terrain] }} />
    </figure>
  );
}
