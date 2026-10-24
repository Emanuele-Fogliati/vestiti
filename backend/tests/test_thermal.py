from app.engine import thermal as T


def test_required_clo_grows_as_it_gets_colder():
    warm = T.required_clo(20, 5, met=2.0, moving=False)
    cold = T.required_clo(0, 5, met=2.0, moving=False)
    assert cold > warm >= 0


def test_moving_needs_less_than_resting():
    assert T.required_clo(0, 10, met=6.0, moving=True) < T.required_clo(0, 10, met=1.5, moving=False)


def test_short_stop_and_personal_offset():
    base = T.required_clo(5, 10, met=1.5, moving=False)
    assert T.required_clo(5, 10, met=1.5, moving=False, short_stop=True) < base
    assert T.required_clo(5, 10, met=1.5, moving=False, personal_offset=0.2) == round(base + 0.2, 2)


def test_hot_weather_needs_no_insulation():
    assert T.required_clo(34, 5, met=2.0, moving=True) == 0


def test_ensemble_formula():
    assert T.ensemble_clo([]) == 0
    assert abs(T.ensemble_clo([0.2, 0.3]) - (0.835 * 0.5 + 0.161)) < 1e-9


def test_wind_and_wet_penalties_only_when_cold():
    base, _ = T.effective_clo([0.3, 0.6], 5, False, False, False, temp_c=0)
    windy, notes = T.effective_clo([0.3, 0.6], 30, False, False, False, temp_c=0)
    assert windy < base and notes
    shell, _ = T.effective_clo([0.3, 0.6], 30, True, False, False, temp_c=0)
    assert shell == base
    wet_down, _ = T.effective_clo([0.3, 0.6], 5, False, True, False, down_worn=True, temp_c=0)
    wet, _ = T.effective_clo([0.3, 0.6], 5, False, True, False, temp_c=0)
    assert wet_down < wet < base
    hot_windy, notes = T.effective_clo([0.3], 30, False, True, False, temp_c=25)
    assert notes == [] and hot_windy == T.effective_clo([0.3], 0, False, False, False, temp_c=25)[0]


def test_altitude_and_wind_chill():
    assert T.lapse_adjust(20, 0, 2000) == 20 - 13
    assert T.altitude_wind(10, 0, 1000) > 10
    assert T.altitude_wind(10, 0, 9000) <= 20  # capped at 2x
    assert T.wind_chill_c(-5, 30) < -5
    assert T.feels_like_c(25, 30) == 25  # no wind chill when warm


def test_warmth_status():
    assert T.warmth_status(1.2, 1.0) == "covered"
    assert T.warmth_status(0.9, 1.0) == "marginal"
    assert T.warmth_status(0.5, 1.0) == "cold"
