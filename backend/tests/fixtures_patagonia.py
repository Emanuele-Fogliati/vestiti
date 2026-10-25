"""A shortened agency-style program, like the ones people paste from a tour operator."""

BOILER = ("La quota comprende: voli interni, hotel indicati o similari, guide locali in italiano. "
          "La quota non comprende: assicurazione, mance, pasti non indicati. ")

PATAGONIA = f"""Patagonia Express: dal 16 al 30 maggio 2027
Giorno
1
Italia - Buenos Aires
Partenza con volo intercontinentale per Buenos Aires. Pasti e pernottamento a bordo.
Giorno
2
Buenos Aires
Arrivo e trasferimento in hotel. Pomeriggio visita della città: Plaza de Mayo, La Boca.
Giorno
3
Buenos Aires - El Calafate
Volo per El Calafate. Pomeriggio libero. {BOILER}
Giorno
4
El Calafate
Escursione al ghiacciaio Perito Moreno con minitrekking sul ghiaccio con ramponi. {BOILER}
Giorno
5
El Calafate - El Chaltén
Trasferimento in bus a El Chaltén, capitale del trekking.
Giorno
6
El Chaltén
Trekking alla Laguna de los Tres (1200 m), impegnativo, 10 ore.
Giorno
7
El Chaltén
Giornata di riserva in caso di maltempo.
Giorno
8
El Chaltén - Puerto Natales
Trasferimento in Cile.
Giorno
9
Torres del Paine
Escursione facile al Mirador Las Torres e rafting sul fiume Serrano.
Giorno
10
Torres del Paine
Navigazione sul Lago Grey in catamarano.
Giorno
11
Torres del Paine - Ushuaia
Volo per Ushuaia.
Giorno
12
Ushuaia
Navigazione nel Canale di Beagle in barca.
Giorno
13
Ushuaia
Escursione nel Parco Nazionale Terra del Fuoco.
Giorno
14
Ushuaia - Italia
Volo di rientro.
Giorno
15
Italia
Arrivo in Italia.
"""

# what a small local model returned on the real program: one stop per day,
# every day a hard multi-day trek at 2,500 m, English notes with the agency boilerplate
NOTE = "Price includes internal flights, hotels and local guides; insurance not included."


def _day(name, d, t="trek_multiday", alt=2500):
    return {"name": name, "start_date": f"2027-05-{d:02d}", "end_date": f"2027-05-{d:02d}",
            "activities": [{"type": t, "difficulty": "hard", "max_altitude_m": alt}], "notes": NOTE}


BAD_LLM = {"trip_name": "Patagonia Express", "questions": ["What is your shoe size?"], "stops": [
    _day("Buenos Aires", 17, "city", None), _day("Buenos Aires", 18),
    _day("El Calafate", 19), _day("El Calafate", 20),
    _day("El Chaltén", 21), _day("El Chaltén", 22), _day("El Chaltén", 23),
    _day("Puerto Natales", 24, "city", None),
    _day("Torres del Paine", 25, "safari", None), _day("Torres del Paine", 26, "safari", None),
    _day("Ushuaia", 27), _day("Ushuaia", 28, "safari", None), _day("Ushuaia", 29),
    _day("Ushuaia", 30, "city", None),
]}
