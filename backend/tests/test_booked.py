"""A trip already booked, told in detail (app.services.booked): Manu's own Patagonia text."""
from datetime import date
from pathlib import Path

from app.services import booked

TODAY = date(2026, 11, 14)
MANU = (Path(__file__).parent / "fixtures" / "booked_patagonia_it.txt").read_text(encoding="utf-8")


def test_reads_where_you_sleep():
    r = booked.read(MANU, TODAY)
    assert r["mode"] == "booked"
    beds = [(s["name"], s["start_date"], s["days"], s.get("lodging"), s.get("address")) for s in r["stops"] if s["kind"] != "transit"]
    assert beds == [
        ("Puerto Natales", "2027-01-17", 5, "Hostal Turpial Patagonia", "Manuel Bulnes 354"),
        ("El Chaltén", "2027-01-22", 4, "Patagonia Hostel", "Avenida San Martín 376"),
        ("Ushuaia", "2027-01-26", 3, "Ushuaia Center Apartment Suit", "Gobernador Deloqui 373"),
    ]
    assert r["start_date"] == "2027-01-16" and r["end_date"] == "2027-01-30" and r["days"] == 15 and r["nights"] == 12
    assert r["home"]["name"] == "Turin"


def test_reads_every_move_with_its_times():
    legs = [(lg["date"], lg["mode"], lg["from"], lg["to"], lg["dep"], lg["arr"]) for lg in booked.read(MANU, TODAY)["legs"]]
    assert legs == [
        ("2027-01-16", "flight", "Turin", "Buenos Aires", "11:15", "04:40"),
        ("2027-01-17", "flight", "Buenos Aires", "El Calafate", "08:10", "11:30"),
        ("2027-01-17", "car", "El Calafate", "Puerto Natales", "12:00", "17:30"),
        ("2027-01-22", "car", "Puerto Natales", "El Chaltén", "07:00", None),
        ("2027-01-26", "car", "El Chaltén", "El Calafate", "07:00", None),
        ("2027-01-26", "flight", "El Calafate", "Ushuaia", "17:20", "18:40"),
        ("2027-01-29", "flight", "Ushuaia", "Buenos Aires", "08:20", "11:50"),
        ("2027-01-29", "taxi or bus", "Buenos Aires", "Buenos Aires", None, None),
        ("2027-01-29", "flight", "Buenos Aires", "Rome", "22:35", "16:00"),
        ("2027-01-30", "flight", "Rome", "Turin", "17:20", "18:35"),
    ]
    lg = booked.read(MANU, TODAY)["legs"]
    assert lg[0]["via"] == ["Rome"] and lg[0]["to_airport"] == "Ezeiza" and lg[0]["arr_date"] == "2027-01-17"
    assert lg[2]["notes"] == ["Pick up the car (Hertz)", "Border: Río Turbio–Dorotea"]
    assert "Border: Cerro Castillo" in lg[3]["notes"] and lg[3]["via"] == ["El Calafate"]
    assert lg[4]["stops"] == [{"name": "Perito Moreno Glacier", "when": "late morning"}]
    assert lg[4]["notes"] == ["Car back by 16:00"]
    assert lg[6]["notes"] == ["Leave at 06:15"] and lg[8]["arr_date"] == "2027-01-30"


def test_plans_the_free_days_around_each_base():
    r = booked.read(MANU, TODAY)
    by = {s["name"]: s for s in r["stops"]}
    natales = [i["id"] for d in by["Puerto Natales"]["plan"] for i in d.get("items", [])]
    # "da qui si va e si torna ogni giorno da Torres del Paine": the park's own days, no van tour
    assert by["Puerto Natales"]["day_trips"] == ["Torres del Paine"]
    assert {"base-torres", "french-valley"} <= set(natales) and "tdp-day-tour" not in natales
    assert by["Puerto Natales"]["plan"][0]["items"][0]["id"] == "waterfront"  # 17:30: the evening in town
    chalten = [i["id"] for d in by["El Chaltén"]["plan"] for i in d.get("items", [])]
    assert {"laguna-de-los-tres", "laguna-torre"} <= set(chalten)
    ush = by["Ushuaia"]["plan"]
    assert ush[0]["items"] == [] and "Perito Moreno Glacier" in ush[0]["sights"]  # lands 18:40
    # 11:50 to 22:35 in Buenos Aires: a day there
    assert by["Buenos Aires"]["kind"] == "transit" and by["Buenos Aires"]["start_date"] == "2027-01-29"


def test_timeline_has_every_day_and_bed():
    t = booked.read(MANU, TODAY)["timeline"]
    assert len(t) == 15
    assert t[0]["sleep"] == {"in_the_air": True}
    assert t[1]["sleep"]["name"] == "Hostal Turpial Patagonia" and t[1]["stop_day"] == 1
    assert t[13]["sleep"] == {"in_the_air": True} and t[14]["sleep"] is None


def test_short_texts_stay_with_the_short_reader():
    for text in ("Patagonia in January, three weeks", "Rome 3 nights, Florence 2 nights from 10 May",
                 "Buenos Aires dal 6 all'8 gennaio, poi El Calafate 9-10 gennaio"):
        assert booked.read(text, TODAY) is None, text


def test_api_takes_a_long_text(client):
    client.post("/api/auth/guest")
    long = MANU + "\n\n" + ("Note: " + "x" * 90 + ".\n") * 400  # about 40,000 characters
    assert len(long) > 30000
    r = client.post("/api/plan/understand", json={"text": long})
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "booked"
    assert client.post("/api/plan/understand", json={"text": "x" * 50001}).status_code == 422
    j = r.json()
    t = client.post("/api/plan/trip", json={"stops": j["stops"], "start_date": j["start_date"], "home": j["home"]})
    assert t.status_code == 201, t.text
    got = [(s["name"], s["start_date"], s["end_date"]) for s in t.json()["stops"]]
    assert got[0] == ("Puerto Natales", "2027-01-17", "2027-01-21") and got[-1][1] == "2027-01-29"
