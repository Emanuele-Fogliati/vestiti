"""Simplified clothing heat balance.

THIS IS AN ESTIMATE, NOT A VALIDATED PHYSIOLOGICAL MODEL. See docs/LAYER_MODEL.md.

Model (steady state, dry heat only, after IREQ/ISO 11079 in a very reduced form):

    I_total_required = (T_skin - T_air) / (0.155 * H)          [clo]
    I_clothing_required = I_total_required - I_air(wind)       [clo]

    H      = heat the body must shed through the clothing (W/m2)
           = 58.2 * MET * f   with f = 0.6 moving (more sweat/breath loss), 0.7 at rest
    I_air  = 1 / (0.155 * (h_c + h_r)), h_c = 8.3 * sqrt(v), h_r = 4.7  (boundary air layer)
    0.155  = m2*K/W per clo

Garment clo values are summed with McCullough's ensemble formula:

    I_clothing = 0.835 * sum(I_garment) + 0.161

Penalties: wind without a windproof outer layer, wet insulation without a waterproof
outer layer. Short stops on a hike are allowed a 20% transient tolerance.
"""
from __future__ import annotations

import math

SKIN_TEMP_C = 33.0
CLO_UNIT = 0.155  # m2*K/W
MET_W_M2 = 58.2
SHORT_STOP_FACTOR = 0.8
MARGINAL_CLO = 0.15  # a deficit up to this is "marginal", not "too cold"


def wind_chill_c(temp_c: float, wind_kmh: float) -> float:
    """Environment Canada / NWS wind chill. Valid for T <= 10 C and wind > 4.8 km/h."""
    if temp_c > 10 or wind_kmh <= 4.8:
        return temp_c
    v = wind_kmh**0.16
    return 13.12 + 0.6215 * temp_c - 11.37 * v + 0.3965 * temp_c * v


def feels_like_c(temp_c: float, wind_kmh: float) -> float:
    return round(wind_chill_c(temp_c, wind_kmh), 1)


def air_layer_clo(air_speed_ms: float) -> float:
    v = max(air_speed_ms, 0.2)
    h_c = 8.3 * math.sqrt(v)
    h_r = 4.7
    return 1.0 / (CLO_UNIT * (h_c + h_r))


def heat_to_shed(met: float, moving: bool) -> float:
    return MET_W_M2 * met * (0.6 if moving else 0.7)


def required_clo(
    temp_c: float,
    wind_kmh: float,
    met: float,
    moving: bool,
    extra_air_speed_ms: float = 0.0,
    short_stop: bool = False,
    personal_offset: float = 0.0,
) -> float:
    """Clothing insulation (clo) needed to stay thermally neutral."""
    h = heat_to_shed(met, moving)
    total = (SKIN_TEMP_C - temp_c) / (CLO_UNIT * h)
    air_speed = wind_kmh / 3.6 + extra_air_speed_ms
    clothing = total - air_layer_clo(air_speed)
    if short_stop and not moving:
        clothing *= SHORT_STOP_FACTOR
    clothing += personal_offset
    return round(max(clothing, 0.0), 2)


def ensemble_clo(garment_clos: list[float]) -> float:
    if not garment_clos:
        return 0.0
    return 0.835 * sum(garment_clos) + 0.161


def effective_clo(
    garment_clos: list[float],
    wind_kmh: float,
    windproof_outer: bool,
    wet: bool,
    waterproof_outer: bool,
    down_worn: bool = False,
    temp_c: float = 0.0,
) -> tuple[float, list[str]]:
    """Ensemble clo after wind and wetting penalties. Returns (clo, penalty notes)."""
    clo = ensemble_clo(garment_clos)
    notes: list[str] = []
    if wind_kmh >= 18 and not windproof_outer and temp_c < 15:
        clo *= 0.85
        notes.append("wind cuts through non-windproof layers (-15%)")
    if wet and not waterproof_outer and temp_c < 18:
        factor = 0.55 if down_worn else 0.7
        clo *= factor
        notes.append(
            "wet insulation loses loft (-45%, down)" if down_worn else "wet layers insulate less (-30%)"
        )
    return round(clo, 2), notes


def lapse_adjust(temp_c: float, from_m: float, to_m: float, lapse_c_per_km: float = 6.5) -> float:
    """Standard atmosphere lapse rate: about 6.5 C colder per 1000 m of climb."""
    return temp_c - lapse_c_per_km * (to_m - from_m) / 1000.0


def altitude_wind(wind_kmh: float, from_m: float, to_m: float) -> float:
    """Exposed ridges are windier than the valley station. +15% per 500 m, capped at 2x."""
    gain = max(to_m - from_m, 0.0)
    return wind_kmh * min(1.0 + 0.15 * gain / 500.0, 2.0)


def warmth_status(provided: float, required: float) -> str:
    margin = provided - required
    if margin >= 0:
        return "covered"
    if margin >= -MARGINAL_CLO:
        return "marginal"
    return "cold"
