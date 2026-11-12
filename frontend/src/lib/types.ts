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
  /** Is the map match where the traveller means? "check": ask "Is this the place?" (place_note says why). */
  place_status?: "ok" | "check" | "confirmed" | null;
  place_note?: string | null;
  /** The traveller said "yes, this is the place" (sent on create / patch only). */
  place_confirmed?: boolean;
  /** Other places seen during the stop's days (Moray, Maras... on a Cusco day), in order. */
  visits?: Visit[];
  /** The traveller did not say how long: the days are a guess. */
  days_estimated?: boolean;
  /** What the place is and a fun fact, when we know the place. */
  guide?: PlaceGuide | null;
  /** The trip board: idea (maybe), flex (decided, days can change), fixed (booked). */
  status?: StopStatus;
  fixed_note?: string | null;
  sleep?: string | null;
  arrival?: LegSaved | null;
  plan?: PlanChoices;
}

export type StopStatus = "idea" | "flex" | "fixed";
export type LegMode = "flight" | "bus" | "car" | "train" | "boat" | "local" | "other";
export interface LegSaved { mode: LegMode; booked: boolean; ref?: string | null; from?: string | null; to?: string | null; note?: string | null }
export interface PlanChoices { skip?: string[]; pins?: Record<string, string>; weather?: Record<string, Sky>; mode?: string | null }
export type Sky = "clear" | "cloud" | "rain" | "wind" | "unknown";
export type Need = "clear" | "dry" | "calm" | "any";

export interface Airport { iata: string; name: string; city: string; country: string }
export interface FlightLink { label: string; url: string; airline?: boolean; partner?: boolean }
export interface BoardLeg {
  from_name: string; to_name: string; date: string;
  guess: "local" | "road" | "road_or_flight" | "flight"; km: number | null; hours: number | null; border: boolean;
  mode: LegMode; chosen: boolean; booked: boolean; ref: string | null; note: string | null;
  from_airport: Airport | null; to_airport: Airport | null; links: FlightLink[];
}
export interface TodoItem {
  id: string; name: string; hours: string; length: "full" | "half" | "short"; effort: "easy" | "moderate" | "hard";
  need: Need; need_text: string; best: string; book: string; why: string; months: number[]; weekdays?: number[]; act: Activity | null;
  note?: string; moved?: boolean; pinned?: boolean;
}
export interface PlanDayOut {
  date: string; sky: Sky; rain_chance: number; source: string; kind: "plan" | "rain" | "free" | "spare" | "route";
  title: string; note: string; override: boolean; tmin: number; tmax: number; wind_kmh: number; things: TodoItem[];
}
export interface BoardStop {
  id: string; name: string; country_code: string | null; start_date: string; end_date: string; days: number;
  status: StopStatus; fixed_note: string | null; sleep: string | null; days_estimated: boolean;
  arrival: BoardLeg;
  todo: {
    source: "guide" | "trips" | "nearby" | "none"; area: string | null; items: TodoItem[];
    rain: { name: string; hours: string; why: string } | null;
    routes: { id: string; name: string; summary: string; book: string; days: { title: string; note: string; rain: string }[] }[];
    season: string; sleep_tip: string; sources: string[];
  };
  plan: { mode: string | null; choices: PlanChoices; days: PlanDayOut[]; waiting: TodoItem[]; out_of_season: string[]; advice: string[] };
  weather_sources: string[];
}
export interface Board {
  trip_id: string; start_date: string | null; end_date: string | null; total_days: number; start_estimated: boolean;
  home_airport: Airport | null; stops: BoardStop[]; return_leg: BoardLeg | null; prices: boolean;
}
export interface FlightPrice { date: string; price: number | null; currency: string; airline: string | null; transfers: number | null; url: string | null }

export interface FlightSeg { from: string; to: string; departs: string; arrives: string; airline: string | null; flight: string }
export interface FlightSlice { origin: string; destination: string; departs: string | null; arrives: string | null; minutes: number | null; stops: number; segments: FlightSeg[] }
export interface FlightOffer {
  id: string; price: number; currency: string; airline: string | null; expires_at: string | null;
  slices: FlightSlice[]; passenger_ids: string[]; changeable: boolean | null; refundable: boolean | null; bags: number | null;
}
export interface FlightLeg extends BoardLeg { stop_id: string | null }
export interface TripFlights { legs: FlightLeg[]; all_legs_link: string | null; search: boolean; book: boolean; test: boolean }
export interface Passenger { title: "mr" | "ms" | "mrs" | "miss" | "dr"; given_name: string; family_name: string; gender: "m" | "f"; born_on: string; email: string; phone_number: string }
export interface FlightOrder { order_id: string; booking_reference: string | null; price: number; currency: string; slices: FlightSlice[]; test: boolean }

/** One stop of a trip being started (a proposal, a sentence read, or a row typed). */
export interface PlanStep {
  key: string; place_id?: string | null; name: string; country: string | null; lat: number; lon: number;
  kind?: string | null; days: number; start_date?: string | null; fixed_dates?: boolean;
  elevation_m?: number | null; activities?: Activity[] | null; sights: string[];
  /** What to do each day there, from what organised trips do (several things a day). */
  plan?: PlanDay[]; also?: string[];
}
export interface PlanDay {
  day: number; kind: "arrive" | "day" | "more" | "free"; sights: string[];
  /** a trip out of several days (a trek): how many */ days?: number;
  /** "more" days: the trip out they belong to */ of?: string;
}
export interface PlanArea { id: string; name: string; kind: "region" | "country" }
export interface PlanProposal {
  area: PlanArea; only: string[]; stops: PlanStep[]; more: PlanStep[]; route: string | null;
  best_months: number[]; days: number; suggested_start: string;
}
export interface PlanIdea { id: string; title: string; days: number; countries: string[]; weather: string; guide: string | null }
export interface PlanReading {
  text: string; mode: "stops" | "region" | "open"; area: PlanArea | null; only: string[]; month: number | null;
  start_date: string | null; start_part?: string; days: number | null; stops: PlanStep[];
  home: { name: string; country: string; lat: number; lon: number } | null; wishes: string[];
  missing: ("where" | "when" | "how_long")[]; keep?: string[]; last?: string[]; proposal: PlanProposal | null; ideas: PlanIdea[];
}
export interface PlanSuggestion { type: "region" | "country"; id: string; name: string; sub: string }

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
  /** The trip's countries (ISO codes): a stop outside them is asked about. */
  countries?: string[];
  /** Slug of the recommended trip it started from; null = the traveller's own. */
  source_itinerary?: string | null;
  home_airport?: string | null;
  return_leg?: LegSaved | null;
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
  /** The verified place registry's id, when the place comes from it. */
  place_id?: string | null;
  /** A sight placed at the town where you sleep (Machu Picchu -> Aguas Calientes). */
  base?: string | null;
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

/** The server's verdict on a stop's map match: "check" means it may be the wrong place. */
export interface PlaceCheck {
  status: "ok" | "check" | "confirmed";
  codes: string[];
  issues: string[];
}

export interface DraftStop {
  name: string;
  start_date: string;
  end_date: string;
  activities: Activity[];
  matches: Place[];
  place: Place | null;
  check?: PlaceCheck | null;
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
export interface ItineraryStop extends Omit<Stop, "plan"> {
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
