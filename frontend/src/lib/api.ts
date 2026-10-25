import type {
  AppConfig, ChatReply, DraftStop, Profile, QuizResult, Place, Plans, Stop, Strategy, Tier, Trip, TripSummary, User, WardrobeItem,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type FieldError = { type?: string; msg?: string; loc?: (string | number)[]; ctx?: Record<string, unknown> };

/** Turn FastAPI/pydantic validation errors into sentences a traveller understands. */
export function friendlyError(d: FieldError): string {
  const field = String(d.loc?.[d.loc.length - 1] ?? "");
  const what = field === "text" ? "Your trip description" : field ? field.replace(/_/g, " ") : "This field";
  const n = (k: string) => Number(d.ctx?.[k] ?? 0).toLocaleString("en-US");
  switch (d.type) {
    case "string_too_long": return `${what} is too long: the limit is ${n("max_length")} characters.`;
    case "string_too_short": return `${what} is too short: write at least ${n("min_length")} characters.`;
    case "missing": return `${what} is missing.`;
    case "value_error": return (d.msg ?? "").replace(/^Value error, /, "");
    default: return d.msg ? `${what}: ${d.msg.charAt(0).toLowerCase()}${d.msg.slice(1)}.` : "Something in the form is not valid.";
  }
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: {
      "X-Requested-With": "app",
      ...(body !== undefined && !(body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
    },
    body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = data?.detail;
    const msg = typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map(friendlyError).join(" ")
      : `Request failed (${res.status})`;
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

export type StopInput = Omit<Stop, "id" | "position"> & { position?: number };

export const api = {
  config: () => req<AppConfig>("GET", "/api/config"),
  me: () => req<User>("GET", "/api/me"),
  guest: () => req<User>("POST", "/api/auth/guest"),
  register: (email: string, password: string, display_name?: string) =>
    req<User>("POST", "/api/auth/register", { email, password, display_name }),
  login: (email: string, password: string) => req<User>("POST", "/api/auth/login", { email, password }),
  logout: () => req<void>("POST", "/api/auth/logout"),
  updateMe: (patch: Partial<Pick<User, "display_name" | "gender_pref" | "thermal_offset" | "pace" | "evenings">>) =>
    req<User>("PATCH", "/api/me", patch),
  profile: () => req<Profile>("GET", "/api/me/profile"),
  quiz: (answers: { cold?: string | null; pace?: string | null; evenings?: string | null; owned?: string[] | null }, tripId?: string, tier?: Tier) => {
    const q = new URLSearchParams();
    if (tripId) q.set("trip_id", tripId);
    if (tier) q.set("tier", tier);
    return req<QuizResult>("POST", `/api/me/quiz?${q}`, answers);
  },
  chat: (tripId: string, message: string, tier: Tier) =>
    req<ChatReply>("POST", `/api/trips/${tripId}/chat`, { message, tier }),
  exportMe: () => req<unknown>("GET", "/api/me/export"),
  deleteMe: () => req<void>("DELETE", "/api/me"),

  trips: () => req<TripSummary[]>("GET", "/api/trips"),
  trip: (id: string) => req<Trip>("GET", `/api/trips/${id}`),
  createTrip: (name: string, stops: StopInput[] = []) => req<Trip>("POST", "/api/trips", { name, stops }),
  patchTrip: (id: string, patch: { name?: string; notes?: string }) => req<Trip>("PATCH", `/api/trips/${id}`, patch),
  deleteTrip: (id: string) => req<void>("DELETE", `/api/trips/${id}`),
  duplicateTrip: (id: string) => req<Trip>("POST", `/api/trips/${id}/duplicate`),
  addStop: (id: string, stop: StopInput) => req<Stop>("POST", `/api/trips/${id}/stops`, stop),
  patchStop: (id: string, stopId: string, patch: Partial<StopInput>) =>
    req<Stop>("PATCH", `/api/trips/${id}/stops/${stopId}`, patch),
  deleteStop: (id: string, stopId: string) => req<void>("DELETE", `/api/trips/${id}/stops/${stopId}`),
  reorder: (id: string, stop_ids: string[]) => req<Trip>("POST", `/api/trips/${id}/stops/reorder`, { stop_ids }),

  strategy: (id: string, tier: Tier) => req<Strategy>("GET", `/api/trips/${id}/strategy?tier=${tier}`),
  plans: (id: string) => req<Plans>("GET", `/api/trips/${id}/plans`),
  slotProducts: (id: string, slot: string, params: Record<string, string | boolean | undefined>) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== "" && v !== false) q.set(k, String(v)); });
    return req<{ items: import("./types").Item[]; brands: string[]; requirement: import("./types").Requirement; slot_name: string }>(
      "GET", `/api/trips/${id}/slots/${slot}/products?${q}`);
  },
  select: (id: string, body: { tier: Tier; slot: string; choice: string; product_id?: string; wardrobe_item_id?: string }) =>
    req<{ ok: boolean }>("PUT", `/api/trips/${id}/selections`, body),
  resetSelections: (id: string, tier?: Tier) =>
    req<{ ok: boolean }>("DELETE", `/api/trips/${id}/selections${tier ? `?tier=${tier}` : ""}`),

  geocode: (q: string) => req<{ results: Place[] }>("GET", `/api/geocode?q=${encodeURIComponent(q)}`),
  parseItinerary: (text: string) =>
    req<{ trip_name: string | null; stops: DraftStop[]; questions: string[]; parser: string }>(
      "POST", "/api/ai/parse-itinerary", { text }),
  explain: (id: string, body: { topic: string; stage_index?: number; slot?: string; tier: Tier }) =>
    req<{ text: string; source: string; model: string | null }>("POST", `/api/trips/${id}/explain`, body),
  ask: (id: string, question: string, tier: Tier) =>
    req<{ text: string; source: string; model: string | null }>("POST", `/api/trips/${id}/ask`, { question, tier }),

  wardrobe: () => req<WardrobeItem[]>("GET", "/api/wardrobe"),
  addWardrobe: (item: Omit<WardrobeItem, "id">) => req<WardrobeItem>("POST", "/api/wardrobe", item),
  updateWardrobe: (id: string, item: Omit<WardrobeItem, "id">) => req<WardrobeItem>("PUT", `/api/wardrobe/${id}`, item),
  deleteWardrobe: (id: string) => req<void>("DELETE", `/api/wardrobe/${id}`),

  adminStats: () => req<Record<string, unknown>>("GET", "/api/admin/stats"),
  adminFeeds: () => req<{ networks: string[]; imports: Record<string, unknown>[] }>("GET", "/api/admin/feeds"),
  adminImport: (form: FormData) => req<Record<string, unknown>>("POST", "/api/admin/feeds/import", form),
};

export const buyUrl = (productId: string, tripId?: string, tier?: Tier, slot?: string) => {
  const q = new URLSearchParams();
  if (tripId) q.set("trip_id", tripId);
  if (tier) q.set("tier", tier);
  if (slot) q.set("slot", slot);
  return `/api/go/product/${productId}?${q}`;
};

export const rentUrl = (r: { partner_id: string; slot: string; start: string; end: string; country: string | null }, tripId?: string) => {
  const q = new URLSearchParams({ slot: r.slot, start: r.start, end: r.end });
  if (r.country) q.set("country", r.country);
  if (tripId) q.set("trip_id", tripId);
  return `/api/go/rental/${r.partner_id}?${q}`;
};
