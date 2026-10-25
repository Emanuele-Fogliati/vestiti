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
Arrivo e trasferimento in hotel. Pomeriggio visita della città: Plaza de Mayo, La Boca. Si consigliano scarpe comode per i sentieri del parco della Reserva Ecológica.
Giorno
3
Buenos Aires - El Calafate
Volo per El Calafate. Pomeriggio libero. {BOILER}
Giorno
4
El Calafate
Escursione al ghiacciaio Perito Moreno con minitrekking sul ghiaccio con ramponi (1 ora e mezza). {BOILER}
Giorno
5
El Calafate - El Chaltén
Trasferimento in bus a El Chaltén, capitale del trekking.
Giorno
6
El Chaltén
Trekking alla Laguna de los Tres (1200 m), 8 ore di cammino. Abbigliamento a strati, scarponi impermeabili e protezione solare.
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
Trekking al Mirador Base Torres, 7-9 ore. Rafting sul fiume Serrano.
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
Trekking alla Laguna Esmeralda, 8 ore su neve e ghiaccio con ramponi. Volo panoramico di 1 ora facoltativo.
Giorno
14
Ushuaia - Italia
Volo di rientro.
Giorno
15
Italia
Arrivo in Italia.

Abbigliamento e attrezzatura:
Si consiglia abbigliamento a strati, scarponi da trekking impermeabili per i sentieri, bastoncini.
La quota comprende: voli, hotel, escursioni e trekking indicati.
"""

# what a small local model returned on the real program: one stop per day,
# every day a hard multi-day trek at 2,500 m, English notes with the agency boilerplate
NOTE = "Price includes internal flights, hotels and local guides; insurance not included."
GEAR = ("Si consiglia abbigliamento a strati, scarponi impermeabili e protezione solare. "
        "Giornata dedicata alla scoperta dei dintorni con guida locale esperta in lingua italiana")


def _day(name, d, t="trek_multiday", alt=2500):
    return {"name": name, "start_date": f"2027-05-{d:02d}", "end_date": f"2027-05-{d:02d}",
            "activities": [{"type": t, "difficulty": "hard", "max_altitude_m": alt}], "notes": NOTE}


BAD_LLM = {"trip_name": "Patagonia Express",
           "questions": ["Quali sono le date esatte del viaggio?", "Che taglia porti?"], "stops": [
    _day("Buenos Aires", 17, "hiking", None), _day("Buenos Aires", 18),
    _day("El Calafate", 19), _day("El Calafate", 20),
    _day("El Chaltén", 21), _day("El Chaltén", 22), _day("El Chaltén", 23),
    _day("Puerto Natales", 24, "hiking", None),
    _day("Torres del Paine", 25, "safari", None), _day("Torres del Paine", 26, "safari", None),
    _day("Ushuaia", 27), _day("Ushuaia", 28, "safari", None), _day("Ushuaia", 29),
    _day("Ushuaia", 30, "city", None),
]}

BAD_LLM["stops"][-2]["notes"] = GEAR
BAD_LLM["stops"][5]["notes"] = GEAR


# The generator used for the PC tests: the same 15 days, with or without agency filler
GEN_DAYS = [
    ("Buenos Aires", "Arrivo all'aeroporto di Ezeiza, trasferimento in hotel e visita a piedi del quartiere di San Telmo e della Plaza de Mayo."),
    ("Buenos Aires", "Giornata dedicata alla città: La Boca, Caminito, Recoleta e serata di tango a Palermo."),
    ("El Chaltén", "Volo per El Calafate e trasferimento in bus a El Chaltén, la capitale del trekking argentino."),
    ("El Chaltén", "Trekking alla Laguna de los Tres, 8-10 ore con l'ultimo tratto molto ripido sotto il Fitz Roy."),
    ("El Chaltén", "Giornata di riserva meteo, breve escursione al Mirador de los Cóndores."),
    ("El Calafate", "Rientro a El Calafate e pomeriggio di rafting sul fiume."),
    ("El Calafate", "Minitrekking sul ghiacciaio Perito Moreno con ramponi, poi passerelle panoramiche."),
    ("Puerto Natales", "Attraversamento della frontiera con il Cile e arrivo a Puerto Natales."),
    ("Torres del Paine", "Trekking al Mirador Base Torres, 7-9 ore, vento forte e possibile neve in quota."),
    ("Torres del Paine", "Giro in barca sul lago Grey e sentieri panoramici del parco."),
    ("Ushuaia", "Volo per Ushuaia, Terra del Fuoco, passeggiata sul lungomare."),
    ("Ushuaia", "Escursione in barca sul Canale di Beagle con l'isola dei leoni marini e il faro Les Eclaireurs."),
    ("Ushuaia", "Trekking alla Laguna Esmeralda e all'Ojo del Albino con ramponi sul ghiaccio, circa 8 ore."),
    ("Ushuaia", "Mattina libera, poi volo di rientro verso Buenos Aires."),
    ("Buenos Aires", "Ultima giornata a Buenos Aires e volo intercontinentale di ritorno."),
]
GEN_FILLER = (" Il programma comprende guida locale in italiano, pranzo al sacco, assicurazione, "
              "trasferimenti privati e assistenza 24 ore su 24. Si consiglia abbigliamento a strati, "
              "scarponi impermeabili e protezione solare. Gli orari possono cambiare in base al meteo "
              "e alle condizioni dei sentieri; la guida decide sul posto eventuali variazioni.")


def generated(filler_times: int) -> str:
    parts = ["Programma di viaggio Patagonia dal 16 al 30 maggio 2027, proposto dall'agenzia.\n"]
    for i, (place, desc) in enumerate(GEN_DAYS, start=1):
        parts.append(f"Giorno {i} - {place}: {desc}" + GEN_FILLER * filler_times + "\n")
    return "\n".join(parts)


GEN_EXPECTED = [("Buenos Aires", 16, 17), ("El Chaltén", 18, 20), ("El Calafate", 21, 22),
                ("Puerto Natales", 23, 23), ("Torres del Paine", 24, 25), ("Ushuaia", 26, 29),
                ("Buenos Aires", 30, 30)]


def _stop(name, a, b, acts):
    return {"name": name, "start_date": f"2027-05-{a:02d}", "end_date": f"2027-05-{b:02d}",
            "activities": acts, "notes": None}


_H = [{"type": "hiking", "difficulty": "moderate", "max_altitude_m": None}]
# what the PC model returned on the short version: right stops, compressed dates,
# a hike on every stop, an invented question
GEN_BAD_LLM = {"trip_name": "Patagonia", "questions": ["Farai la gita in barca con lezioni di navigazione?"],
               "stops": [_stop("Buenos Aires", 16, 16, _H), _stop("El Chaltén", 16, 17, _H),
                         _stop("El Calafate", 18, 19, _H), _stop("Puerto Natales", 20, 20, _H),
                         _stop("Torres del Paine", 21, 22, _H), _stop("Ushuaia", 23, 25, _H),
                         _stop("Buenos Aires", 26, 26, _H)]}
