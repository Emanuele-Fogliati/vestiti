export const money = (n: number, currency = "EUR") =>
  new Intl.NumberFormat("en-IE", { style: "currency", currency, maximumFractionDigits: 0 }).format(n);

export const minus = (n: number) => (n < 0 ? "−" + Math.abs(n) : String(n));
export const temp = (n: number) => `${minus(Math.round(n))} °C`;
export const f2 = (n: number) => n.toFixed(2);
export const signed = (n: number) => (n >= 0 ? "+" : "−") + Math.abs(n).toFixed(2);

const D = (s: string) => new Date(s + "T12:00:00Z");
export const dayMonth = (s: string) =>
  D(s).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
export const daysBetween = (a: string, b: string) => Math.round((D(b).getTime() - D(a).getTime()) / 86400000);
export const nights = (a: string, b: string) => daysBetween(a, b) + 1;
export const addDays = (s: string, n: number) => {
  const d = D(s);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};
export const today = () => new Date().toISOString().slice(0, 10);

export const ACTIVITY_LABEL: Record<string, string> = {
  city: "City",
  hiking: "Hiking",
  trek_multiday: "Multi-day trek",
  beach: "Beach",
  ski: "Ski",
  cycling: "Cycling",
  safari: "Safari",
  boat: "Boat, kayak & rafting",
  desert: "Desert & dunes",
  unknown: "Don't know yet",
};

export const activityText = (a: { type: string; difficulty?: string | null; max_altitude_m?: number | null; glacier?: boolean }) => {
  let s = ACTIVITY_LABEL[a.type] ?? a.type;
  if ((a.type === "hiking" || a.type === "trek_multiday") && a.difficulty)
    s += a.difficulty === "unknown" ? " · difficulty?" : ` · ${a.difficulty}`;
  if (a.max_altitude_m) s += ` · ${Math.round(a.max_altitude_m).toLocaleString("en-US")} m`;
  if (a.glacier) s += " · glacier";
  return s;
};

export const STATUS_LABEL = { worn: "Worn", stops: "At stops", pack: "In pack", none: "Not needed" } as const;
export const SOURCE_LABEL: Record<string, string> = {
  forecast: "Forecast",
  climate: "Climate avg",
  observed: "Observed",
  estimate: "Rough estimate",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** [11, 12, 1, 2, 3] -> "Nov–Mar"; [7] -> "Jul". Months run in the order given (they can wrap the year). */
export const monthRange = (ms: number[]) =>
  !ms.length ? "" : ms.length === 1 ? MONTHS[ms[0] - 1] : `${MONTHS[ms[0] - 1]}–${MONTHS[ms[ms.length - 1] - 1]}`;

/** "2027-05-01" -> "May 2027" */
export const monthYear = (s: string) =>
  new Date(`${s}T00:00:00`).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
