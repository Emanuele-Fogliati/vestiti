"""What a traveller means, typed or spoken (Manu, 2026-11-12: "ti parlo e dico qual è la mia
idea e tu crei il viaggio").

Three cases, read without guessing:
- stops: "Buenos Aires dal 6 all'8 gennaio, poi 3 giorni a El Chaltén e Torres del Paine";
- a region or a country: "Patagonia a gennaio per tre settimane" (the route is proposed by
  app.services.explore);
- just a wish: "qualcosa di caldo a febbraio".

Dates, months, lengths and places are read by rules in Italian, English and Spanish: a
spoken sentence is messy and a small local model gets it wrong. Places are the globe's
places named in the text. What is missing (when, how long) is asked, never invented.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from functools import lru_cache

from app.places.countries import norm
from app.services import explore

MONTHS = {
    1: ["gennaio", "january", "enero"], 2: ["febbraio", "february", "febrero"],
    3: ["marzo", "march"], 4: ["aprile", "april", "abril"], 5: ["maggio", "may", "mayo"],
    6: ["giugno", "june", "junio"], 7: ["luglio", "july", "julio"], 8: ["agosto", "august"],
    9: ["settembre", "september", "septiembre", "setiembre"], 10: ["ottobre", "october", "octubre"],
    11: ["novembre", "november", "noviembre"], 12: ["dicembre", "december", "diciembre"],
}
SHORT = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
         "oct": 10, "nov": 11, "dec": 12, "gen": 1, "giu": 6, "lug": 7, "ago": 8, "set": 9, "ott": 10, "dic": 12}
MONTH_OF = {w: m for m, ws in MONTHS.items() for w in ws}
NUM = {
    "un": 1, "uno": 1, "una": 1, "a": 1, "one": 1, "due": 2, "two": 2, "dos": 2, "tre": 3, "three": 3, "tres": 3,
    "quattro": 4, "four": 4, "cuatro": 4, "cinque": 5, "five": 5, "cinco": 5, "sei": 6, "six": 6, "seis": 6,
    "sette": 7, "seven": 7, "siete": 7, "otto": 8, "eight": 8, "ocho": 8, "nove": 9, "nine": 9, "nueve": 9,
    "dieci": 10, "ten": 10, "diez": 10, "undici": 11, "eleven": 11, "once": 11, "dodici": 12, "twelve": 12,
    "doce": 12, "tredici": 13, "thirteen": 13, "quattordici": 14, "fourteen": 14, "catorce": 14,
    "quindici": 15, "fifteen": 15, "quince": 15, "venti": 20, "twenty": 20, "veinte": 20, "trenta": 30,
    "thirty": 30, "treinta": 30, "paio": 2, "couple": 2, "qualche": 3, "few": 3,
}
UNIT = {"giorno": 1, "giorni": 1, "giornata": 1, "giornate": 1, "day": 1, "days": 1, "dia": 1, "dias": 1,
        "notte": 1, "notti": 1, "night": 1, "nights": 1, "noche": 1, "noches": 1,
        "settimana": 7, "settimane": 7, "week": 7, "weeks": 7, "semana": 7, "semanas": 7,
        "mese": 30, "mesi": 30, "month": 30, "months": 30, "mes": 30, "meses": 30}
NIGHTS = {"notte", "notti", "night", "nights", "noche", "noches"}
# words that are also small places somewhere: never a stop unless written as a name
STOP = {"como", "nice", "split", "bath", "reading", "mobile", "male", "sale", "man", "rest", "sun", "may",
        "march", "most", "best", "grande", "bella", "vista", "verde", "santa", "san", "porto", "isola",
        "lago", "monte", "capo", "punta", "cabo", "rio", "playa", "villa", "porta", "casa", "mare", "sole",
        "luna", "tre", "poi", "dopo", "nord", "sud", "est", "ovest", "centro", "citta", "city", "beach",
        "paris texas", "golden", "bay", "lake", "park", "parco", "nuovo", "nueva", "new", "old", "vecchio",
        "alta", "bassa", "media", "calafate"}
WISHES = {
    "warm": ["caldo", "calde", "caldi", "sole", "warm", "hot", "sunny", "calor", "estate"],
    "beach": ["mare", "spiaggia", "spiagge", "beach", "beaches", "playa", "isole", "islands", "snorkeling"],
    "snow": ["neve", "sciare", "sci", "snow", "ski", "skiing", "nieve", "aurora", "aurore"],
    "mountains": ["montagna", "montagne", "trekking", "hiking", "escursioni", "mountains", "mountain", "montana", "camminare"],
    "city": ["citta", "city", "cities", "musei", "museums", "ciudad", "shopping"],
}
# what Italians and Spaniards call places the globe knows by their English name
EXONYMS = {
    "lisbona": "lisbon", "parigi": "paris", "londra": "london", "roma": "rome", "firenze": "florence",
    "venezia": "venice", "napoli": "naples", "milano": "milan", "torino": "turin", "genova": "genoa",
    "monaco di baviera": "munich", "vienna": "vienna", "praga": "prague", "atene": "athens", "mosca": "moscow",
    "pechino": "beijing", "citta del messico": "mexico city", "il cairo": "cairo", "cairo": "cairo",
    "siviglia": "seville", "sevilla": "seville", "barcellona": "barcelona", "edimburgo": "edinburgh",
    "bruxelles": "brussels", "varsavia": "warsaw", "cracovia": "krakow", "copenaghen": "copenhagen",
    "stoccolma": "stockholm", "ginevra": "geneva", "zurigo": "zurich", "lucerna": "lucerne", "berna": "bern",
    "nizza": "nice", "marsiglia": "marseille", "lione": "lyon", "tolosa": "toulouse", "dublino": "dublin",
    "oporto": "porto", "cordova": "cordoba", "salisburgo": "salzburg", "belgrado": "belgrade",
    "bucarest": "bucharest", "gerusalemme": "jerusalem", "citta del capo": "cape town", "nuova delhi": "new delhi",
    "katmandu": "kathmandu", "calcutta": "kolkata", "bombay": "mumbai", "saigon": "ho chi minh city",
    "nuova york": "new york", "new york city": "new york", "nuova orleans": "new orleans", "san paolo": "sao paulo",
    "l avana": "havana", "avana": "havana", "la habana": "havana", "cuzco": "cusco", "anversa": "antwerp",
    "bruges": "bruges", "colonia": "cologne", "francoforte": "frankfurt", "amburgo": "hamburg",
    "berlino": "berlin", "dresda": "dresden", "norimberga": "nuremberg", "lipsia": "leipzig",
    "san pietroburgo": "saint petersburg", "istanbul": "istanbul", "smirne": "izmir", "tunisi": "tunis",
    "algeri": "algiers", "tangeri": "tangier", "fes": "fez", "gerico": "jericho", "damasco": "damascus",
    "teheran": "tehran", "kyoto": "kyoto", "tokio": "tokyo", "seul": "seoul", "giacarta": "jakarta",
    "manila": "manila", "sydney": "sydney", "citta del vaticano": "vatican city", "siracusa": "syracuse",
    "padova": "padua", "mantova": "mantua", "bergamo": "bergamo", "dubrovnik": "dubrovnik",
    "spalato": "split", "zara": "zadar", "lubiana": "ljubljana", "salonicco": "thessaloniki", "creta": "crete",
    "rodi": "rhodes", "corfu": "corfu", "malaga": "malaga", "saragozza": "zaragoza", "granata": "granada",
    "lucca": "lucca", "pisa": "pisa", "siena": "siena", "assisi": "assisi",
}
END_LEAD = re.compile(r"\b(?:alla fine|per finire|infine|finendo|finire|finale|ultimo|ultima|at the end|ending|end|finish|finishing|"
                      r"finally|lastly|al final|terminando|terminar|acabando)\b(?:\s+\w+){0,2}\s+$")
HOME_LEAD = re.compile(r"\b(?:parto da|partendo da|partenza da|parto dall|volo da|from|leaving from|flying from|salgo da|desde)\s+$")


def _num(w: str) -> int | None:
    if w.isdigit():
        return int(w)
    return NUM.get(w)


@lru_cache
def _place_index() -> dict[str, list[dict]]:
    """Globe places by normalized name, most visited first."""
    from app import globe
    trips = explore._trips()
    idx: dict[str, list[dict]] = {}
    for p in globe.by_id().values():
        k = norm(p["name"])
        if len(k) < 3 or k in STOP:
            continue
        idx.setdefault(k, []).append(p)
    for k in idx:
        idx[k].sort(key=lambda p: -trips.get(p["id"], 0))
    return idx


def _lookup(k: str) -> list[dict] | None:
    idx = _place_index()
    return idx.get(k) or idx.get(EXONYMS.get(k, ""))


@lru_cache
def _max_words() -> int:
    return max(len(k.split()) for k in _place_index())


def _area_keys() -> set[str]:
    return {k for a in (*explore.regions(), *explore.countries()) for k in a["keys"]}


def find_places(text: str, only: list[str] | None = None) -> list[tuple[int, int, dict]]:
    """The globe's places named in a text: (start word, end word, place), in text order. A
    one-word name counts only when written with a capital (speech-to-text writes them so) or
    when it is long and unusual."""
    words_raw = re.findall(r"\w+", text)
    words = [norm(w) for w in words_raw]
    area_keys = _area_keys()
    out, i = [], 0
    while i < len(words):
        hit = None
        for n in range(min(_max_words(), len(words) - i), 0, -1):
            k = " ".join(w for w in words[i:i + n] if w)
            found = _lookup(k) if k and k not in area_keys else None
            if not found:
                continue
            if n == 1 and not (words_raw[i][:1].isupper() or len(k) >= 7 or k in EXONYMS):
                continue
            cands = [p for p in found if not only or p["country"] in only] or found
            hit = (i, i + n, cands[0])
            break
        if hit:
            out.append(hit)
            i = hit[1]
        else:
            i += 1
    return out


def _year_for(month: int, day: int, today: date) -> date:
    for y in (today.year, today.year + 1):
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if d >= today:
            return d
    return date(today.year + 1, month, min(day, 28))


def read(text: str, today: date | None = None) -> dict:
    """Everything a sentence says about a trip; see the module doc."""
    today = today or date.today()
    raw = text.strip()
    t = norm(raw)
    words = t.split()
    out: dict = {"text": raw[:500], "mode": "open", "area": None, "only": [], "month": None,
                 "start_date": None, "days": None, "stops": [], "home": None, "wishes": [], "missing": []}

    # ---- the area: a region or a country
    a, only = explore.best_area(raw)

    # ---- places, and where each sits in the words
    places = find_places(raw, only or None)
    raw_words = re.findall(r"\w+", raw)
    joined = " ".join(norm(w) for w in raw_words)
    nw = joined.split()
    home = None
    keep_places = []
    for s, e, p in places:
        before = " ".join(nw[max(0, s - 3):s]) + " "
        if HOME_LEAD.search(before) and not keep_places:
            home = p
            continue
        keep_places.append((s, e, p))
    places = keep_places
    # "e alla fine Ushuaia", "ending in Ushuaia": this place closes the trip
    last = [p["id"] for s, e, p in places if END_LEAD.search(" ".join(nw[max(0, s - 4):s]) + " ")]

    # ---- dates and lengths, each with where it sits
    spans: list[dict] = []
    mw = "|".join(MONTH_OF)
    # ranges with a month on both ends: "dal 16 gennaio 2027 al 30 gennaio 2027", "dal 28 gennaio al 5 febbraio"
    for m in re.finditer(r"\b(?:dal |from |del |tra il |between )?(\d{1,2}) (?:de )?(%s)(?: (?:de |del )?(20\d\d))? "
                         r"(?:al |to |all |a |till |until |e |and |y |hasta el |hasta |al dia )?(?:il |el |the )?"
                         r"(\d{1,2}) (?:de )?(%s)(?: (?:de |del )?(20\d\d))?\b" % (mw, mw), t):
        try:
            y1 = int(m.group(3)) if m.group(3) else None
            y2 = int(m.group(6)) if m.group(6) else y1
            m1, m2 = MONTH_OF[m.group(2)], MONTH_OF[m.group(5)]
            a1 = date(y1, m1, int(m.group(1))) if y1 else _year_for(m1, int(m.group(1)), today)
            a2 = date(y2, m2, int(m.group(4))) if y2 else _year_for(m2, int(m.group(4)), a1)
        except ValueError:
            continue
        if a1 <= a2 <= a1 + timedelta(days=120):
            spans.append({"at": m.start(), "end": m.end(), "kind": "range", "start": a1, "stop": a2})
    taken = [(s["at"], s["end"]) for s in spans]
    # ranges: "dal 6 al 20 gennaio", "6-8 gennaio", "from 6 to 20 january", "6 al 8 de enero"
    for m in re.finditer(r"\b(?:dal |from |del )?(\d{1,2}) (?:al |to |all |a |till |until |-|e )?(\d{1,2}) (?:de )?(%s)\b"
                         % "|".join(MONTH_OF), t):
        d1, d2, mo = int(m.group(1)), int(m.group(2)), MONTH_OF[m.group(3)]
        if 1 <= d1 <= 31 and 1 <= d2 <= 31 and d2 >= d1 and all(m.end() <= a0 or m.start() >= b0 for a0, b0 in taken):
            a1 = _year_for(mo, d1, today)
            spans.append({"at": m.start(), "end": m.end(), "kind": "range", "start": a1,
                          "stop": a1 + timedelta(days=d2 - d1)})
    taken = [(s["at"], s["end"]) for s in spans]

    def free(i: int, j: int) -> bool:
        return all(j <= a0 or i >= b0 for a0, b0 in taken)

    # "dall'11 al 13": the month is the next one named, else the one before
    for m in re.finditer(r"\b(?:dal |dall |from |del |tra il |between )?(\d{1,2}) (?:al|all|to|till|until|e|and|y) (\d{1,2})\b(?! (?:%s|%s))"
                         % ("|".join(MONTH_OF), "|".join(UNIT)), t):
        if not free(m.start(), m.end()):
            continue
        d1, d2 = int(m.group(1)), int(m.group(2))
        nxt = re.search(r"\b(%s)\b" % "|".join(MONTH_OF), t[m.end():])
        prev = [sp for sp in spans if sp["at"] < m.start() and "start" in sp]
        mo = MONTH_OF[nxt.group(1)] if nxt else (max(prev, key=lambda sp: sp["at"])["start"].month if prev else None)
        if mo and 1 <= d1 <= d2 <= 31:
            a1 = _year_for(mo, d1, today)
            if prev and a1 < max(prev, key=lambda sp: sp["at"])["start"]:
                a1 = _year_for(mo, d1, max(prev, key=lambda sp: sp["at"])["start"])
            spans.append({"at": m.start(), "end": m.end(), "kind": "range", "start": a1, "stop": a1 + timedelta(days=d2 - d1)})
            taken.append((m.start(), m.end()))
    for m in re.finditer(r"\b(\d{1,2}) (?:de )?(%s)\b" % "|".join([*MONTH_OF, *SHORT]), t):
        if not free(m.start(), m.end()):
            continue
        mo = MONTH_OF.get(m.group(2)) or SHORT[m.group(2)]
        d = int(m.group(1))
        if 1 <= d <= 31:
            spans.append({"at": m.start(), "end": m.end(), "kind": "date", "start": _year_for(mo, d, today)})
            taken.append((m.start(), m.end()))
    for m in re.finditer(r"\b(%s) (\d{1,2}) (?:to |till |until |through |thru |and |)(\d{1,2})\b(?! (?:%s)\b)" % (mw, "|".join(UNIT)), t):  # "january 16 to 30"
        d1, d2 = int(m.group(2)), int(m.group(3))
        if free(m.start(), m.end()) and 1 <= d1 <= d2 <= 31:
            a1 = _year_for(MONTH_OF[m.group(1)], d1, today)
            spans.append({"at": m.start(), "end": m.end(), "kind": "range", "start": a1, "stop": a1 + timedelta(days=d2 - d1)})
            taken.append((m.start(), m.end()))
    for m in re.finditer(r"\b(%s) (\d{1,2})\b(?! (?:%s)\b)" % ("|".join(MONTH_OF), "|".join(UNIT)), t):  # "january 6", not "gennaio 10 giorni"
        if free(m.start(), m.end()) and 1 <= int(m.group(2)) <= 31:
            spans.append({"at": m.start(), "end": m.end(), "kind": "date",
                          "start": _year_for(MONTH_OF[m.group(1)], int(m.group(2)), today)})
            taken.append((m.start(), m.end()))
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", raw):
        try:
            if m.group(1):
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            else:
                y = int(m.group(6)) if m.group(6) else None
                y = (2000 + y if y and y < 100 else y)
                d = date(y, int(m.group(5)), int(m.group(4))) if y else _year_for(int(m.group(5)), int(m.group(4)), today)
        except ValueError:
            continue
        spans.append({"at": len(norm(raw[:m.start()])) + 1, "end": len(norm(raw[:m.end()])) + 1, "kind": "date", "start": d})
    # a month alone: "a gennaio", "in January", "fine gennaio"
    month, part = None, None
    for m in re.finditer(r"\b(?:(inizio|fine|meta|early|late|mid|end of|beginning of|principios de|finales de|mediados de) (?:di |de |of )?)?(%s)\b"
                         % "|".join(MONTH_OF), t):
        if free(m.start(), m.end()):
            month, part = MONTH_OF[m.group(2)], m.group(1)
            break
    # lengths: "tre settimane", "10 giorni", "un mese", "a week", "weekend"
    for m in re.finditer(r"\b(\w+) (?:e mezzo |and a half )?(%s)\b" % "|".join(UNIT), t):
        n = _num(m.group(1))
        unit = m.group(2)
        if n is None:
            if m.group(1) in ("per", "for", "una", "un", "a", "the", "la", "il"):
                n = 1
            else:
                continue
        days = n * UNIT[unit] + (1 if unit in NIGHTS else 0)
        if "e mezzo" in m.group(0) or "and a half" in m.group(0):
            days += UNIT[unit] // 2
        if 1 <= days <= 120 and free(m.start(), m.end()):
            total = bool(re.match(r" ?(in tutto|in totale|totali|in total|total|overall|en total|al todo)\b", t[m.end():]))
            spans.append({"at": m.start(), "end": m.end(), "kind": "length", "days": days, "total": total})
    if re.search(r"\b(weekend|fine settimana|finde)\b", t) and not any(s["kind"] == "length" for s in spans):
        spans.append({"at": t.index(re.search(r"\b(weekend|fine settimana|finde)\b", t).group(0)), "end": 0,
                      "kind": "length", "days": 3})

    # ---- which date or length belongs to which place: the one right after it (or "3 giorni a X")
    char_at = []  # start char of each word in the normalized text
    pos = 0
    for w in nw:
        k = joined.index(w, pos)
        char_at.append(k)
        pos = k + len(w)
    pstarts = [(char_at[s], char_at[e - 1] + len(nw[e - 1]), p) for s, e, p in places]
    stop_info: list[dict] = [{"place": p, "days": None, "start": None, "stop": None} for _, _, p in pstarts]
    trip_len = None
    for sp in sorted(spans, key=lambda s: s["at"]):
        owner = None
        month_words = "|".join(MONTH_OF)
        for k, (ps, pe, _) in enumerate(pstarts):
            if sp.get("total"):
                break
            nxt = pstarts[k + 1][0] if k + 1 < len(pstarts) else len(joined) + 1
            gap = joined[pe:sp["at"]]
            if (pe <= sp["at"] < nxt and len(gap.split()) <= 2
                    and not re.search(r"\b(poi|then|luego|after|%s)\b" % month_words, gap)):
                owner = k
                break
            # "3 giorni a El Chaltén": the length right before the place
            before = joined[sp["end"]:ps] if sp["end"] <= ps else ""
            if sp["kind"] == "length" and sp["end"] <= ps and re.fullmatch(r" ?(a|ad|in|at|en|nel|nella|sul|sulla|al|alla|per|di|a l)? ?", before):
                owner = k
                break
        if owner is None:
            if sp["kind"] == "length" and trip_len is None:
                trip_len = sp["days"]
            elif sp["kind"] in ("date", "range") and out["start_date"] is None:
                out["start_date"] = sp["start"]
                if sp["kind"] == "range":
                    trip_len = trip_len or (sp["stop"] - sp["start"]).days + 1
            continue
        si = stop_info[owner]
        if sp["kind"] == "length" and si["days"] is None:
            si["days"] = sp["days"]
        elif sp["kind"] == "range":
            si["start"], si["stop"] = sp["start"], sp["stop"]
            si["days"] = (sp["stop"] - sp["start"]).days + 1
        elif sp["kind"] == "date" and si["start"] is None:
            si["start"] = sp["start"]

    if month and not out["start_date"]:
        out["month"] = month
        if part in ("fine", "late", "end of", "finales de"):
            out["start_date"] = _year_for(month, 20, today)
            out["start_part"] = "late"
        elif part in ("meta", "mid", "mediados de"):
            out["start_date"] = _year_for(month, 10, today)
            out["start_part"] = "mid"
        elif part in ("inizio", "early", "beginning of", "principios de"):
            out["start_date"] = _year_for(month, 1, today)
            out["start_part"] = "early"
    if out["start_date"] and not out["month"]:
        out["month"] = out["start_date"].month
    out["days"] = trip_len
    out["wishes"] = [k for k, ws in WISHES.items() if any(f" {w} " in f" {t} " for w in ws)]
    if home:
        out["home"] = {"name": home["name"], "country": home["country"], "lat": home["lat"], "lon": home["lon"]}

    # ---- what kind of trip this is
    inside_area = a is not None and all(explore.inside(a, p["lat"], p["lon"], p["country"], only) for _, _, p in places)
    dated = [si for si in stop_info if si["start"]]
    if a is not None and (not places or inside_area) and len(dated) <= 1:
        # "Patagonia ... e alla fine Ushuaia dal 16 al 30 gennaio": with a region named, the
        # dates of a single place are the trip's own (Manu, 2026-11-12)
        for si in dated:
            out["start_date"] = out["start_date"] or si["start"]
            if si["stop"] and not trip_len:
                trip_len = out["days"] = (si["stop"] - si["start"]).days + 1
        if out["start_date"]:
            out["month"] = out["start_date"].month
            out.pop("start_part", None)
        if out["days"] is None and trip_len:
            out["days"] = trip_len
        out["mode"] = "region"
        out["area"] = {"id": a["id"], "name": a["name"], "kind": a["kind"]}
        out["only"] = only
        out["keep"] = [p["id"] for _, _, p in places]
        out["last"] = last
    elif places:
        out["mode"] = "stops"
        out["stops"] = _stops(stop_info, out["start_date"], trip_len)
        first = out["stops"][0]["start_date"]
        if first:
            out["start_date"] = date.fromisoformat(first)
            out["month"] = out["start_date"].month
    if out["mode"] != "stops" and not out["days"]:
        out["missing"].append("how_long")
    if not out["start_date"] and not out["month"]:
        out["missing"].append("when")
    if out["mode"] == "open":
        out["missing"].insert(0, "where")
    return out


def _stops(info: list[dict], start: date | None, total: int | None) -> list[dict]:
    """Stops back to back. A stop's own dates win; a stop without a length shares what is
    left of the whole trip, else gets the usual days for its kind."""
    known = sum(i["days"] or 0 for i in info)
    unknown = [i for i in info if not i["days"]]
    share = None
    if total and unknown and total > known:
        share = max(1, (total - known) // len(unknown))
    out, cur = [], start
    for k, i in enumerate(info):
        p = i["place"]
        days = i["days"] or share or explore.DEFAULT_DAYS.get(p["kind"], 2)
        if total and unknown and i is unknown[-1] and share:
            days = max(1, total - known - share * (len(unknown) - 1))
        s0 = i["start"] or cur
        out.append({"key": p["id"], "place_id": p["id"], "name": p["name"], "country": p["country"],
                    "lat": p["lat"], "lon": p["lon"], "kind": p["kind"], "days": days,
                    "start_date": s0.isoformat() if s0 else None, "fixed_dates": bool(i["start"]),
                    "elevation_m": None, "activities": None, "sights": []})
        cur = (s0 + timedelta(days=days)) if s0 else None
    # "... then London from 3 March": the stops before a dated one end the day before it
    first = next((k for k, o in enumerate(out) if o["start_date"]), None)
    if first:
        d = date.fromisoformat(out[first]["start_date"])
        for o in reversed(out[:first]):
            d -= timedelta(days=o["days"])
            o["start_date"] = d.isoformat()
    return out
