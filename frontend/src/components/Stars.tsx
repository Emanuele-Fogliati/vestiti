export function Stars({ value, label }: { value: number; label?: string }) {
  const pct = Math.max(0, Math.min(100, (value / 5) * 100));
  return (
    <span className="stars" aria-label={`${value} out of 5${label ? ` ${label}` : ""}`}>
      <span className="st" aria-hidden="true">★★★★★<b style={{ width: `${pct}%` }}>★★★★★</b></span>
      <span>{value.toFixed(1)}{label ? ` ${label}` : ""}</span>
    </span>
  );
}
