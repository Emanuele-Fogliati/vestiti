from __future__ import annotations

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


class TripIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)
    stops: list[StopIn] = Field(default_factory=list)


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


class TripSummary(ORM):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    stop_count: int
    start_date: date | None
    end_date: date | None
    places: list[str]


class ReorderIn(BaseModel):
    stop_ids: list[str]


class SelectionIn(BaseModel):
    tier: str
    slot: str
    choice: str  # product | owned | rent | skip | auto
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
        if v not in ("product", "owned", "rent", "skip", "auto"):
            raise ValueError("choice must be product, owned, rent, skip or auto")
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
    text: str = Field(min_length=3, max_length=4000)


class ExplainIn(BaseModel):
    topic: str = Field(max_length=300)
    stage_index: int | None = None
    slot: str | None = None
    tier: str = "medium"


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    tier: str = "medium"
