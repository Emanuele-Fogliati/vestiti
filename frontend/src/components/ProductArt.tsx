// Line drawings per clothing slot. Used when a product has no licensed image.
// (Seed data ships without photos on purpose: brand photos need a licence or a feed.)
const P: Record<string, string> = {
  shell_top: "M30 18l10-6h20l10 6 12 16-8 6-6-6v54H32V34l-6 6-8-6zM40 12q10 10 20 0M50 22v66",
  insulation_top: "M30 18l10-6h20l10 6 12 16-8 6-6-6v54H32V34l-6 6-8-6zM32 40h36M32 54h36M32 68h36M32 82h36",
  mid_top: "M30 18l10-6h20l10 6 12 16-8 6-6-6v54H32V34l-6 6-8-6zM44 12l6 8 6-8M50 20v68",
  base_top: "M32 16l10-4h16l10 4 14 22-8 4-8-12v58H36V30l-8 12-8-4zM42 12q8 6 16 0",
  base_bottom: "M36 12h28l4 76h-12l-6-56-6 56H32z",
  trousers: "M34 12h32l6 76H58l-8-58-8 58H28zM34 22h32M44 12v10M56 12v10",
  shell_bottom: "M34 12h32l6 76H58l-8-58-8 58H28zM34 20h32M30 70h12M58 70h12",
  headwear: "M24 64q0-36 26-36t26 36zM20 64h60v10H20zM50 22a6 6 0 1 1 0 .1",
  gloves: "M34 86V46l-6-14 4-2 8 12V22h4v20-24h4v24-22h4v22-18h4v30l6-10 4 2-8 20v32z",
  sun_hat: "M14 62q36 14 72 0M30 60q0-30 20-30t20 30M30 52h40",
  socks: "M40 12h20v44l14 18q4 10-6 14L44 84q-4-2-4-8z M40 22h20",
  footwear: "M22 40h22l6 18 26 10q8 4 8 12v6H22zM22 76h62M30 40V26h14v14",
};

export function ProductArt({ slot, className = "art" }: { slot: string; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 100 100" aria-hidden="true" fill="none" stroke="currentColor"
      strokeWidth="2.4" strokeLinejoin="round" strokeLinecap="round">
      <path d={P[slot] ?? P.base_top} />
    </svg>
  );
}
