from __future__ import annotations

import datetime as _dt
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.engine.activities import ACTIVITY_TYPES, DIFFICULTIES
from app.engine.garments import FOOTWEAR_TYPES, LEVELS, SLOT_KEYS, known_slot


PACES = ("relaxed", "average", "brisk")
EVENINGS = ("early", "sometimes", "late")
COLD = ("very_cold", "bit_cold", "average", "warm")

# Trip dates must stay in a sane window: a stop dated in year 9999 made the weather loop
# run over millions of days and froze the server for minutes (security audit 2026-10).
MIN_DATE = date(1950, 1, 1)  # Open-Meteo's archive starts in 1940
MAX_DATE = date(2100, 12, 31)
MAX_STOP_DAYS = 120
MAX_STOPS = 30


def check_date(d: date | None) -> date | None:
    if d is not None and not MIN_DATE <= d <= MAX_DATE:
        raise ValueError(f"dates must be between {MIN_DATE} and {MAX_DATE}")
    return d


def check_country(v: str | None) -> str | None:
    if v and not (len(v) == 2 and v.isascii() and v.isalpha()):
        raise ValueError("country_code must be a 2-letter ISO code")
    return v


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth / user

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: str | None = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)  # argon2 on a megabyte "password" would burn CPU


MAX_BRANDS = 8


def clean_brand_list(v: list[str] | None) -> list[str] | None:
    """Trimmed, de-duplicated (case-insensitive), at most MAX_BRANDS names of 60 chars."""
    if v is None:
        return None
    out: list[str] = []
    for b in v:
        b = " ".join(str(b).split())[:60]
        if b and b.lower() not in {x.lower() for x in out}:
            out.append(b)
    return out[:MAX_BRANDS]


class UserOut(ORM):
    id: str
    email: str | None
    display_name: str | None
    is_guest: bool
    is_admin: bool
    gender_pref: str
    thermal_offset: float
    pace: str = "average"
    evenings: str = "sometimes"
    preferred_brands: list[str] = []
    market: str = "us"  # where the kit shops: the user's choice, else the app's default
    profile_done_at: datetime | None = None
    created_at: datetime

    @field_validator("market", mode="before")
    @classmethod
    def _market(cls, v):
        from app.config import get_settings
        return v if v in ("us", "eu") else get_settings().default_market


class ProfileIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    gender_pref: str | None = None
    thermal_offset: float | None = Field(default=None, ge=-0.5, le=0.5)
    pace: str | None = None
    evenings: str | None = None
    preferred_brands: list[str] | None = Field(default=None, max_length=20)
    market: str | None = None

    @field_validator("market")
    @classmethod
    def _m(cls, v):
        if v is not None and v not in ("us", "eu"):
            raise ValueError("market must be us or eu")
        return v

    @field_validator("pace")
    @classmethod
    def _p(cls, v):
        if v is not None and v not in PACES:
            raise ValueError(f"pace must be one of {PACES}")
        return v

    @field_validator("evenings")
    @classmethod
    def _e(cls, v):
        if v is not None and v not in EVENINGS:
            raise ValueError(f"evenings must be one of {EVENINGS}")
        return v

    @field_validator("preferred_brands")
    @classmethod
    def _b(cls, v):
        return clean_brand_list(v)

    @field_validator("gender_pref")
    @classmethod
    def _g(cls, v):
        if v is not None and v not in ("men", "women", "any"):
            raise ValueError("gender_pref must be men, women or any")
        return v


# ---------------------------------------------------------------- trips

class ActivityIn(BaseModel):
    type: str = "city"
    difficulty: str | None = None
    max_altitude_m: float | None = Field(default=None, ge=-500, le=9000)
    glacier: bool = False  # walking on ice with crampons

    @field_validator("type")
    @classmethod
    def _t(cls, v):
        if v not in ACTIVITY_TYPES:
            raise ValueError(f"type must be one of {ACTIVITY_TYPES}")
        return v

    @field_validator("difficulty")
    @classmethod
    def _d(cls, v):
        if v is not None and v not in DIFFICULTIES:
            raise ValueError(f"difficulty must be one of {DIFFICULTIES}")
        return v


class VisitIn(BaseModel):
    """A place seen during a stop besides where you sleep ("Moray" on the Cusco days)."""
    name: str = Field(min_length=1, max_length=120)
    date: _dt.date | None = None

    _d = field_validator("date")(classmethod(lambda cls, v: check_date(v)))


STATUSES = ("idea", "flex", "fixed")
LEG_MODES = ("flight", "bus", "car", "train", "boat", "local", "other")


class LegIn(BaseModel):
    """How the traveller gets to a stop (or home): the mode, whether it is booked, and for a
    flight the airports (IATA) and the flight number."""
    mode: str = "other"
    booked: bool = False
    ref: str | None = Field(default=None, max_length=40)  # "AR 1872"
    from_: str | None = Field(default=None, alias="from", max_length=3)
    to: str | None = Field(default=None, max_length=3)
    note: str | None = Field(default=None, max_length=200)

    model_config = {"populate_by_name": True}

    @field_validator("mode")
    @classmethod
    def _m(cls, v):
        if v not in LEG_MODES:
            raise ValueError(f"mode must be one of {LEG_MODES}")
        return v

    @field_validator("from_", "to")
    @classmethod
    def _code(cls, v):
        if v in (None, ""):
            return None
        v = v.upper()
        from app.travel import by_code
        if v not in by_code():
            raise ValueError(f"unknown airport code {v}")
        return v

    def stored(self) -> dict:
        return {"mode": self.mode, "booked": self.booked, "ref": self.ref, "from": self.from_,
                "to": self.to, "note": self.note}


class PlanChoicesIn(BaseModel):
    """The traveller's choices on a stop's day plan."""
    skip: list[str] = Field(default_factory=list, max_length=60)
    pins: dict[str, _dt.date] = Field(default_factory=dict, max_length=60)
    weather: dict[_dt.date, str] = Field(default_factory=dict, max_length=60)
    mode: str | None = Field(default=None, max_length=40)

    @field_validator("weather")
    @classmethod
    def _w(cls, v):
        for k in v.values():
            if k not in ("clear", "cloud", "rain", "wind"):
                raise ValueError("weather must be clear, cloud, rain or wind")
        return v

    def stored(self) -> dict:
        return {"skip": self.skip, "pins": {k: d.isoformat() for k, d in self.pins.items()},
                "weather": {d.isoformat(): w for d, w in self.weather.items()}, "mode": self.mode}


class LayoutStopIn(BaseModel):
    id: str
    days: int = Field(ge=1, le=MAX_STOP_DAYS + 1)
    status: str | None = None
    gap_before: int = Field(default=0, ge=0, le=60)  # free days left before this stop

    @field_validator("status")
    @classmethod
    def _s(cls, v):
        if v is not None and v not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        return v


class LayoutIn(BaseModel):
    """The board: every stop in its new order with its days; the dates follow back to back."""
    start_date: date | None = None
    stops: list[LayoutStopIn] = Field(min_length=1, max_length=MAX_STOPS)

    _sd = field_validator("start_date")(classmethod(lambda cls, v: check_date(v)))


class _Iata(BaseModel):
    @staticmethod
    def code(v: str) -> str:
        v = (v or "").upper()
        from app.travel import by_code
        if v not in by_code():
            raise ValueError(f"unknown airport code {v}")
        return v


class FlightSliceIn(BaseModel):
    origin: str
    destination: str
    date: date

    _c = field_validator("origin", "destination")(classmethod(lambda cls, v: _Iata.code(v)))

    @field_validator("date")
    @classmethod
    def _d(cls, v):
        check_date(v)
        if v < _dt.date.today():
            raise ValueError("that day is in the past")
        return v


class FlightSearchIn(FlightSliceIn):
    adults: int = Field(default=1, ge=1, le=9)


class FlightsTogetherIn(BaseModel):
    slices: list[FlightSliceIn] = Field(min_length=2, max_length=6)
    adults: int = Field(default=1, ge=1, le=9)


class PassengerIn(BaseModel):
    title: str = Field(pattern=r"^(mr|ms|mrs|miss|dr)$")
    given_name: str = Field(min_length=1, max_length=60)
    family_name: str = Field(min_length=1, max_length=60)
    gender: str = Field(pattern=r"^(m|f)$")
    born_on: date
    email: EmailStr
    phone_number: str = Field(pattern=r"^\+[1-9][0-9]{6,14}$")


class FlightBookIn(BaseModel):
    offer_id: str = Field(min_length=3, max_length=80)
    stop_id: str | None = None  # the stop this flight takes you to; None = the flight home
    passengers: list[PassengerIn] = Field(min_length=1, max_length=9)


class StopIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    country_code: str | None = Field(default=None, max_length=2)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    elevation_m: float = Field(default=0, ge=-500, le=9000)
    start_date: date
    end_date: date
    activities: list[ActivityIn] = Field(default_factory=lambda: [ActivityIn()], max_length=20)
    notes: str | None = Field(default=None, max_length=2000)
    position: int | None = None
    visits: list[VisitIn] = Field(default_factory=list, max_length=30)
    days_estimated: bool = False  # the traveller did not say how long: the days are a guess
    place_confirmed: bool = False  # the traveller said "yes, this is the place"
    status: str = "flex"

    _cc = field_validator("country_code")(classmethod(lambda cls, v: check_country(v)))
    _sd = field_validator("start_date", "end_date")(classmethod(lambda cls, v: check_date(v)))

    @field_validator("status")
    @classmethod
    def _st(cls, v):
        if v not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        return v

    @model_validator(mode="after")
    def _dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date is before start_date")
        if (self.end_date - self.start_date).days > MAX_STOP_DAYS:
            raise ValueError(f"a single stop can be at most {MAX_STOP_DAYS} days")
        return self


class StopPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    country_code: str | None = Field(default=None, max_length=2)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    elevation_m: float | None = Field(default=None, ge=-500, le=9000)
    start_date: date | None = None
    end_date: date | None = None
    activities: list[ActivityIn] | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=2000)
    visits: list[VisitIn] | None = Field(default=None, max_length=30)
    place_confirmed: bool | None = None  # true: "yes, this is the place"
    status: str | None = None
    fixed_note: str | None = Field(default=None, max_length=120)
    sleep: str | None = Field(default=None, max_length=200)
    arrival: LegIn | None = None
    plan: PlanChoicesIn | None = None

    _cc = field_validator("country_code")(classmethod(lambda cls, v: check_country(v)))
    _sd = field_validator("start_date", "end_date")(classmethod(lambda cls, v: check_date(v)))

    @field_validator("status")
    @classmethod
    def _st(cls, v):
        if v is not None and v not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        return v


class StopArt(BaseModel):
    kind: str = "landmark"
    id: str
    label: str


class VisitOut(BaseModel):
    name: str
    date: _dt.date | None = None
    art: StopArt | None = None


class TripEstimate(BaseModel):
    """What of the trip's dates is a guess: the start date, the days per stop, or both."""
    start: bool
    days: bool
    total_days: int


class StopOut(ORM):
    id: str
    position: int
    name: str
    country_code: str | None
    latitude: float
    longitude: float
    elevation_m: float
    start_date: date
    end_date: date
    activities: list[dict]
    notes: str | None
    visits: list[VisitOut] = Field(default_factory=list)
    days_estimated: bool = False
    art: StopArt | None = None
    # ok | check (ask "Is this the place?", place_note says why) | confirmed | null (older stop)
    place_status: str | None = None
    place_note: str | None = None
    # what the place is and a fun fact, when we know the place (app.guide)
    guide: dict | None = None
    status: str = "flex"  # idea | flex | fixed
    fixed_note: str | None = None
    sleep: str | None = None
    arrival: dict | None = None
    plan: dict = Field(default_factory=dict)

    @field_validator("status", mode="before")
    @classmethod
    def _stt(cls, v):
        return v or "flex"

    @field_validator("plan", mode="before")
    @classmethod
    def _pl(cls, v):
        return v or {}

    @field_validator("visits", mode="before")
    @classmethod
    def _v(cls, v):
        return v or []

    @field_validator("days_estimated", mode="before")
    @classmethod
    def _de(cls, v):
        return bool(v)

    @model_validator(mode="after")
    def _art(self):
        from app.art import match
        for v in self.visits:  # by name only: a visit has no coordinates of its own
            if v.art is None:
                lm = match(v.name, None, None, country=self.country_code)
                v.art = StopArt(id=lm.id, label=lm.label) if lm else None
        if self.art is None:
            lm = match(self.name, self.latitude, self.longitude, country=self.country_code)
            self.art = StopArt(id=lm.id, label=lm.label) if lm else _first_visit_art(self)
        if self.guide is None:
            from app.guide import lookup
            g = lookup(self.name, self.country_code)
            self.guide = g.model_dump() if g else None
        return self


def _first_visit_art(stop: StopOut) -> StopArt | None:
    """A stop with no landmark of its own ("Valle Sacra") shows its first visit's."""
    return next((v.art for v in stop.visits if v.art), None)


class TripIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)
    stops: list[StopIn] = Field(default_factory=list, max_length=MAX_STOPS)
    start_estimated: bool = False  # no start date was given: the plan shows it as a guess
    countries: list[str] = Field(default_factory=list, max_length=30)  # ISO codes, from the parse

    @field_validator("countries")
    @classmethod
    def _cc(cls, v):
        from app.places.countries import is_code
        return sorted({c.upper() for c in v if is_code(c)})


class TripPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)
    home_airport: str | None = Field(default=None, max_length=3)
    return_leg: LegIn | None = None

    @field_validator("home_airport")
    @classmethod
    def _ha(cls, v):
        if v in (None, ""):
            return None
        v = v.upper()
        from app.travel import by_code
        if v not in by_code():
            raise ValueError(f"unknown airport code {v}")
        return v


class TripOut(ORM):
    id: str
    name: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
    stops: list[StopOut]
    start_estimated: bool = False
    estimate: TripEstimate | None = None
    countries: list[str] = Field(default_factory=list)

    @field_validator("countries", mode="before")
    @classmethod
    def _cs(cls, v):
        return v or []
    source_itinerary: str | None = None  # slug of the recommended trip it started from
    home_airport: str | None = None
    return_leg: dict | None = None

    @field_validator("start_estimated", mode="before")
    @classmethod
    def _se(cls, v):
        return bool(v)

    @model_validator(mode="after")
    def _art(self):
        # trip-wide pass: the same landmark twice gives way to one named in the notes or visits
        from types import SimpleNamespace

        from app.art import assign
        # visits count as notes: the second Cusco stop shows the Rainbow Mountain it visits
        view = [SimpleNamespace(name=s.name, latitude=s.latitude, longitude=s.longitude,
                                country_code=s.country_code,
                                notes=" · ".join([s.notes or ""] + [v.name for v in s.visits]))
                for s in self.stops]
        for s, lm in zip(self.stops, assign(view)):
            s.art = StopArt(id=lm.id, label=lm.label) if lm else _first_visit_art(s)
        days = any(s.days_estimated for s in self.stops)
        if self.stops and (self.start_estimated or days):
            total = (max(s.end_date for s in self.stops) - min(s.start_date for s in self.stops)).days + 1
            self.estimate = TripEstimate(start=self.start_estimated, days=days, total_days=total)
        return self


class TripDatesIn(BaseModel):
    """Firm up a trip whose dates are a guess. start_date moves every stop; total_days
    spreads the guessed stops over that many days; confirm keeps the dates as they are."""
    start_date: date | None = None
    total_days: int | None = Field(default=None, ge=1, le=365)
    confirm: bool = False

    _sd = field_validator("start_date")(classmethod(lambda cls, v: check_date(v)))


class TripSummary(ORM):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    stop_count: int
    start_date: date | None
    end_date: date | None
    places: list[str]
    art: StopArt | None = None
    estimated: bool = False
    source_itinerary: str | None = None


class ReorderIn(BaseModel):
    stop_ids: list[str] = Field(max_length=MAX_STOPS)


class SelectionIn(BaseModel):
    tier: str
    slot: str
    choice: str  # product | owned | rent | skip | have | buy | auto
    product_id: str | None = None
    wardrobe_item_id: str | None = None

    @field_validator("tier")
    @classmethod
    def _tier(cls, v):
        if v not in ("cheap", "medium", "premium"):
            raise ValueError("tier must be cheap, medium or premium")
        return v

    @field_validator("slot")
    @classmethod
    def _slot(cls, v):
        if not known_slot(v):
            raise ValueError("unknown slot")
        return v

    @field_validator("choice")
    @classmethod
    def _choice(cls, v):
        if v not in ("product", "owned", "rent", "skip", "have", "buy", "auto"):
            raise ValueError("choice must be product, owned, rent, skip, have, buy or auto")
        return v


# ---------------------------------------------------------------- wardrobe

class WardrobeIn(BaseModel):
    category: str
    name: str = Field(min_length=1, max_length=200)
    brand: str | None = Field(default=None, max_length=120)
    warmth: str = "medium"
    clo_override: float | None = Field(default=None, ge=0, le=2)
    waterproof: bool = False
    windproof: bool = False
    material: str | None = None
    footwear_type: str | None = None
    ankle_support: bool = False
    notes: str | None = Field(default=None, max_length=1000)
    model_ref: str | None = Field(default=None, max_length=120)
    added_via: str | None = None

    @field_validator("added_via")
    @classmethod
    def _via(cls, v):
        if v is not None and v not in ("hand", "search", "photo"):
            raise ValueError("unknown way of adding")
        return v

    @field_validator("material")
    @classmethod
    def _m(cls, v):
        if v is not None and v not in ("merino", "synthetic", "fleece", "down", "cotton", "other"):
            raise ValueError("unknown material")
        return v

    @field_validator("footwear_type")
    @classmethod
    def _f(cls, v):
        if v is not None and v not in FOOTWEAR_TYPES:
            raise ValueError("unknown footwear type")
        return v

    @field_validator("category")
    @classmethod
    def _c(cls, v):
        if v not in SLOT_KEYS:
            raise ValueError("unknown category")
        return v

    @field_validator("warmth")
    @classmethod
    def _w(cls, v):
        if v not in LEVELS:
            raise ValueError(f"warmth must be one of {LEVELS}")
        return v


class WardrobeOut(ORM):
    id: str
    category: str
    name: str
    brand: str | None
    warmth: str
    clo_override: float | None
    waterproof: bool
    windproof: bool
    material: str | None
    footwear_type: str | None
    ankle_support: bool
    notes: str | None
    model_ref: str | None = None
    added_via: str | None = None
    specs: dict | None = None
    created_at: datetime


# ---------------------------------------------------------------- AI

class ParseIn(BaseModel):
    text: str = Field(min_length=3, max_length=50000)


class ExplainIn(BaseModel):
    topic: str = Field(max_length=300)
    stage_index: int | None = None
    slot: str | None = Field(default=None, max_length=40)
    tier: str = "medium"


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    tier: str = "medium"


# ---------------------------------------------------------------- traveller profile

class QuizIn(BaseModel):
    """The pre-plan quiz. Every answer is optional: None = skipped, keep what we have."""
    cold: str | None = None
    pace: str | None = None
    evenings: str | None = None
    # basics the traveller already owns (keys of services.profile.BASICS); None = skipped
    owned: list[str] | None = Field(default=None, max_length=30)
    # brands they prefer; None = skipped, [] = no preference
    brands: list[str] | None = Field(default=None, max_length=20)

    @field_validator("brands")
    @classmethod
    def _b(cls, v):
        return clean_brand_list(v)

    @field_validator("cold")
    @classmethod
    def _c(cls, v):
        if v is not None and v not in COLD:
            raise ValueError(f"cold must be one of {COLD}")
        return v

    @field_validator("pace")
    @classmethod
    def _p(cls, v):
        if v is not None and v not in PACES:
            raise ValueError(f"pace must be one of {PACES}")
        return v

    @field_validator("evenings")
    @classmethod
    def _e(cls, v):
        if v is not None and v not in EVENINGS:
            raise ValueError(f"evenings must be one of {EVENINGS}")
        return v


class ChatIn(BaseModel):
    message: str = Field(min_length=2, max_length=1000)
    tier: str = "medium"
