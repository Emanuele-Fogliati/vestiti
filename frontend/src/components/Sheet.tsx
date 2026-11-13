import { useEffect, useState, type ReactNode } from "react";

/** A panel that slides up from the bottom (centred on wide screens). Escape or the scrim closes it. */
export function Sheet({ open, onClose, title, children, wide = false }: {
  open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean;
}) {
  const [mounted, setMounted] = useState(open);
  useEffect(() => { if (open) setMounted(true); }, [open]);
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", k);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", k); document.body.style.overflow = prev; };
  }, [open, onClose]);
  return (
    <>
      <div className={`x-scrim${open ? " open" : ""}`} onClick={onClose} aria-hidden="true" />
      <div className={`x-sheet${open ? " open" : ""}${wide ? " wide" : ""}`} role="dialog" aria-modal="true" aria-label={title} aria-hidden={!open}>
        <div className="x-grab" />
        <div className="x-sheet-h">
          <h2>{title}</h2>
          <button type="button" className="x-close" aria-label="Close" onClick={onClose}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
        <div className="x-sheet-b">{mounted ? children : null}</div>
      </div>
    </>
  );
}
