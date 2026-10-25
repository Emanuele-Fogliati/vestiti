"""Layer Strategy engine.

Input: stages (one per itinerary stop) with daily weather and activities.
Output: what each layer does at each stage (worn while moving / on at stops / in the
pack as a precaution / not needed), why, the warmth margin, day-specific exceptions,
and the trip-level requirements that the product matcher uses.

Everything here is deterministic. No network, no database, no LLM.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from app.engine import thermal
from app.engine.activities import ActivityProfile, activity_label, resolve
from app.engine.garments import (
    FOOTWEAR_TYPES,
    LEVELS,
    SLOT_BY_KEY,
    SLOTS,
    KitItem,
    ref_clo,
    reference_item,
)

COLD_ONLY = {"headwear", "gloves", "base_bottom", "shell_bottom"}  # never added for warmth above 10 C
STATUS_RANK = {"none": 0, "pack": 1, "stops": 2, "worn": 3}
ESSENTIALS = ["base_top", "trousers", "socks", "footwear"]
MOVE_ORDER = ["mid_top", "shell_top", "headwear", "gloves", "base_bottom", "insulation_top",
              "shell_bottom"]
REST_ORDER = ["insulation_top", "headwear", "gloves", "mid_top", "shell_top", "base_bottom",
              "shell_bottom"]


# ---------------------------------------------------------------- inputs

@dataclass
class DayWeather:
    date: date
    tmax: float
    tmin: float
    precip_mm: float
    precip_prob: float  # 0-100
    wind_kmh: float
    source: str = "forecast"  # forecast | climate | estimate
    gust_kmh: float | None = None
    uv: float | None = None
    tmin_p10: float | None = None  # climate only: a cold night (10th percentile)


@dataclass
class StageInput:
    index: int
    stop_id: str
    name: str
    base_elevation_m: float
    start: date
    end: date
    activities: list[dict]
    days: list[DayWeather]
    country_code: str | None = None


@dataclass
class Condition:
    stage_index: int
    date: date
    activity: ActivityProfile
    activity_label: str
    mode: str  # moving | rest
    temp_c: float
    feels_like_c: float
    wind_kmh: float
    precip_mm: float
    precip_prob: float
    wet: bool
    snow: bool
    hot_sun: bool
    altitude_m: float
    required: float
    source: str
    where: str  # human description of the moment

    def key(self) -> tuple:
        return (self.stage_index, self.date, self.activity.key, self.mode)


# ---------------------------------------------------------------- conditions

def _activity_altitude(stage: StageInput, activity: dict, profile: ActivityProfile) -> float:
    base = stage.base_elevation_m or 0.0
    alt = activity.get("max_altitude_m")
    if alt:
        return max(float(alt), base)
    if profile.mountain and profile.key != "ski":
        return base + 500.0  # assumed climb when the user did not say (asked as a question)
    if profile.key == "ski":
        return base + 800.0
    return base


def conditions_for_stage(stage: StageInput, personal_offset: float = 0.0) -> list[Condition]:
    out: list[Condition] = []
    acts = stage.activities or [{"type": "city"}]
    for day in stage.days:
        span = day.tmax - day.tmin
        for act in acts:
            for profile in resolve(act):
                base = stage.base_elevation_m or 0.0
                alt = _activity_altitude(stage, act, profile)
                label = activity_label(act)
                daytime = day.tmin + 0.65 * span
                wind_alt = thermal.altitude_wind(day.wind_kmh, base, alt)
                # moving: daytime at the highest point of the activity
                t_move = thermal.lapse_adjust(daytime, base, alt)
                # at rest: the colder of the high break and the early start / evening
                if profile.key == "trek_multiday":
                    camp = base + 0.7 * (alt - base)
                    t_rest = thermal.lapse_adjust(day.tmin, base, camp)
                    rest_where = f"evening at camp (~{camp:.0f} m)"
                    rest_wind = thermal.altitude_wind(day.wind_kmh, base, camp) * 0.6
                elif profile.mountain:
                    early = day.tmin + 0.15 * span
                    t_break = t_move
                    if early < t_break:
                        t_rest, rest_where, rest_wind = early, f"early start at {base:.0f} m", day.wind_kmh
                    else:
                        t_rest, rest_where, rest_wind = t_break, f"break at {alt:.0f} m", wind_alt
                else:
                    t_rest = day.tmin + 0.25 * span
                    rest_where = "evening outdoors"
                    rest_wind = day.wind_kmh
                wet = day.precip_mm >= 1.0 and day.precip_prob >= 50
                hot_sun = day.tmax >= 26 or (day.uv or 0) >= 7
                for mode, temp, wind, where, alt_here in (
                    ("moving", t_move, wind_alt,
                     f"{profile.label.lower()} at {alt:.0f} m" if alt > base + 50 else profile.label.lower(),
                     alt),
                    ("rest", t_rest, rest_wind, rest_where, alt if "break" in rest_where else base),
                ):
                    met = profile.met_moving if mode == "moving" else profile.met_rest
                    air = profile.extra_air_ms if mode == "moving" else (
                        2.0 if profile.key == "ski" else 0.0  # chairlift
                    )
                    req = thermal.required_clo(
                        temp, wind, met, moving=(mode == "moving"), extra_air_speed_ms=air,
                        short_stop=profile.short_stops, personal_offset=personal_offset,
                    )
                    snow = wet and thermal.lapse_adjust(day.tmax, base, alt_here) <= 1.0
                    out.append(Condition(
                        stage_index=stage.index, date=day.date, activity=profile,
                        activity_label=label, mode=mode, temp_c=round(temp, 1),
                        feels_like_c=thermal.feels_like_c(temp, wind), wind_kmh=round(wind),
                        precip_mm=day.precip_mm, precip_prob=day.precip_prob, wet=wet,
                        snow=snow, hot_sun=hot_sun and mode == "moving", altitude_m=alt_here,
                        required=req, source=day.source, where=where,
                    ))
    return out


# ---------------------------------------------------------------- dressing

@dataclass
class Dress:
    worn: list[str]
    provided: float
    required: float
    status: str
    penalties: list[str]
    reasons: dict[str, str]  # slot -> why it is on

    @property
    def margin(self) -> float:
        return round(self.provided - self.required, 2)


def _provided(kit: dict[str, KitItem], worn: list[str], cond: Condition) -> tuple[float, list[str]]:
    items = [kit[s] for s in worn if s in kit]
    windproof = any(i.windproof for i in items if i.slot in ("shell_top", "insulation_top", "mid_top"))
    waterproof = any(i.waterproof for i in items if i.slot == "shell_top")
    down = any(i.down for i in items)
    return thermal.effective_clo(
        [i.clo for i in items], cond.wind_kmh, windproof, cond.wet, waterproof, down,
        cond.temp_c,
    )


def dress(kit: dict[str, KitItem], cond: Condition, start: list[str] | None = None) -> Dress:
    worn: list[str] = []
    reasons: dict[str, str] = {}

    def add(slot: str, why: str):
        if slot in kit and slot not in worn:
            worn.append(slot)
            reasons[slot] = why

    for s in start or []:
        add(s, "already on from moving")
    for s in ESSENTIALS:
        add(s, "always worn")
    if cond.wet:
        add("shell_top", f"rain {cond.precip_mm:.1f} mm ({cond.precip_prob:.0f}% chance)")
        if (cond.precip_mm >= 10 and cond.precip_prob >= 60) or (
                cond.precip_mm >= 4 and cond.precip_prob >= 60 and cond.activity.mountain):
            add("shell_bottom", f"steady rain {cond.precip_mm:.1f} mm on a long day outside")
    if cond.snow:
        add("shell_bottom", "snow")
    if cond.wind_kmh >= 30:
        add("shell_top", f"wind {cond.wind_kmh:.0f} km/h")
    if cond.hot_sun:
        add("sun_hat", "strong sun")

    order = MOVE_ORDER if cond.mode == "moving" else REST_ORDER
    provided, pens = _provided(kit, worn, cond)
    why = (f"needed for warmth: {cond.required:.2f} clo needed at "
           f"{cond.feels_like_c:.0f} °C feels-like")
    while provided < cond.required:
        candidates = [s for s in order if s in kit and s not in worn
                      and not (s in COLD_ONLY and cond.feels_like_c > 10)]
        if not candidates:
            break
        # Prefer the lightest single layer that closes the gap (a fleece for a mild
        # evening, not the down jacket); otherwise add layers in the usual order.
        closing = []
        for s in candidates:
            p, _ = _provided(kit, worn + [s], cond)
            if p >= cond.required:
                closing.append((kit[s].clo, order.index(s), s))
        pick = min(closing)[2] if closing else candidates[0]
        add(pick, why)
        provided, pens = _provided(kit, worn, cond)
    return Dress(worn, provided, cond.required, thermal.warmth_status(provided, cond.required),
                 pens, reasons)


def precaution(slot: str, conds: list[Condition]) -> str | None:
    """Reason to carry a layer in the pack even when the model says it is not worn."""
    mountain = [c for c in conds if c.activity.mountain]
    max_prob = max((c.precip_prob for c in conds), default=0)
    max_wind = max((c.wind_kmh for c in conds), default=0)
    max_alt = max((c.altitude_m for c in conds), default=0)
    if slot == "shell_top":
        if mountain:
            return "mountain weather turns fast: always carry a shell"
        if max_prob >= 30:
            return f"{max_prob:.0f}% chance of rain"
        if max_wind >= 20:
            return f"wind up to {max_wind:.0f} km/h"
    if slot == "shell_bottom":
        # In town an umbrella or a doorway beats rain trousers; carry them only for downpours.
        max_mm = max((c.precip_mm for c in conds), default=0)
        if mountain and max_prob >= 40:
            return f"{max_prob:.0f}% chance of rain"
        if max_prob >= 60 and max_mm >= 10:
            return f"heavy rain likely (up to {max_mm:.0f} mm a day)"
    if slot == "insulation_top" and mountain and max_alt >= 2000:
        return f"above 2,000 m ({max_alt:.0f} m): an emergency warm layer"
    if slot in ("headwear", "gloves") and mountain and max_alt >= 2500:
        return f"above 2,500 m ({max_alt:.0f} m)"
    return None


# ---------------------------------------------------------------- requirements (pass 1)

PRESETS: list[dict[str, str]] = [
    {"base_top": "light", "trousers": "light", "socks": "light", "sun_hat": "light"},
    {"base_top": "medium", "trousers": "medium", "socks": "medium", "mid_top": "light",
     "shell_top": "medium"},
    {"base_top": "medium", "trousers": "medium", "socks": "medium", "mid_top": "medium",
     "shell_top": "medium", "insulation_top": "light", "headwear": "medium", "gloves": "light",
     "base_bottom": "light"},
    {"base_top": "warm", "trousers": "warm", "socks": "warm", "mid_top": "warm",
     "shell_top": "warm", "insulation_top": "warm", "headwear": "warm", "gloves": "warm",
     "base_bottom": "medium", "shell_bottom": "medium"},
    {s.key: "very_warm" for s in SLOTS},
]


def _footwear_level(conds: list[Condition]) -> str:
    cold = min((c.temp_c for c in conds), default=10)
    return "warm" if cold < -5 else "medium"


def _preset_kit(i: int, footwear: str) -> dict[str, KitItem]:
    levels = dict(PRESETS[i])
    levels.setdefault("footwear", footwear)
    if i == 0:
        levels.setdefault("shell_top", "light")
    kit = {slot: reference_item(slot, lv) for slot, lv in levels.items()}
    return kit


@dataclass
class SlotRequirement:
    slot: str
    code: str
    name: str
    needed: bool = False
    level: str = "light"
    ref_clo: float = 0.0
    waterproof: bool = False
    waterproof_grade_mm: int = 0
    windproof: bool = False
    footwear_type: str | None = None
    ankle_support: bool = False
    insulated: bool = False
    breathable_high: bool = False
    packable: bool = False
    reasons: list[str] = field(default_factory=list)
    stages: list[int] = field(default_factory=list)
    days_needed: int = 0
    trip_days: int = 0


def requirements(stages: list[StageInput], conds: list[Condition]) -> dict[str, SlotRequirement]:
    reqs = {s.key: SlotRequirement(s.key, s.code, s.name) for s in SLOTS}
    footwear_lv = _footwear_level(conds)
    used_days: dict[str, set] = {s.key: set() for s in SLOTS}

    def bump(slot: str, level: str, stage_idx: int, d: date, why: str | None = None):
        r = reqs[slot]
        if not r.needed or LEVELS.index(level) > LEVELS.index(r.level):
            r.level = level
        r.needed = True
        if stage_idx not in r.stages:
            r.stages.append(stage_idx)
        used_days[slot].add(d)
        if why and why not in r.reasons and len(r.reasons) < 4:
            r.reasons.append(why)

    by_key: dict[tuple, Dress] = {}
    for c in sorted(conds, key=lambda c: c.mode != "moving"):
        chosen = None
        for i in range(len(PRESETS)):
            kit = _preset_kit(i, footwear_lv)
            start = None
            if c.mode == "rest":
                mv = by_key.get((c.stage_index, c.date, c.activity.key, "moving"))
                start = [s for s in (mv.worn if mv else []) if s in kit]
            d = dress(kit, c, start)
            chosen = (kit, d)
            if d.status != "cold":
                break
        kit, d = chosen
        by_key[c.key()] = d
        for slot in d.worn:
            why = None
            if slot not in ESSENTIALS:
                why = (f"{SLOT_BY_KEY[slot].name}: {d.reasons.get(slot, '')} "
                       f"({c.date:%d %b}, {c.where})")
            bump(slot, kit[slot].level or "medium", c.stage_index, c.date, why)

    for stage in stages:
        sc = [c for c in conds if c.stage_index == stage.index]
        for slot in ("shell_top", "shell_bottom", "insulation_top", "headwear", "gloves"):
            why = precaution(slot, sc)
            if why:
                for c in sc:
                    bump(slot, reqs[slot].level if reqs[slot].needed else "medium",
                         stage.index, c.date, f"{SLOT_BY_KEY[slot].name} in the pack: {why}")

    # hard properties
    all_days = {d.date for s in stages for d in s.days}
    wet = [c for c in conds if c.wet]
    profiles = [c.activity for c in conds]
    if reqs["shell_top"].needed:
        r = reqs["shell_top"]
        r.windproof = True
        if wet or any(c.precip_prob >= 30 for c in conds) or any(
                p.mountain or p.spray for p in profiles):
            r.waterproof = True
            heavy = max((c.precip_mm for c in conds), default=0) >= 10 or len(
                {c.date for c in wet}) >= 3
            r.waterproof_grade_mm = 20000 if heavy else 10000
            if heavy:
                r.reasons.append("heavy or repeated rain: look for 20,000 mm or more")
    if reqs["shell_bottom"].needed:
        reqs["shell_bottom"].waterproof = True
        reqs["shell_bottom"].waterproof_grade_mm = 10000
    fw = reqs["footwear"]
    fw.needed = True
    fw.footwear_type = max((p.footwear for p in profiles), key=FOOTWEAR_TYPES.index,
                           default="sneaker")
    fw.ankle_support = any(p.ankle_support for p in profiles)
    hiking_wet = [c for c in wet if c.activity.mountain] or [c for c in conds if c.snow]
    fw.waterproof = bool(hiking_wet)
    fw.insulated = any(c.temp_c < -5 and c.activity.mountain for c in conds)
    fw.reasons.append(f"activities need at least: {fw.footwear_type.replace('_', ' ')}")
    if fw.ankle_support:
        fw.reasons.append("hard or technical terrain: ankle support")
    if fw.waterproof:
        fw.reasons.append("wet or snowy trail days: waterproof")
    high = any(p.high_intensity for p in profiles)
    multi = len(stages) >= 3 or any(p.key == "trek_multiday" for p in profiles)
    for r in reqs.values():
        r.trip_days = len(all_days)
        r.days_needed = len(used_days[r.slot]) if r.slot not in ESSENTIALS else len(all_days)
        r.breathable_high = high and r.slot in ("shell_top", "base_top", "mid_top")
        r.packable = multi and r.slot in ("insulation_top", "shell_top", "shell_bottom", "mid_top")
        r.ref_clo = ref_clo(r.slot, r.level)
    for s in ESSENTIALS:
        reqs[s].needed = True
    return reqs


def reference_kit(reqs: dict[str, SlotRequirement]) -> dict[str, KitItem]:
    kit = {}
    for slot, r in reqs.items():
        if r.needed:
            it = reference_item(slot, r.level)
            it.waterproof = it.waterproof or r.waterproof
            kit[slot] = it
    return kit


# ---------------------------------------------------------------- evaluation (pass 2)

def _fmt_day(d: date) -> str:
    return f"{d:%d %b}"


def evaluate(
    stages: list[StageInput],
    conds: list[Condition],
    kit: dict[str, KitItem],
) -> dict:
    """Dress every condition with a concrete kit; aggregate per stage and per trip."""
    dresses: dict[tuple, Dress] = {}
    for c in sorted(conds, key=lambda c: c.mode != "moving"):
        start = None
        if c.mode == "rest":
            mv = dresses.get((c.stage_index, c.date, c.activity.key, "moving"))
            start = mv.worn if mv else None
        dresses[c.key()] = dress(kit, c, start)

    stage_out = []
    for st in stages:
        sc = [c for c in conds if c.stage_index == st.index]
        if not sc:
            continue
        day_status: dict[date, dict[str, str]] = {}
        day_reasons: dict[date, dict[str, str]] = {}
        for c in sc:
            d = dresses[c.key()]
            ds = day_status.setdefault(c.date, {s: "none" for s in kit})
            dr = day_reasons.setdefault(c.date, {})
            for slot in d.worn:
                new = "worn" if c.mode == "moving" else "stops"
                if STATUS_RANK[new] > STATUS_RANK[ds[slot]]:
                    ds[slot] = new
                    dr[slot] = d.reasons.get(slot, "")
        for slot in kit:
            why = precaution(slot, sc)
            if why:
                for dte, ds in day_status.items():
                    if ds[slot] == "none":
                        ds[slot] = "pack"
                        day_reasons[dte][slot] = why

        slots = {}
        for slot in kit:
            statuses = [ds[slot] for ds in day_status.values()]
            best = max(statuses, key=lambda s: STATUS_RANK[s])
            slots[slot] = {
                "status": best,
                "days_worn": statuses.count("worn"),
                "days_stops": statuses.count("stops"),
                "days_total": len(statuses),
                "why": _slot_why(slot, best, sc, dresses, day_status, day_reasons, kit),
            }

        modes = {}
        for mode in ("moving", "rest"):
            mc = [c for c in sc if c.mode == mode]
            worst = min(mc, key=lambda c: (dresses[c.key()].margin, c.temp_c))
            d = dresses[worst.key()]
            modes[mode] = {
                "condition": _cond_json(worst),
                "required": d.required,
                "provided": d.provided,
                "margin": d.margin,
                "status": d.status,
                "penalties": d.penalties,
                "worn": d.worn,
                "cross_section": _cross_section(kit, d, worst),
            }

        # day-specific exceptions: days whose layering differs from the typical day
        vectors = {dte: tuple(sorted(ds.items())) for dte, ds in day_status.items()}
        typical = Counter(vectors.values()).most_common(1)[0][0]
        typical_map = dict(typical)
        exceptions = []
        for dte in sorted(day_status):
            ds = day_status[dte]
            if vectors[dte] == typical:
                continue
            more = [s for s in kit if STATUS_RANK[ds[s]] > STATUS_RANK[typical_map[s]]]
            less = [s for s in kit if STATUS_RANK[ds[s]] < STATUS_RANK[typical_map[s]]]
            if not more and not less:
                continue
            day_conds = [c for c in sc if c.date == dte]
            exceptions.append({
                "date": dte.isoformat(),
                "stage_index": st.index,
                "more": [{"slot": s, "status": ds[s], "why": day_reasons[dte].get(s, "")} for s in more],
                "less": [{"slot": s, "status": ds[s]} for s in less],
                "summary": _exception_summary(dte, more, less, ds, day_conds),
            })

        days_json = [{
            "date": d.date.isoformat(), "tmax": d.tmax, "tmin": d.tmin,
            "precip_mm": d.precip_mm, "precip_prob": d.precip_prob, "wind_kmh": d.wind_kmh,
            "source": d.source, "uv": d.uv, "tmin_p10": d.tmin_p10,
        } for d in st.days]
        stage_out.append({
            "index": st.index,
            "stop_id": st.stop_id,
            "name": st.name,
            "start": st.start.isoformat(),
            "end": st.end.isoformat(),
            "elevation_m": st.base_elevation_m,
            "activities": [activity_label(a) for a in (st.activities or [{"type": "city"}])],
            "max_altitude_m": max((c.altitude_m for c in sc), default=st.base_elevation_m),
            "days": days_json,
            "weather_sources": sorted({d.source for d in st.days}),
            "slots": slots,
            "modes": modes,
            "exceptions": exceptions,
            "notes": _stage_notes(st, sc, dresses, kit),
        })

    margins = {m: min((s["modes"][m]["margin"] for s in stage_out), default=0) for m in ("moving", "rest")}
    worst_status = "covered"
    for s in stage_out:
        for m in ("moving", "rest"):
            stt = s["modes"][m]["status"]
            if stt == "cold" or (stt == "marginal" and worst_status == "covered"):
                worst_status = stt
    return {"stages": stage_out, "margins": margins, "status": worst_status, "dresses": dresses}


def _cond_json(c: Condition) -> dict:
    return {
        "date": c.date.isoformat(), "mode": c.mode, "activity": c.activity_label,
        "temp_c": c.temp_c, "feels_like_c": c.feels_like_c, "wind_kmh": c.wind_kmh,
        "precip_mm": c.precip_mm, "precip_prob": c.precip_prob, "wet": c.wet, "snow": c.snow,
        "altitude_m": round(c.altitude_m), "where": c.where, "source": c.source,
    }


def _cross_section(kit: dict[str, KitItem], d: Dress, c: Condition) -> dict:
    layers = []
    for s in SLOTS:
        if not s.torso or s.key not in kit:
            continue
        it = kit[s.key]
        layers.append({"slot": s.key, "code": s.code, "name": s.name, "item": it.name,
                       "clo": it.clo, "worn": s.key in d.worn})
    # interface temperatures across worn torso layers, outside -> skin
    worn = [l for l in layers if l["worn"]]
    total = sum(l["clo"] for l in worn) + 0.12
    t = thermal.SKIN_TEMP_C
    temps = []
    for l in reversed(worn):
        t -= (thermal.SKIN_TEMP_C - c.feels_like_c) * l["clo"] / total
        temps.append({"slot": l["slot"], "outer_temp_c": round(t, 1)})
    return {"outside_c": c.feels_like_c, "skin_c": thermal.SKIN_TEMP_C, "layers": layers,
            "interfaces": list(reversed(temps)), "wind_kmh": c.wind_kmh, "precip_mm": c.precip_mm}


def _slot_why(slot, status, sc, dresses, day_status, day_reasons, kit) -> str:
    name = SLOT_BY_KEY[slot].name
    days = sorted(day_status)
    if status == "none":
        mc = [c for c in sc if c.mode == "rest"]
        coldest = min(mc, key=lambda c: c.feels_like_c)
        d = dresses[coldest.key()]
        return (f"{name} not needed here. Coldest moment is {coldest.feels_like_c:.0f} °C "
                f"feels-like ({_fmt_day(coldest.date)}, {coldest.where}); the other layers give "
                f"{d.provided:.2f} clo against {d.required:.2f} needed.")
    if status == "pack":
        reason = next((day_reasons[d].get(slot) for d in days if day_reasons[d].get(slot)), "")
        return f"{name} stays in the pack as a precaution: {reason}."
    hits = [d for d in days if day_status[d][slot] == status]
    reason = next((day_reasons[d].get(slot) for d in hits if day_reasons[d].get(slot)), "")
    when = "every day" if len(hits) == len(days) else (
        ", ".join(_fmt_day(d) for d in hits[:4]) + ("…" if len(hits) > 4 else ""))
    verb = "Worn while moving" if status == "worn" else "Put on at stops"
    return f"{verb} ({when}): {reason}."


def _exception_summary(dte, more, less, ds, day_conds) -> str:
    c = min(day_conds, key=lambda c: c.feels_like_c)
    weather = []
    if any(x.wet for x in day_conds):
        weather.append(f"rain {c.precip_mm:.1f} mm")
    if max(x.wind_kmh for x in day_conds) >= 30:
        weather.append(f"wind {max(x.wind_kmh for x in day_conds):.0f} km/h")
    weather.append(f"{c.feels_like_c:.0f} °C feels-like at the coldest moment")
    parts = []
    if more:
        parts.append("also " + ", ".join(
            f"{SLOT_BY_KEY[s].name.lower()} {'on' if ds[s] == 'worn' else 'at stops' if ds[s] == 'stops' else 'in the pack'}"
            for s in more))
    if less:
        parts.append("no need for " + ", ".join(SLOT_BY_KEY[s].name.lower() for s in less))
    return f"{_fmt_day(dte)}: " + "; ".join(parts) + f" ({', '.join(weather)})."


def _stage_notes(st: StageInput, sc: list[Condition], dresses, kit) -> list[str]:
    notes = []
    coldest = min(sc, key=lambda c: c.feels_like_c)
    notes.append(f"Coldest moment: {coldest.feels_like_c:.0f} °C feels-like on "
                 f"{_fmt_day(coldest.date)} ({coldest.where}).")
    hottest = max(st.days, key=lambda d: d.tmax)
    if hottest.tmax >= 26:
        notes.append(f"Hot: up to {hottest.tmax:.0f} °C on {_fmt_day(hottest.date)}. Light, "
                     "breathable layers and sun protection.")
    wettest = max(st.days, key=lambda d: d.precip_mm)
    if wettest.precip_mm >= 1:
        notes.append(f"Wettest day: {_fmt_day(wettest.date)} with {wettest.precip_mm:.1f} mm "
                     f"({wettest.precip_prob:.0f}% chance).")
    if any(c.altitude_m > st.base_elevation_m + 300 for c in sc):
        top = max(c.altitude_m for c in sc)
        notes.append(f"Up to {top:.0f} m: about {6.5 * (top - st.base_elevation_m) / 1000:.0f} °C "
                     f"colder than at {st.base_elevation_m:.0f} m, and windier.")
    if "climate" in {d.source for d in st.days}:
        p10 = [d.tmin_p10 for d in st.days if d.tmin_p10 is not None]
        extra = f" Cold nights can drop to {min(p10):.0f} °C." if p10 else ""
        notes.append("Dates are beyond the forecast range, so this uses climate averages from "
                     f"past years.{extra} Check again a week before you leave.")
    if "estimate" in {d.source for d in st.days}:
        notes.append("Weather service unreachable: temperatures are a rough latitude/season "
                     "estimate. Refresh before relying on this.")
    pens = {p for c in sc for p in dresses[c.key()].penalties}
    for p in sorted(pens):
        notes.append(f"Watch out: {p}.")
    return notes


# ---------------------------------------------------------------- questions

def clarifying_questions(stages: list[StageInput]) -> list[dict]:
    qs = []
    for st in stages:
        for i, a in enumerate(st.activities or []):
            t = a.get("type")
            if t == "unknown":
                qs.append({"stop_id": st.stop_id, "field": f"activities.{i}.type",
                           "question": f"What will you do in {st.name}? Until you decide, the "
                                       "plan covers both easy city days and a technical hike.",
                           "options": ["city", "hiking", "beach", "ski", "unknown"]})
            if t in ("hiking", "trek_multiday") and not a.get("max_altitude_m"):
                qs.append({"stop_id": st.stop_id, "field": f"activities.{i}.max_altitude_m",
                           "question": f"How high does the hike in {st.name} go? Without it we "
                                       "assume 500 m above the town.",
                           "options": []})
            if t == "hiking" and a.get("difficulty") == "unknown":
                qs.append({"stop_id": st.stop_id, "field": f"activities.{i}.difficulty",
                           "question": f"How hard is the hike in {st.name}? Until you know, the "
                                       "plan covers easy and technical.",
                           "options": ["easy", "moderate", "hard", "technical"]})
    total_days = sum((s.end - s.start).days + 1 for s in stages)
    if total_days > 21:
        qs.append({"stop_id": None, "field": "laundry",
                   "question": "This trip is longer than three weeks. Will you do laundry on "
                               "the way? The plan assumes yes and does not multiply base layers.",
                   "options": ["yes", "no"]})
    ordered = sorted(stages, key=lambda s: s.start)
    for a, b in zip(ordered, ordered[1:]):
        if (b.start - a.end).days > 1:
            qs.append({"stop_id": b.stop_id, "field": "dates",
                       "question": f"There is a gap between {a.name} and {b.name} "
                                   f"({_fmt_day(a.end)} to {_fmt_day(b.start)}). Is a stop "
                                   "missing?", "options": []})
    return qs
