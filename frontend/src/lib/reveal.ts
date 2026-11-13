import { useEffect } from "react";

/** Elements with class x-reveal slide in the first time they scroll into view. */
export function useReveal() {
  useEffect(() => {
    const els = [...document.querySelectorAll<HTMLElement>(".x-reveal")];
    if (!("IntersectionObserver" in window) || matchMedia("(prefers-reduced-motion: reduce)").matches) {
      els.forEach((e) => e.classList.add("in"));
      return;
    }
    document.documentElement.classList.add("x-js");
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: 0.15 });
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, []);
}
