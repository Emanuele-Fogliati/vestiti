"""The days of one stop, planned against the weather (Manu, 2026-11-12).

"I have 5 days in Torres del Paine: what do I do, in which order, and if a day rains what do I
skip?" The things to do come in order (app.guide.todo): the first is the one not to miss. Each
says what weather it needs. The plan puts them on the days:

- a walk that is only worth it with a view goes on a clear day; with no clear day it goes on the
  least bad one, marked "only if it clears";
- a boat goes on a day without strong wind or rain;
- what works in any weather goes on the bad days first, to keep the good days for the rest;
- a day left over in the rain gets the area's rain plan; a dry one stays free, or is kept for
  a walk still waiting for a clear day.

The sky of a day: real forecast within ~15 days (clear, cloudy, rain, wind), "unknown" before
that, with the chance of rain from the climate. Months ahead nobody knows which day will be
clear, so the plan follows the order and tells you whether you have a spare day to move a walk.
On the trip, "It's raining today" (weather override) re-plans the remaining days.

A stop done as a fixed route with its nights booked (the W Trek) follows the route's days
whatever the sky; the weather only changes the advice of the day.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.engine.strategy import DayWeather
from app.guide.todo import Item, Rain, Route

Sky = str  # clear | cloud | rain | wind | unknown
SKIES = ("clear", "cloud", "rain", "wind", "unknown")

# how much of a day a thing takes; a day holds 2
SIZE = {"full": 2.0, "half": 1.0, "short": 0.5}
DAY = 2.0
# the day you arrive: half a day after a flight or a long road, a full day otherwise
ARRIVAL_DAY = 1.0
# chance of a wet day (climate) from which the plan keeps a spare day for the walks with a view
SPARE_WET = 30


def sky_of(d: DayWeather) -> Sky:
    """What the sky does on a day, from the weather we have for it."""
    if d.source not in ("forecast", "observed"):
        return "unknown"
    if d.precip_mm >= 3 or (d.precip_prob >= 70 and d.precip_mm >= 1):
        return "rain"
    if (d.gust_kmh or 0) >= 75 or d.wind_kmh >= 45:
        return "wind"
    if d.cloud is not None:
        return "clear" if d.cloud <= 45 else "cloud"
    return "clear" if d.precip_prob <= 20 else "cloud"


# how good a sky is for a need: 2 good, 1 possible (marked), 0 no
FIT = {
    "clear": {"clear": 2, "unknown": 2, "cloud": 1, "wind": 0, "rain": 0},
    "dry": {"clear": 2, "unknown": 2, "cloud": 2, "wind": 1, "rain": 0},
    "calm": {"clear": 2, "unknown": 2, "cloud": 2, "wind": 0, "rain": 0},
    "any": {"clear": 2, "unknown": 2, "cloud": 2, "wind": 2, "rain": 2},
}
# for "any" things: the worst days first, to keep the good ones for the rest
WORST_FIRST = {"rain": 0, "wind": 1, "cloud": 2, "unknown": 3, "clear": 4}


@dataclass
class Slot:
    item: Item
    note: str = ""  # "Only if it clears in the morning"
    moved: bool = False  # the weather moved it from where the order would put it
    pinned: bool = False


@dataclass
class PlanDay:
    date: date
    sky: Sky
    rain_chance: float
    source: str
    things: list[Slot] = field(default_factory=list)
    kind: str = "plan"  # plan | rain | free | spare | route
    title: str = ""  # for rain / free / spare / route days
    note: str = ""
    override: bool = False  # the traveller said what the sky does that day


@dataclass
class DayPlan:
    days: list[PlanDay]
    waiting: list[Item]  # things with no day for them (not enough days, or no weather)
    out_of_season: list[Item]
    advice: list[str]
    mode: str | None = None


def _place(items: list[Item], skies: list[Sky], pins: dict[str, int], arrival_light: bool,
           dates: list[date] | None = None, spare: int | None = None
           ) -> tuple[dict[int, list[Slot]], list[Item]]:
    room = [DAY] * len(skies)
    if skies and arrival_light:
        room[0] = ARRIVAL_DAY
    if spare is not None:
        room[spare] = 0.0  # kept free to move a walk when its day is bad
    out: dict[int, list[Slot]] = {i: [] for i in range(len(skies))}
    waiting: list[Item] = []
    for it in items:  # pins first: the traveller chose the day
        i = pins.get(it.id)
        if i is not None:
            out[i].append(Slot(it, pinned=True))
            room[i] -= SIZE[it.length]
    for it in items:
        if it.id in pins:
            continue
        size = SIZE[it.length]
        free = [i for i in range(len(skies)) if room[i] >= size - 1e-9
                and (not it.weekdays or not dates or dates[i].weekday() in it.weekdays)]
        if it.need == "any":
            free.sort(key=lambda i: (WORST_FIRST[skies[i]], i))
            best = free[0] if free else None
            note = ""
        else:
            good = [i for i in free if FIT[it.need][skies[i]] == 2]
            maybe = [i for i in free if FIT[it.need][skies[i]] == 1]
            # a clear-sky walk prefers a known clear day to an unknown one
            good.sort(key=lambda i: (0 if skies[i] == "clear" else 1, i))
            best = good[0] if good else (maybe[0] if maybe else None)
            note = "" if good else ("Only if it clears in the morning" if it.need == "clear"
                                    else "Only if the wind drops")
        if best is None:
            waiting.append(it)
            continue
        out[best].append(Slot(it, note=note))
        room[best] -= size
    return out, waiting


def plan_days(weather: list[DayWeather], items: list[Item], rain: Rain | None = None,
              routes: list[Route] | None = None, choices: dict | None = None,
              arrival_light: bool = False) -> DayPlan:
    """Plan a stop's days. choices: the stop's saved plan (skip, pins, weather, mode)."""
    choices = choices or {}
    skip = set(choices.get("skip") or [])
    overrides = {k: v for k, v in (choices.get("weather") or {}).items() if v in SKIES}
    dates = [d.date for d in weather]
    skies = [overrides.get(d.date.isoformat()) or sky_of(d) for d in weather]
    month = dates[0].month if dates else None
    season_ok = [it for it in items if not it.months or not dates
                 or any(d.month in it.months for d in dates)]
    out_of_season = [it for it in items if it not in season_ok]
    todo = [it for it in season_ok if it.id not in skip]
    pins = {}
    for iid, ds in (choices.get("pins") or {}).items():
        try:
            pins[iid] = dates.index(date.fromisoformat(ds))
        except (ValueError, TypeError):
            continue
    pins = {k: v for k, v in pins.items() if any(it.id == k for it in todo)}

    days = [PlanDay(date=d.date, sky=s, rain_chance=d.precip_prob, source=d.source,
                    override=d.date.isoformat() in overrides)
            for d, s in zip(weather, skies)]
    advice: list[str] = []
    mode = choices.get("mode")
    route = next((r for r in routes or [] if r.id == mode), None)
    start = 0
    if route:
        for i, rd in enumerate(route.days[:len(days)]):
            pd = days[i]
            pd.kind, pd.title, pd.note = "route", rd.title, rd.note
            if pd.sky in ("rain", "wind") and rd.rain:
                pd.note = rd.rain
        start = min(len(route.days), len(days))
        if len(days) < len(route.days):
            advice.append(f"The {route.name.split(',')[0]} takes {len(route.days)} days: "
                          f"you have {len(days)} here.")
        if route.book:
            advice.append(route.book)
    rest = list(range(start, len(days)))
    if rest:
        sub_skies = [skies[i] for i in rest]
        sub_pins = {k: rest.index(v) for k, v in pins.items() if v in rest}
        sub_dates = [dates[i] for i in rest]
        # months ahead, in a place where many days are wet, keep the last day free to move a
        # walk that needs a view: nobody knows yet which day will be clear
        wet = sum(d.precip_prob for d in weather) / len(weather) if weather else 0
        views = [it for it in todo if it.need == "clear"]
        spare = None
        if (all(s == "unknown" for s in sub_skies) and wet >= SPARE_WET and len(rest) >= 3
                and len(views) >= 2 and (len(rest) - 1) not in sub_pins.values()):
            spare = len(rest) - 1
        placed, waiting = _place(todo, sub_skies, sub_pins, arrival_light and start == 0, sub_dates, spare)
        # where the order alone would put them: what moved, moved for the weather
        base, _ = _place(todo, ["unknown"] * len(sub_skies), sub_pins, arrival_light and start == 0,
                         sub_dates, spare)
        where = {s.item.id: i for i, ss in base.items() for s in ss}
        for j, slots in placed.items():
            for s in slots:
                s.moved = not s.pinned and where.get(s.item.id) not in (None, j) \
                    and sub_skies[j] != "unknown"
            days[rest[j]].things = slots
        waits = [w for w in waiting if w.need != "any"]
        for j in range(len(rest)):
            pd = days[rest[j]]
            if pd.things:
                continue
            if pd.sky in ("rain", "wind") and rain:
                pd.kind, pd.title, pd.note = "rain", rain.name, rain.why
            elif spare is not None and j == spare:
                pd.kind, pd.title = "spare", "Spare day for the weather"
                pd.note = ("If a walk that needs a view gets a bad day, move it here. "
                           + (f"If not, {waits[0].name}." if waits else "If not, rest."))
            elif waits:
                w = waits.pop(0)
                pd.kind, pd.title = "spare", f"Kept free for {w.name}"
                pd.note = "No good day left for it yet. If this morning is clear, go; if not, rest."
            else:
                pd.kind, pd.title = "free", "Free day"
                pd.note = "Rest, or do the best walk again if the sky is clear."
    else:
        waiting = [it for it in todo]
    for it in waiting:
        if it.weekdays and dates and not any(d.weekday() in it.weekdays for d in dates):
            import calendar
            advice.append(f"{it.name} is on {', '.join(calendar.day_name[w] for w in it.weekdays)} "
                          "only: not on your days here.")

    # honest advice about the margin
    needs_view = [it for it in todo if it.need in ("clear", "calm")]
    unknown = all(s == "unknown" for s in skies) if skies else False
    if needs_view and unknown and rest:
        wet = round(sum(d.precip_prob for d in weather) / len(weather))
        spare = sum(1 for i in rest if days[i].kind in ("free", "spare"))
        if wet >= 25:
            if spare:
                advice.append(f"About {wet}% of days are wet here in {_month(month)}: "
                              f"you have {spare} free day{'s' if spare > 1 else ''} to move a walk "
                              "if its day is bad.")
            else:
                advice.append(f"About {wet}% of days are wet here in {_month(month)} and every day "
                              "is full: one more day gives you a backup for the walks that need a view.")
    if any(s != "unknown" for s in skies):
        advice.append("Real forecast for these days. The plan follows it and changes when it does.")
    elif skies:
        advice.append("The forecast arrives 15 days before. Until then the order follows what is "
                      "most worth it.")
    return DayPlan(days=days, waiting=waiting, out_of_season=out_of_season, advice=advice,
                   mode=route.id if route else None)


def _month(m: int | None) -> str:
    import calendar
    return calendar.month_name[m] if m else "this season"
