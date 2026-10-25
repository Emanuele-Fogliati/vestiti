from datetime import date

from app.llm.itinerary import parse_itinerary

TODAY = date(2026, 10, 24)


def test_english_multi_stop():
    d = parse_itinerary("From 12 June 2027: 3 days in Reykjavik, then 4 days hard trekking in Landmannalaugar "
                        "up to 1100 m, then 2 days in Rome", TODAY, use_llm=False)
    assert [s.name for s in d.stops] == ["Reykjavik", "Landmannalaugar", "Rome"]
    assert d.stops[0].start_date == date(2027, 6, 12)
    assert (d.stops[1].end_date - d.stops[1].start_date).days == 3
    hike = d.stops[1].activities[0]
    assert hike.type == "hiking" and hike.difficulty == "hard" and hike.max_altitude_m == 1100
    assert d.stops[1].start_date > d.stops[0].end_date


def test_italian_unknown_difficulty():
    d = parse_itinerary("Dal 3 agosto 2027: 3 giorni a Chamonix escursioni non so quanto difficile, poi 2 giorni a Roma",
                        TODAY, use_llm=False)
    assert [s.name for s in d.stops] == ["Chamonix", "Roma"]
    assert d.stops[0].activities[0].difficulty == "unknown"
    assert d.questions  # asks how high the hike goes


def test_llm_disabled_falls_back_to_rules():
    d = parse_itinerary("From 1 May 2027: 2 days in Paris", TODAY)
    assert d.parser == "rules" and d.stops[0].name == "Paris"


AGENCY = """Programma di viaggio dal 5 maggio 2027
Giorno
1
Italia - Lima
Partenza con volo per Lima. Trasferimento in hotel e pernottamento.
Giorno
2
Lima
Alla scoperta della city: centro storico e museo Larco.
Giorno
3
Lima - Cusco
Volo per Cusco a 3400 m.
Giorno
4
Cusco
Visita della città.
Giorno
5
Valle Sacra
Escursione facile nella valle.
"""


def test_agency_day_by_day_merges_days_per_place():
    d = parse_itinerary(AGENCY, TODAY, use_llm=False)
    assert [s.name for s in d.stops] == ["Lima", "Cusco", "Valle Sacra"]
    assert d.stops[0].start_date == date(2027, 5, 5) and d.stops[0].end_date == date(2027, 5, 6)
    assert d.stops[1].start_date == date(2027, 5, 7) and d.stops[1].end_date == date(2027, 5, 8)
    assert d.stops[2].activities[0].type == "hiking"


def test_agency_program_skips_home_and_reads_activities():
    from tests.fixtures_patagonia import PATAGONIA
    d = parse_itinerary(PATAGONIA, TODAY, use_llm=False)
    names = [s.name for s in d.stops]
    assert names == ["Buenos Aires", "El Calafate", "El Chaltén", "Puerto Natales",
                     "Torres del Paine", "Ushuaia"]
    by = {s.name: s for s in d.stops}
    assert by["El Chaltén"].start_date == date(2027, 5, 20) and by["El Chaltén"].end_date == date(2027, 5, 22)
    chalten = by["El Chaltén"].activities[0]
    assert chalten.type == "hiking" and chalten.difficulty == "hard" and chalten.max_altitude_m == 1200
    assert {a.type for a in by["Torres del Paine"].activities} == {"hiking", "boat"}
    assert all(a.type != "trek_multiday" for s in d.stops for a in s.activities)
    assert by["El Calafate"].activities[0].max_altitude_m is None  # glacier minitrek: no number given


def test_questions_follow_the_language_of_the_text():
    d = parse_itinerary("3 giorni a Roma poi escursioni a Chamonix", TODAY, use_llm=False)
    assert d.questions and all("?" in q for q in d.questions)
    assert any(q.startswith("Quando parti") for q in d.questions)


def test_altitude_with_thousands_separator():
    d = parse_itinerary("Dal 3 agosto 2027: 4 giorni di trekking impegnativo a Zermatt fino a 3.100 m", TODAY, use_llm=False)
    a = d.stops[0].activities[0]
    assert a.type == "hiking" and a.difficulty == "hard" and a.max_altitude_m == 3100


def test_notes_drop_packing_advice_and_cut_on_a_boundary():
    from app.llm.itinerary import clean_note
    assert clean_note("Si consiglia abbigliamento a strati e scarponi impermeabili.") is None
    long = "Trekking alla Laguna de los Tres con vista sul Fitz Roy " * 5
    out = clean_note(long)
    assert len(out) <= 161 and out.endswith("…") and not out[:-1].endswith(" ")
    assert long.startswith(out[:-1])
