export type Tier = "cheap" | "medium" | "premium";
export const TIERS: Tier[] = ["cheap", "medium", "premium"];
export const TIER_LABEL: Record<Tier, string> = { cheap: "Cheap", medium: "Medium", premium: "Premium" };

export interface User {
  id: string;
  email: string | null;
  display_name: string | null;
  is_guest: boolean;
  is_admin: boolean;
  gender_pref: "men" | "women" | "any";
  thermal_offset: number;
  pace: Pace;
  evenings: Evenings;
  profile_done_at: string | null;
  created_at: string;
}

export type Cold = "very_cold" | "bit_cold" | "average" | "warm";
export type Pace = "relaxed" | "average" | "brisk";
export type Evenings = "early" | "sometimes" | "late";

export interface Profile {
  cold: Cold;
  thermal_offset: number;
  pace: Pace;
  evenings: Evenings;
  owned: string[];
  done: boolean;
  basics: { key: string; label: string }[];
}

export interface PlanDiff {
  tier: Tier;
  pieces: { slot: string; slot_name: string; before: string; after: string; cost_delta: number }[];
  totals: { tier: Tier; before: number; after: number }[];
  status: { before: string; after: string } | null;
  owned: string[];
}

export interface ProfileUndo {
  profile: { thermal_offset: number; pace: Pace; evenings: Evenings };
  wardrobe_ids: string[];
}

export interface QuizResult {
  profile: Profile;
  changes: string[];
  undo: ProfileUndo;
  plan: PlanDiff;
}

export type ChatReply =
  | { kind: "answer"; text: string; source: string; reader: string }
  | { kind: "update"; text: string; changes: string[]; plan: PlanDiff; undo: ProfileUndo; profile: Profile; reader: string };

export interface Activity {
  type: string;
  difficulty?: string | null;
  max_altitude_m?: number | null;
  glacier?: boolean;
}

export interface Stop {
  id: string;
  position: number;
  name: string;
  country_code: string | null;
  latitude: number;
  longitude: number;
  elevation_m: number;
  start_date: string;
  end_date: string;
  activities: Activity[];
  notes: string | null;
  /** The place's own landmark scene, when the library has one near this stop. */
  art?: StopArt | null;
  /** Other places seen during the stop's days (Moray, Maras... on a Cusco day), in order. */
  visits?: Visit[];
  /** The traveller did not say how long: the days are a guess. */
  days_estimated?: boolean;
  /** What the place is and a fun fact, when we know the place. */
  guide?: PlaceGuide | null;
}

export interface PlaceGuide { blurb: string; fun_fact: string; source: string }

export interface Visit {
  name: string;
  date?: string | null;
  art?: StopArt | null;
}

/** What of a trip's dates is a guess. */
export interface TripEstimate {
  start: boolean;
  days: boolean;
  total_days: number | null;
}

export interface StopArt {
  kind: "landmark";
  id: string;
  label: string;
}

export interface Trip {
  id: string;
  name: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
  stops: Stop[];
  start_estimated?: boolean;
  estimate?: TripEstimate | null;
  /** Slug of the recommended trip it started from; null = the traveller's own. */
  source_itinerary?: string | null;
}

export interface TripSummary {
  id: string;
  name: string;
  stop_count: number;
  start_date: string | null;
  end_date: string | null;
  places: string[];
  updated_at: string;
  /** The first landmark of the trip, for the card. */
  art?: StopArt | null;
  estimated?: boolean;
  source_itinerary?: string | null;
}

export interface Place {
  name: string;
  admin?: string | null;
  country?: string | null;
  country_code?: string | null;
  latitude: number;
  longitude: number;
  elevation_m: number;
  source?: string;
}

export interface Fit {
  stars: number;
  score: number;
  passes: boolean;
  issues: string[];
  positives: string[];
}

export interface Specs {
  clo?: number;
  waterproof_mm?: number;
  waterproof?: boolean;
  windproof?: boolean;
  breathability_g?: number;
  weight_g?: number;
  packable?: boolean;
  insulation?: string;
  fill_power?: number;
  footwear_type?: string;
  ankle_support?: boolean;
  insulated?: boolean;
  features?: string[];
  estimated?: string[];
}

export interface Item {
  id: string;
  source: "product" | "owned";
  slot: string;
  name: string;
  brand: string;
  merchant: string;
  price: number;
  currency: string;
  image_url: string | null;
  specs: Specs;
  rating: number | null;
  review_count: number;
  network: string;
  gender: string;
  fit: Fit | null;
}

export interface Requirement {
  slot: string;
  code: string;
  name: string;
  needed: boolean;
  level: string;
  ref_clo: number;
  waterproof: boolean;
  waterproof_grade_mm: number;
  windproof: boolean;
  footwear_type: string | null;
  ankle_support: boolean;
  insulated: boolean;
  breathable_high: boolean;
  packable: boolean;
  reasons: string[];
  stages: number[];
  days_needed: number;
  trip_days: number;
}

export interface Rental {
  partner_id: string;
  partner: string;
  slot: string;
  days: number;
  daily_rate: number;
  price: number;
  currency: string;
  is_placeholder: boolean;
  start: string;
  end: string;
  country: string | null;
  saving?: number;
}

export interface KitLine {
  slot: string;
  code: string;
  slot_name: string;
  kind: "product" | "owned" | "have" | "rent" | "none";
  locked: boolean;
  assumed: boolean;
  note: string | null;
  item: Item | null;
  rental: Rental | null;
  rent_suggestion: Rental | null;
  rental_options: Rental[];
  alternatives: number;
  owned_alternatives: Item[];
  requirement: Requirement;
  cost: number;
  owned_verdict: "fine" | "works" | null;
}

export interface MarginRow { required: number; provided: number; margin: number; status: Status }
export type Status = "covered" | "marginal" | "cold";

export interface TierPlan {
  tier: Tier;
  items: KitLine[];
  totals: {
    buy: number; rent: number; total: number; owned_value_saved: number;
    items_to_buy: number; items_owned: number; items_rented: number; weight_g: number;
  };
  warmth: { status: Status; margins: { moving: number; rest: number };
    stages: { index: number; name: string; moving: MarginRow; rest: MarginRow }[] };
  auto_upgrades: { slot: string; reason: string; extra_cost: number; to: Item; from: Item | null; added: boolean }[];
  shortfall: { stage: string; mode: "moving" | "rest"; gap_clo: number; feels_like_c: number | null;
    missing: string[]; message: string; avoidable: boolean } | null;
  advice: { tier: Tier; extra_cost: number; message: string } | null;
  owned_notes: { slot: string; verdict: string; message: string; item: Item }[];
  owned_fine_count: number;
}

export interface Question { stop_id: string | null; field: string; question: string; options: string[] }

export interface Plans {
  empty: boolean;
  message?: string;
  tiers: Record<Tier, TierPlan>;
  comparison: { tier: Tier; total: number; status: Status }[];
  requirements: Record<string, Requirement>;
  questions: Question[];
  currency: string;
  model_note: string;
  catalog_note: string | null;
}

export interface Condition {
  date: string; mode: string; activity: string; temp_c: number; feels_like_c: number;
  wind_kmh: number; precip_mm: number; precip_prob: number; wet: boolean; snow: boolean;
  altitude_m: number; where: string; source: string;
}

export interface CrossSection {
  outside_c: number; skin_c: number; wind_kmh: number; precip_mm: number;
  layers: { slot: string; code: string; name: string; item: string; clo: number; worn: boolean }[];
  interfaces: { slot: string; outer_temp_c: number }[];
}

export interface Upgrade {
  stage_index: number; mode: string; slot: string; slot_name: string; item: Item;
  gain_clo: number; extra_cost: number; closes: boolean; margin_before: number; margin_after: number;
  condition: { date: string; where: string; feels_like_c: number };
}

export interface ModeResult extends MarginRow {
  condition: Condition; penalties: string[]; worn: string[]; cross_section: CrossSection;
}

export type SlotStatus = "worn" | "stops" | "pack" | "none";

export interface Day {
  date: string; tmax: number; tmin: number; precip_mm: number; precip_prob: number;
  wind_kmh: number; source: string; uv: number | null; tmin_p10: number | null;
}

export interface Stage {
  index: number; stop_id: string; name: string; start: string; end: string;
  elevation_m: number; activities: string[]; max_altitude_m: number; days: Day[];
  weather_sources: string[];
  slots: Record<string, { status: SlotStatus; days_worn: number; days_stops: number; days_total: number; why: string }>;
  modes: { moving: ModeResult; rest: ModeResult };
  exceptions: { date: string; summary: string }[];
  notes: string[];
  upgrades: { moving: Upgrade | null; rest: Upgrade | null };
}

export interface Strategy {
  empty: boolean;
  message?: string;
  tier: Tier;
  slots: { key: string; code: string; name: string; torso: boolean }[];
  kit: Record<string, { name: string; clo: number; source: string; ref_id: string | null; waterproof: boolean; windproof: boolean }>;
  stages: Stage[];
  margins: { moving: number; rest: number };
  status: Status;
  requirements: Record<string, Requirement>;
  questions: Question[];
  totals: TierPlan["totals"];
  model_note: string;
}

export interface AppConfig {
  brand: { name: string; tagline: string; domain: string; support_email: string };
  theme: string;
  currency: string;
  ai: { enabled: boolean; available: boolean; model: string };
  slots: { key: string; code: string; name: string; torso: boolean }[];
  activity_types: string[];
  difficulties: string[];
  warmth_levels: string[];
  footwear_types: string[];
  disclosure: string;
}

export interface WardrobeItem {
  id: string;
  category: string;
  name: string;
  brand: string | null;
  warmth: string;
  clo_override: number | null;
  waterproof: boolean;
  windproof: boolean;
  material: string | null;
  footwear_type: string | null;
  ankle_support: boolean;
  notes: string | null;
  model_ref?: string | null;
  added_via?: "hand" | "search" | "photo" | null;
  specs?: { fill_power?: number; waterproof_mm?: number } | null;
}

/** A model the traveller may own: from the shop, the known older models, an estimate or a photo. */
export interface ModelMatch {
  ref: string | null;
  source: "shop" | "known" | "estimate" | "photo";
  brand: string | null;
  name: string;
  category: string;
  warmth: string;
  waterproof: boolean;
  windproof: boolean;
  material: string | null;
  footwear_type: string | null;
  ankle_support: boolean;
  older: boolean;
  note: string | null;
  score?: number;
  by?: "ai" | "rules";
}

export interface PhotoReading {
  seen: { brand: string | null; model: string | null; style_code: string | null; text: string[]; colour: string | null;
    features: string[]; label_readable: boolean; confidence: "low" | "medium" | "high" };
  results: ModelMatch[];
  described: ModelMatch | null;
}

export interface DraftStop {
  name: string;
  start_date: string;
  end_date: string;
  activities: Activity[];
  matches: Place[];
  place: Place | null;
  visits: Visit[];
  days_estimated: boolean;
}

/** A ready-made itinerary on the "Looking for ideas?" list. */
export interface ItineraryCard {
  slug: string;
  title: string;
  countries: string[];
  summary: string;
  days: number;
  best_months: number[];
  highest_m: number;
  places: string[];
  art: StopArt | null;
}

export interface ExcursionLink { provider: string; label: string; href: string }

/** One stop of an itinerary: the same shape as a trip stop, plus the day plan and tips. */
export interface ItineraryStop extends Stop {
  plan: string[];
  do: string[];
  skip: string[];
  excursions: { title: string; links: ExcursionLink[] }[];
}

export interface Itinerary extends ItineraryCard {
  season_note: string;
  start_date: string;
  stops: ItineraryStop[];
  group_trips: { operator: string; title: string; days: number; href: string }[];
}
