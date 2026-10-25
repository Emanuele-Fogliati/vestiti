from __future__ import annotations

import datetime as _dt
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.engine.activities import ACTIVITY_TYPES, DIFFICULTIES
from app.engine.garments import FOOTWEAR_TYPES, LEVELS, SLOT_KEYS


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth / user

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: str | None = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORM):
    id: str
    email: str | None
    display_name: str | None
    is_guest: bool
    is_admin: bool
    gender_pref: str
    thermal_offset: float
    created_at: datetime


class ProfileIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    gender_pref: str | None = None
    thermal_offset: float | None = Field(default=None, ge=-0.5, le=0.5)

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


class StopIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    country_code: str | None = Field(default=None, max_length=2)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    elevation_m: float = Field(default=0, ge=-500, le=9000)
    start_date: date
    end_date: date
    activities: list[ActivityIn] = Field(default_factory=lambda: [ActivityIn()])
    notes: str | None = Field(default=None, max_length=2000)
    position: int | None = None
    visits: list[VisitIn] = Field(default_factory=list, max_length=30)
    days_estimated: bool = False  # the traveller did not say how long: the days are a guess

    @model_validator(mode="after")
    def _dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date is before start_date")
        if (self.end_date - self.start_date).days > 120:
            raise ValueError("a single stop can be at most 120 days")
        return self


class StopPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    country_code: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    elevation_m: float | None = Field(default=None, ge=-500, le=9000)
    start_date: date | None = None
    end_date: date | None = None
    activities: list[ActivityIn] | None = None
    notes: str | None = None
    visits: list[VisitIn] | None = Field(default=None, max_length=30)


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
                lm = match(v.name, None, None)
                v.art = StopArt(id=lm.id, label=lm.label) if lm else None
        if self.art is None:
            lm = match(self.name, self.latitude, self.longitude)
            self.art = StopArt(id=lm.id, label=lm.label) if lm else _first_visit_art(self)
        return self


def _first_visit_art(stop: StopOut) -> StopArt | None:
    """A stop with no landmark of its own ("Valle Sacra") shows its first visit's."""
    return next((v.art for v in stop.visits if v.art), None)


class TripIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)
    stops: list[StopIn] = Field(default_factory=list)
    start_estimated: bool = False  # no start date was given: the plan shows it as a guess


class TripPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = None


class TripOut(ORM):
    id: str
    name: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
    stops: list[StopOut]
    start_estimated: bool = False
    estimate: TripEstimate | None = None

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


class ReorderIn(BaseModel):
    stop_ids: list[str]


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
        if v not in SLOT_KEYS:
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
    created_at: datetime


# ---------------------------------------------------------------- AI

class ParseIn(BaseModel):
    text: str = Field(min_length=3, max_length=50000)


class ExplainIn(BaseModel):
    topic: str = Field(max_length=300)
    stage_index: int | None = None
    slot: str | None = None
    tier: str = "medium"


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    tier: str = "medium"
