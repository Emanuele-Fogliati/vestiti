"""Database models. Portable between PostgreSQL (production) and SQLite (tests)."""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(120))
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Product fit preference: "men", "women" or "any"
    gender_pref: Mapped[str] = mapped_column(String(10), default="any")
    # Personal comfort offset in clo: +0.3 means "I run cold", -0.3 "I run warm"
    thermal_offset: Mapped[float] = mapped_column(Float, default=0.0)
    # Pace on the move: relaxed | average | brisk (changes the heat you make walking)
    pace: Mapped[str] = mapped_column(String(10), default="average")
    # Evenings outdoors in town: early (back inside) | sometimes | late (out after dark)
    evenings: Mapped[str] = mapped_column(String(10), default="sometimes")
    # Set when the traveller answered or skipped the profile quiz (it is not shown again)
    profile_done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    trips: Mapped[list["Trip"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    wardrobe: Mapped[list["WardrobeItem"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    # the traveller gave no start date: the dates are a guess until they set one
    start_estimated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="trips")
    stops: Mapped[list["Stop"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="Stop.position"
    )
    selections: Mapped[list["TripSelection"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )


class Stop(Base):
    __tablename__ = "stops"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(200))
    country_code: Mapped[str | None] = mapped_column(String(2))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    elevation_m: Mapped[float] = mapped_column(Float, default=0.0)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    # [{"type": "hiking", "difficulty": "hard", "max_altitude_m": 2400, "hours": 6}]
    activities: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    # places seen during the stop besides where you sleep, in order:
    # [{"name": "Moray", "date": "2027-05-08"}, {"name": "Maras", "date": "2027-05-08"}]
    visits: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    # the traveller gave places but not how long: this stop's days are a guess
    days_estimated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    trip: Mapped[Trip] = relationship(back_populates="stops")


class WardrobeItem(Base):
    __tablename__ = "wardrobe_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(120))
    # light | medium | warm | very_warm
    warmth: Mapped[str] = mapped_column(String(20), default="medium")
    clo_override: Mapped[float | None] = mapped_column(Float)
    waterproof: Mapped[bool] = mapped_column(Boolean, default=False)
    windproof: Mapped[bool] = mapped_column(Boolean, default=False)
    # merino | synthetic | fleece | down | cotton | other
    material: Mapped[str | None] = mapped_column(String(20))
    # footwear only: sandal | sneaker | trail_runner | hiking_boot | mountaineering_boot
    footwear_type: Mapped[str | None] = mapped_column(String(30))
    ankle_support: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="wardrobe")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("network", "external_id", name="uq_product_network_ext"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    network: Mapped[str] = mapped_column(String(40), default="direct")
    # The network's id for the merchant/advertiser (Awin awinmid, Impact campaign, ...)
    program_id: Mapped[str | None] = mapped_column(String(80))
    external_id: Mapped[str] = mapped_column(String(200))
    merchant: Mapped[str] = mapped_column(String(120))
    brand: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(40), index=True)
    gender: Mapped[str] = mapped_column(String(10), default="unisex")
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    url: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    # clo, waterproof_mm, breathability_g, windproof, weight_g, packable, insulation,
    # fill_power, ankle_support, features[]
    specs: Mapped[dict] = mapped_column(JSON, default=dict)
    rating: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    source: Mapped[str] = mapped_column(String(20), default="seed")  # seed | feed | manual
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TripSelection(Base):
    """A user's manual choice for one slot of one tier (overrides the optimizer)."""

    __tablename__ = "trip_selections"
    __table_args__ = (UniqueConstraint("trip_id", "tier", "slot", name="uq_selection"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    tier: Mapped[str] = mapped_column(String(10))  # cheap | medium | premium
    slot: Mapped[str] = mapped_column(String(40))
    # product | owned | rent | skip
    choice: Mapped[str] = mapped_column(String(10), default="product")
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    wardrobe_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("wardrobe_items.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    trip: Mapped[Trip] = relationship(back_populates="selections")


class RentalPartner(Base):
    __tablename__ = "rental_partners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    url_template: Mapped[str] = mapped_column(Text)  # {category} {start} {end} {country}
    network: Mapped[str] = mapped_column(String(40), default="direct")
    countries: Mapped[list] = mapped_column(JSON, default=list)  # ISO2; ["*"] = worldwide
    categories: Mapped[list] = mapped_column(JSON, default=list)
    daily_rates: Mapped[dict] = mapped_column(JSON, default=dict)  # category -> price/day
    min_days: Mapped[int] = mapped_column(Integer, default=1)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    is_placeholder: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AffiliateClick(Base):
    __tablename__ = "affiliate_clicks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    trip_id: Mapped[str | None] = mapped_column(ForeignKey("trips.id", ondelete="SET NULL"))
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    rental_partner_id: Mapped[str | None] = mapped_column(
        ForeignKey("rental_partners.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(10), default="buy")  # buy | rent | excursion | tour
    network: Mapped[str] = mapped_column(String(40))
    tracked: Mapped[bool] = mapped_column(Boolean, default=False)
    tier: Mapped[str | None] = mapped_column(String(10))
    slot: Mapped[str | None] = mapped_column(String(40))
    price: Mapped[float | None] = mapped_column(Float)
    destination_url: Mapped[str] = mapped_column(Text)
    referrer: Mapped[str | None] = mapped_column(Text)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64))


class WeatherCache(Base):
    __tablename__ = "weather_cache"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    source: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class FeedImport(Base):
    __tablename__ = "feed_imports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    network: Mapped[str] = mapped_column(String(40))
    filename: Mapped[str] = mapped_column(String(300))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")
    rows: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    deactivated: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
