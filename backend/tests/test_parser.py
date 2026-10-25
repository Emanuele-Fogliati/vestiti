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
