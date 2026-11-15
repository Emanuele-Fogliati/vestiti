/** Line icons of the pieces of a kit, one per slot, drawn on a 24 px grid with the stroke of the app.
 *  "trousers@warm" (a lighter piece only the hot places get) uses the icon of its base slot. */
const G: Record<string, string> = {
  base_top: "M8 4 4 7l2 3 2-1v11h8V9l2 1 2-3-4-3c-1 1.3-2.4 2-4 2s-3-.7-4-2zM9 12h6",
  mid_top: "M8 4 4 7v13h16V7l-4-3M8 4c1 1.2 2.4 1.8 4 1.8S15 5.2 16 4M12 5.8V20M9 9v11M15 9v11",
  insulation_top: "M8 4 4 7v13h16V7l-4-3c-1 1.2-2.4 1.8-4 1.8S9 5.2 8 4zM4 11h16M4 15.5h16M12 5.8V20",
  shell_top: "M9 3.5c.6-.9 1.8-1.5 3-1.5s2.4.6 3 1.5l5 3.5v13h-5v-9M9 3.5 4 7v13h5v-9M9 3.5c.4 2 1.4 3.2 3 3.2s2.6-1.2 3-3.2M12 6.7V20",
  base_bottom: "M7 3h10l1 18h-4l-2-11-2 11H6zM7 7h10",
  trousers: "M7 3h10l1 18h-4l-2-11-2 11H6z",
  shell_bottom: "M7 3h10l1 18h-4l-2-11-2 11H6zM9.5 3v4M14.5 3v4",
  headwear: "M5 15a7 7 0 0 1 14 0zM4 15h16v3.5H4zM12 8V5.5",
  gloves: "M7 21v-6L4.5 11a1.5 1.5 0 0 1 2.5-1.6L9 12V5a1.5 1.5 0 0 1 3 0v5-6a1.5 1.5 0 0 1 3 0v6-4a1.5 1.5 0 0 1 3 0v9c0 3-1.5 6-4 6zM7 18h9",
  sun_hat: "M3 15c2.5 1.5 15.5 1.5 18 0M7 15c0-4 2-7 5-7s5 3 5 7",
  socks: "M8 3h7v9l3.5 3.5a3 3 0 0 1-4.2 4.2L8.6 14A2 2 0 0 1 8 12.6zM8 7h7",
  footwear: "M7 3h5v8.5l5.6 2.6c1.4.7 2.4 1.9 2.4 3.4V20H5V11zM5 17h15M12 7h-2.5M12 9.5h-2.5",
};

export const baseSlot = (slot: string) => slot.split("@")[0];

export function Garment({ slot, title }: { slot: string; title?: string }) {
  const d = G[baseSlot(slot)] ?? G.base_top;
  return (
    <svg className="g-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"
      role={title ? "img" : undefined} aria-label={title} aria-hidden={title ? undefined : true}>
      {title && <title>{title}</title>}
      <path d={d} />
      {baseSlot(slot) === "headwear" && <circle cx="12" cy="4.5" r="1.2" />}
    </svg>
  );
}
