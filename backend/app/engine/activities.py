"""Activity profiles: how hard you work, how exposed you are, what feet need.

MET values from the Compendium of Physical Activities, rounded.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActivityProfile:
    key: str
    label: str
    met_moving: float
    met_rest: float
    outdoor_hours: float
    footwear: str  # minimum footwear type, see garments.FOOTWEAR_TYPES
    ankle_support: bool = False
    mountain: bool = False  # carry a shell as a precaution even when dry
    extra_air_ms: float = 1.0  # own movement through the air (walking ~1 m/s)
    short_stops: bool = False  # rest = short breaks on the trail (transient tolerance)
    high_intensity: bool = False  # breathability matters


ACTIVITIES: dict[str, ActivityProfile] = {
    "city": ActivityProfile("city", "City & sightseeing", 3.0, 1.8, 6, "sneaker"),
    "hiking_easy": ActivityProfile(
        "hiking_easy", "Easy hike", 4.0, 2.0, 4, "trail_runner", mountain=True, short_stops=True
    ),
    "hiking_moderate": ActivityProfile(
        "hiking_moderate", "Moderate hike", 5.0, 2.0, 6, "trail_runner",
        mountain=True, short_stops=True, high_intensity=True,
    ),
    "hiking_hard": ActivityProfile(
        "hiking_hard", "Hard hike", 6.0, 2.0, 8, "hiking_boot", ankle_support=True,
        mountain=True, short_stops=True, high_intensity=True,
    ),
    "hiking_technical": ActivityProfile(
        "hiking_technical", "Technical / alpine", 6.5, 2.0, 9, "mountaineering_boot",
        ankle_support=True, mountain=True, short_stops=True, high_intensity=True,
    ),
    "trek_multiday": ActivityProfile(
        "trek_multiday", "Multi-day trek", 5.5, 1.6, 10, "hiking_boot", ankle_support=True,
        mountain=True, high_intensity=True,
    ),
    "beach": ActivityProfile("beach", "Beach & coast", 2.0, 1.4, 6, "sandal", extra_air_ms=0.3),
    "ski": ActivityProfile(
        "ski", "Ski / snowboard", 6.0, 1.8, 6, "sneaker", mountain=True,
        extra_air_ms=6.0, short_stops=True, high_intensity=True,
    ),
    "cycling": ActivityProfile(
        "cycling", "Cycling", 7.0, 2.0, 5, "sneaker", extra_air_ms=5.0,
        short_stops=True, high_intensity=True,
    ),
    "safari": ActivityProfile("safari", "Safari / game drives", 1.8, 1.5, 6, "sneaker",
                              extra_air_ms=4.0),
}

HIKING_BY_DIFFICULTY = {
    "easy": "hiking_easy",
    "moderate": "hiking_moderate",
    "hard": "hiking_hard",
    "technical": "hiking_technical",
}

ACTIVITY_TYPES = ["city", "hiking", "trek_multiday", "beach", "ski", "cycling", "safari", "unknown"]
DIFFICULTIES = ["easy", "moderate", "hard", "technical", "unknown"]


def resolve(activity: dict) -> list[ActivityProfile]:
    """Turn a stored activity into one or more profiles.

    "Don't know yet" (type unknown, or hiking with unknown difficulty) returns both an
    easy and a technical profile, so the plan covers either outcome.
    """
    kind = (activity or {}).get("type", "city")
    difficulty = (activity or {}).get("difficulty") or "moderate"
    if kind == "unknown":
        return [ACTIVITIES["city"], ACTIVITIES["hiking_hard"]]
    if kind == "hiking":
        if difficulty == "unknown":
            return [ACTIVITIES["hiking_easy"], ACTIVITIES["hiking_technical"]]
        return [ACTIVITIES[HIKING_BY_DIFFICULTY.get(difficulty, "hiking_moderate")]]
    if kind == "trek_multiday" and difficulty in ("technical",):
        return [ACTIVITIES["trek_multiday"], ACTIVITIES["hiking_technical"]]
    return [ACTIVITIES.get(kind, ACTIVITIES["city"])]


def activity_label(activity: dict) -> str:
    kind = activity.get("type", "city")
    if kind == "unknown":
        return "Not decided yet (covering easy and technical)"
    if kind == "hiking":
        d = activity.get("difficulty") or "moderate"
        return "Hike (difficulty not decided)" if d == "unknown" else f"{d.capitalize()} hike"
    return ACTIVITIES.get(kind, ACTIVITIES["city"]).label
