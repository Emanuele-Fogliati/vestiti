"""A trip already booked, told in detail (Manu, 2026-11-14): flights with their times, the car
picked up and returned, borders, and where you sleep each night with the address.

"Si parte sabato 16 gennaio da Torino alle 11:15, con scalo a Roma ... A Puerto Natales si dorme
cinque notti, dal 17 al 22 gennaio, all'Hostal Turpial Patagonia, in Manuel Bulnes 354 ..."

The places where you sleep become the stops, with their nights and dates as written; every move
becomes a leg on its day (flight, car, taxi or bus) with its times, layovers, borders and what you
stop to see on the way; a long wait in a city between two flights becomes a day there. Then the
free days around each base get what a local guide would do (explore._guide_days).

Rules, no AI: the same text always reads the same way. Italian first, English and Spanish words
where they cost nothing. A text without a night somewhere is not this: read() returns None and the
short reader (understand.read) takes it.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from functools import lru_cache

from app.places.countries import norm
from app.services import explore, understand

WEEKDAYS = {
    0: ["lunedi", "lunedì", "monday", "lunes"], 1: ["martedi", "martedì", "tuesday", "martes"],
    2: ["mercoledi", "mercoledì", "wednesday", "miercoles", "miércoles"],
    3: ["giovedi", "giovedì", "thursday", "jueves"], 4: ["venerdi", "venerdì", "friday", "viernes"],
    5: ["sabato", "saturday", "sabado", "sábado"], 6: ["domenica", "sunday", "domingo"],
}
WEEKDAY_OF = {w: d for d, ws in WEEKDAYS.items() for w in ws}
_WD = "|".join(sorted(WEEKDAY_OF, key=len, reverse=True))
_MO = "|".join(sorted(understand.MONTH_OF, key=len, reverse=True))

# airports written instead of their city ("si arriva a Fiumicino")
AIRPORTS = {
    "ezeiza": ("Buenos Aires", "Ezeiza"), "aeroparque": ("Buenos Aires", "Aeroparque"),
    "fiumicino": ("Rome", "Fiumicino"), "ciampino": ("Rome", "Ciampino"),
    "malpensa": ("Milan", "Malpensa"), "linate": ("Milan", "Linate"), "caselle": ("Turin", "Caselle"),
    "orio al serio": ("Bergamo", "Orio al Serio"), "marco polo": ("Venice", "Marco Polo"),
    "barajas": ("Madrid", "Barajas"), "el prat": ("Barcelona", "El Prat"),
    "heathrow": ("London", "Heathrow"), "gatwick": ("London", "Gatwick"),
    "charles de gaulle": ("Paris", "Charles de Gaulle"), "orly": ("Paris", "Orly"),
    "jfk": ("New York", "JFK"), "arturo merino benitez": ("Santiago", "Arturo Merino Benítez"),
    "guarulhos": ("São Paulo", "Guarulhos"), "jorge chavez": ("Lima", "Jorge Chávez"),
    "keflavik": ("Reykjavik", "Keflavík"),
}

TIME = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
NIGHTS_RE = re.compile(r"\b(\w+)\s+(?:notti|notte|nights?|noches?)\b", re.I)
SLEEP = re.compile(r"\b(?:si dorme|dormiamo|dormo|dormire|pernott\w*|alloggi\w*|soggiorn\w*|sleep\w*|"
                   r"stay(?:ing)?|we stay|duerm\w*|dormimos|alojamiento)\b|\b(?:notti|nights|noches)\b", re.I)
RANGE = re.compile(rf"\b(?:dal|from|del|tra il|between)\s+(\d{{1,2}})(?:\s+(?:di\s+|de\s+)?({_MO}))?\s+"
                   rf"(?:al|to|until|till|and|e il|y el|hasta el)\s+(\d{{1,2}})(?:\s+(?:di\s+|de\s+)?({_MO}))?", re.I)
DASH_RANGE = re.compile(rf"\b(\d{{1,2}})\s*[-–]\s*(\d{{1,2}})\s+(?:di\s+|de\s+)?({_MO})\b", re.I)
LODGING = re.compile(r"(?:\ball['’]|\b(?:al|alla|allo|presso(?:\s+l['’])?|at(?:\s+the)?|en(?:\s+el)?)\s+)"
                     r"((?:[A-ZÀ-Ý0-9][\w'’&.\-]*)(?:\s+(?:[A-ZÀ-Ý0-9de][\w'’&.\-]*))*)")
ADDRESS = re.compile(r",\s*(?:in|at|en|via|calle)\s+([^,.;\n]*\d[^,.;\n]*)", re.I)

FLIGHT = re.compile(r"\b(?:vol[oiae]|vola|voliamo|flight|fly|flies|flying|vuelo|vuela|atterr\w*|decoll\w*|lands?|landing)\b", re.I)
ARRIVE = re.compile(r"\b(?:arriv\w*|atterr\w*|lands?|landing|lleg\w*|reach\w*)\b", re.I)
DEPART = re.compile(r"\b(?:si parte|partiamo|parto|parte|partenza|si esce|usciamo|leav\w*|depart\w*|salimos|sale|"
                    r"si prosegue|proseguiamo|continu\w+|ripart\w*)\b", re.I)
CAR = re.compile(r"\b(?:auto|macchina|car|coche|camper|guid\w+|drive|driving|manej\w*)\b", re.I)
PICKUP = re.compile(r"\b(?:ritir\w*|noleggi\w*|prend\w*|pick(?:s|ing)?\s+up|recog\w*|rent\w*)\b", re.I)
RETURN = re.compile(r"\b(?:restitu\w*|riconsegn\w*|lasciare|lascia|return\w*|drop(?:s|ping)?\s+off|devol\w*|entreg\w*)\b", re.I)
BORDER = re.compile(r"\b(?:frontier\w*|confine|dogana|border|frontera|paso fronterizo)\b(?:\s+(?:di|de|at|of|del))?\s*(.*)", re.I)
VIA = re.compile(r"\b(?:scalo|layover|stopover|connection|via|attravers\w*|cross(?:es|ing)?|through|passando per|escala)\b", re.I)
STOPBY = re.compile(r"\b(?:ci si ferma|si ferma|fermata|sosta|stop(?:ping)?\s+(?:at|by)|paramos|parada)\b", re.I)
TRANSFER = re.compile(r"\b(taxi|bus|autobus|pullman|navetta|shuttle|transfer|metro|treno|train|tren|traghetto|ferry|barca|boat|uber|remis)\b", re.I)
DAYTRIPS = re.compile(r"\b(?:ogni giorno|tutti i giorni|every day|each day|day trips?|in giornata|cada d[ií]a|si va e si torna)\b", re.I)
HOURS = re.compile(r"(\d+(?:\s*[-–]\s*\d+)?)\s*(?:ore|hours?|h|horas)\b", re.I)
PART = {"mattin": "morning", "morning": "morning", "mañana": "morning", "pomeriggio": "afternoon",
        "afternoon": "afternoon", "tarde": "afternoon", "sera": "evening", "evening": "evening", "notte": "night",
        "night": "night", "noche": "night", "tarda mattinata": "late morning", "late morning": "late morning",
        "mezzogiorno": "midday", "noon": "midday"}
TRANSFER_NAME = {"autobus": "bus", "pullman": "bus", "navetta": "shuttle", "treno": "train", "tren": "train",
                 "traghetto": "ferry", "barca": "boat", "remis": "taxi"}


@lru_cache(maxsize=1)
def _aliases() -> dict[str, tuple[str, object]]:
    """Names of the hand-written guide areas ("Natales", "Perito Moreno") -> (name, area)."""
    from app.guide.todo import areas
    out: dict[str, tuple[str, object]] = {}
    for a in areas():
        for n in a.names:
            k = norm(n)
            if len(k) >= 5 and k not in understand.STOP:
                out.setdefault(k, (n, a))
    return out


def _place_of_area(a) -> dict:
    return {"id": None, "name": a.names[0], "country": a.country, "lat": a.lat, "lon": a.lon, "kind": "town"}


def _places(clause: str) -> list[dict]:
    """The places named in a clause, in order: {name, place, origin (written after "da"/"from"),
    airport}."""
    words = re.findall(r"\w+", clause)
    low = [norm(w) for w in words]
    found: dict[int, dict] = {}
    for i, j, p in understand.find_places(clause):
        found[i] = {"at": i, "end": j, "name": p["name"], "place": p, "airport": None}
    nc = " ".join(low)
    for k, (name, a) in _aliases().items():
        for m in re.finditer(rf"(?<!\w){re.escape(k)}(?!\w)", nc):
            i = nc[:m.start()].count(" ")
            if i in found or any(f["at"] <= i < f["end"] for f in found.values()):
                continue
            # "Natales" -> "Puerto Natales", "Perito Moreno" -> "Perito Moreno Glacier"
            full = max((x for x in a.names if norm(x).startswith(k) or norm(x).endswith(k)), key=len, default=name)
            found[i] = {"at": i, "end": i + len(k.split()), "name": full, "place": _place_of_area(a), "airport": None,
                        "area": a}
    for k, (city, ap) in AIRPORTS.items():
        for m in re.finditer(rf"(?<!\w){re.escape(k)}(?!\w)", nc):
            i = nc[:m.start()].count(" ")
            hit = next((f for f in found.values() if f["at"] <= i < f["end"]), None)
            if hit:
                hit.update(name=city, airport=ap)
                hit["place"] = _city(city) or hit["place"]
            else:
                found[i] = {"at": i, "end": i + len(k.split()), "name": city, "place": _city(city), "airport": ap}
    out = sorted(found.values(), key=lambda f: f["at"])
    for f in out:
        prev = " ".join(low[max(0, f["at"] - 2):f["at"]])
        f["origin"] = bool(re.search(r"\b(?:da|dal|dall|dalla|from|desde|de)$", prev))
    # "Buenos Aires (Ezeiza)": the airport in brackets belongs to the city before it
    merged: list[dict] = []
    for f in out:
        if merged and f["airport"] and merged[-1]["name"] == f["name"] and f["at"] - merged[-1]["end"] <= 1:
            merged[-1]["airport"] = f["airport"]
            continue
        merged.append(f)
    return merged


@lru_cache(maxsize=64)
def _city(name: str) -> dict | None:
    hits = understand.find_places(name)
    return hits[0][2] if hits else None


def _times(clause: str) -> list[str]:
    return [f"{int(h):02d}:{m}" for h, m in TIME.findall(clause)]


def _part(clause: str) -> str | None:
    low = clause.lower()
    for k in sorted(PART, key=len, reverse=True):
        if k in low:
            return PART[k]
    return None


def _clauses(sentence: str) -> list[str]:
    """A sentence cut where a new thing happens: commas, semicolons, "e si", "and then"."""
    parts = re.split(r"[,;]\s*|\s+(?=(?:e|ed|and|y)\s+(?:si|ci|poi|then|we|se)\b)|\s+(?=dove\s)", sentence)
    return [p.strip() for p in parts if p and p.strip()]


def _sentences(text: str) -> list[str]:
    out = []
    for para in re.split(r"\n+", text):
        out += [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9])", para) if s.strip()]
    return out


class _Dates:
    """The date being told about: "sabato 16 gennaio", then "domenica 17", "Venerdì 22"."""

    def __init__(self, today: date):
        self.today, self.month, self.year, self.cur = today, None, None, None

    def make(self, day: int, month: int | None, weekday: int | None = None) -> date | None:
        month = month or self.month or (self.cur.month if self.cur else None)
        if not month:
            return None
        if self.year is None:
            years = [self.today.year + k for k in range(0, 3)]
            ok = []
            for y in years:
                try:
                    d = date(y, month, day)
                except ValueError:
                    continue
                if d >= self.today:
                    ok.append(d)
            if not ok:
                return None
            pick = next((d for d in ok if weekday is not None and d.weekday() == weekday), ok[0])
            self.year = pick.year
            self.month = month
            return pick
        y = self.year
        if self.cur and month < self.cur.month - 6:  # December, then January
            y += 1
        try:
            d = date(y, month, day)
        except ValueError:
            return None
        self.month = month
        return d

    def find(self, clause: str) -> date | None:
        low = clause.lower()
        m = re.search(rf"\b({_WD})\s+(\d{{1,2}})(?:\s+(?:di\s+|de\s+)?({_MO}))?\b", low) or \
            re.search(rf"\b(\d{{1,2}})\s+(?:di\s+|de\s+)?({_MO})\b", low)
        if not m:
            return None
        g = m.groups()
        if len(g) == 3:
            wd, day, mo = WEEKDAY_OF.get(g[0]), int(g[1]), understand.MONTH_OF.get(g[2]) if g[2] else None
        else:
            wd, day, mo = None, int(g[0]), understand.MONTH_OF.get(g[1])
        if mo is None and self.cur and day < self.cur.day - 10:  # "domenica 2" after the 30th
            mo = self.cur.month % 12 + 1
        d = self.make(day, mo, wd)
        if d:
            self.cur = d
        return d


def _stop_dict(name: str, p: dict, days: int, start: date) -> dict:
    pid = p.get("id")
    return {"key": f"b-{pid or norm(name)}-{start.isoformat()}", "place_id": pid, "name": p["name"],
            "country": p.get("country"), "lat": p["lat"], "lon": p["lon"], "kind": p.get("kind") or "town",
            "days": days, "start_date": start.isoformat(), "fixed_dates": True,
            "elevation_m": p.get("elevation_m"), "activities": None, "sights": []}


def _lodging(sentence: str, dates: _Dates) -> dict | None:
    if not SLEEP.search(sentence):
        return None
    places = [f for f in _places(sentence) if f["place"]]
    if not places:
        return None
    nights = None
    m = NIGHTS_RE.search(sentence)
    if m:
        w = m.group(1).lower()
        nights = int(w) if w.isdigit() else understand.NUM.get(w)
    check_in = check_out = None
    r = RANGE.search(sentence)
    if r:
        d1, m1, d2, m2 = r.groups()
        m2n = understand.MONTH_OF.get(m2.lower()) if m2 else None
        m1n = understand.MONTH_OF.get(m1.lower()) if m1 else m2n
        check_in = dates.make(int(d1), m1n)
        check_out = dates.make(int(d2), m2n or m1n)
    else:
        r = DASH_RANGE.search(sentence)
        if r:
            mo = understand.MONTH_OF.get(r.group(3).lower())
            check_in, check_out = dates.make(int(r.group(1)), mo), dates.make(int(r.group(2)), mo)
        else:
            check_in = dates.find(sentence) or dates.cur
    if check_in and check_out and check_out < check_in:
        check_out = check_out.replace(year=check_out.year + 1)
    if check_in and check_out:
        nights_dates = (check_out - check_in).days
        nights = nights or nights_dates
    if not nights or not check_in:
        return None
    check_out = check_out or check_in + timedelta(days=nights)
    dates.cur = check_out
    lodging = address = None
    rest = sentence
    for lm in LODGING.finditer(rest):
        cand = lm.group(1).strip()
        if norm(cand) in {norm(f["name"]) for f in places} or re.fullmatch(r"\d+", cand):
            lm = None
            continue
        lodging = cand
        break
    am = ADDRESS.search(rest)
    if am:
        address = am.group(1).strip()
        if lodging and address in lodging:
            lodging = lodging.replace(address, "").strip(" ,")
    base = places[0]
    return {"name": base["place"]["name"], "place": base["place"], "nights": nights,
            "check_in": check_in, "check_out": check_out, "lodging": lodging, "address": address,
            "day_trips": [], "nights_written": (check_out - check_in).days == nights}


def read(text: str, today: date | None = None) -> dict | None:
    """The trip a detailed text tells, or None when it says nowhere to sleep."""
    today = today or date.today()
    sentences = _sentences(text)
    dates = _Dates(today)
    bases: list[dict] = []
    legs: list[dict] = []
    cur: dict | None = None
    where: dict | None = None  # {name, place, airport}
    car = False
    car_name = None
    home = None

    def new_leg(mode: str | None) -> dict:
        nonlocal cur
        leg = {"date": dates.cur, "mode": mode, "from": where["name"] if where else None,
               "from_airport": where.get("airport") if where else None, "to": None, "to_airport": None,
               "dep": None, "arr": None, "arr_date": None, "arr_part": None, "via": [], "stops": [], "notes": []}
        legs.append(leg)
        cur = leg
        return leg

    for sent in sentences:
        b = _lodging(sent, dates)
        if b:
            bases.append(b)
            where = {"name": b["name"], "place": b["place"], "airport": None}
            cur = None
            continue
        pending: list[str] = []
        for c in _clauses(sent):
            d = dates.find(c)
            times = _times(c)
            places = _places(c)
            dest = [f for f in places if not f["origin"]]
            orig = [f for f in places if f["origin"]]
            low = c.lower()
            if DAYTRIPS.search(c) and not times:
                if bases:
                    bases[-1]["day_trips"] += [f["name"] for f in places if f["name"] != bases[-1]["name"]]
                continue
            bm = BORDER.search(c)
            if bm:
                if cur is not None:
                    name = re.sub(r"^(?:la|il|the|el)\s+", "", bm.group(1).strip(" .")) or None
                    cur["notes"].append(f"Border: {name}" if name else "Border crossing")
                continue
            if RETURN.search(c) and CAR.search(c):
                if cur is not None:
                    by = re.search(r"\b(?:entro|by|before|antes de|prima delle)\b", low)
                    t = times[0] if times else None
                    cur["notes"].append(f"Car back {'by ' if by else 'at '}{t}" if t else "Car back")
                    if dest and not cur["to"]:
                        cur["to"], cur["to_airport"] = dest[-1]["name"], dest[-1]["airport"]
                car = False
                continue
            if PICKUP.search(c) and CAR.search(c):
                nm = re.search(r"\b(?:auto|car|macchina|coche)\s+([A-Z][\w-]+)", c)
                car_name = nm.group(1) if nm else None
                car = True
                leg = new_leg("car")
                leg["dep"] = times[0] if times else (pending[0] if pending else None)
                leg["notes"].append(f"Pick up the car{' (' + car_name + ')' if car_name else ''}")
                pending = []
                continue
            if STOPBY.search(c):
                if cur is not None:
                    for f in places:
                        cur["stops"].append({"name": f["name"], "when": _part(c)})
                continue
            if VIA.search(c) and not ARRIVE.search(c):
                if cur is not None:
                    cur["via"] += [f["name"] for f in places if f["name"] not in cur["via"]]
                    if FLIGHT.search(c) and not cur["mode"]:
                        cur["mode"] = "flight"
                continue
            hm = HOURS.search(c)
            if hm and not times and cur is not None and re.search(r"\b(?:viaggio|guida|drive|driving|travel|circa|about|dopo|after)\b", low):
                cur["notes"].append(f"≈ {hm.group(1).replace(' ', '')} h on the road")
                continue
            tm = TRANSFER.search(c)
            is_flight = bool(FLIGHT.search(c)) and not re.search(r"\batterr\w*|\blands?\b", low)
            if is_flight and (dest or re.search(r"\bvolo delle\b|\bflight at\b", low)):
                flight_t = re.search(r"\b(?:volo delle|volo alle|flight at|vuelo de las)\s+(\d{1,2}[:.]\d{2})", low)
                if cur is None or cur["to"] or (cur["mode"] not in (None, "flight")):
                    leg = new_leg("flight")
                else:
                    leg = cur
                    leg["mode"] = "flight"
                if orig and not leg["from"]:
                    leg["from"], leg["from_airport"] = orig[0]["name"], orig[0]["airport"]
                if dest:
                    leg["to"], leg["to_airport"] = dest[-1]["name"], dest[-1]["airport"]
                if flight_t:
                    leg["dep"] = _times(flight_t.group(1))[0]
                    other = [t for t in times if t != leg["dep"]]
                    if other:
                        leg["notes"].append(f"Leave at {other[0]}")
                elif times and not ARRIVE.search(c):
                    leg["dep"] = leg["dep"] or times[0]
                elif pending:
                    leg["dep"] = leg["dep"] or pending[0]
                pending = []
                if ARRIVE.search(c) and times:
                    leg["arr"] = times[-1]
                continue
            if tm and not ARRIVE.search(c.replace(tm.group(0), "")) or (tm and re.search(r"\bspost\w*|\bmove\w*|\btransfer\w*|\bva\b|\bandiamo\b", low)):
                kinds = []
                for x in TRANSFER.findall(c):
                    k = TRANSFER_NAME.get(x.lower(), x.lower())
                    if k not in kinds:
                        kinds.append(k)
                leg = new_leg(" or ".join(kinds) if kinds else "transfer")
                leg["dep"] = times[0] if times else None
                if dest:
                    leg["to"], leg["to_airport"] = dest[-1]["name"], dest[-1]["airport"]
                    where = {"name": dest[-1]["name"], "place": dest[-1]["place"], "airport": dest[-1]["airport"]}
                continue
            if DEPART.search(c) and not ARRIVE.search(c):
                if cur is None or cur["to"]:
                    leg = new_leg("car" if car else None)
                else:
                    leg = cur
                if orig:
                    leg["from"], leg["from_airport"] = orig[0]["name"], orig[0]["airport"]
                    if not legs[:-1] and home is None:
                        home = orig[0]
                if leg["from"] is None and where:
                    leg["from"] = where["name"]
                if times:
                    leg["dep"] = times[0]
                elif pending:
                    leg["dep"] = pending[0]
                pending = []
                if dest and not re.search(r"\bverso\b|\btowards?\b|\bhacia\b", low):
                    leg["to"], leg["to_airport"] = dest[-1]["name"], dest[-1]["airport"]
                continue
            if ARRIVE.search(c) or re.search(r"\b(?:fino a|fino al|fino all|until|hasta)\b", low):
                if cur is None:
                    new_leg("car" if car else None)
                if dest:
                    if cur["to"] and cur["to"] == dest[-1]["name"] or (cur["to"] and dest[-1]["airport"]
                                                                        and dest[-1]["name"] == cur["to"]):
                        cur["to_airport"] = dest[-1]["airport"] or cur["to_airport"]
                    elif not cur["to"] or not ARRIVE.search(c):
                        cur["to"], cur["to_airport"] = dest[-1]["name"], dest[-1]["airport"]
                    else:
                        cur["to"], cur["to_airport"] = dest[-1]["name"], dest[-1]["airport"]
                if ARRIVE.search(c):
                    if times:
                        cur["arr"] = times[-1]
                    else:
                        cur["arr_part"] = _part(c)
                    if d and cur["date"] and d != cur["date"]:
                        cur["arr_date"] = d
                if cur["to"]:
                    p = next((f for f in places if f["name"] == cur["to"]), None)
                    where = {"name": cur["to"], "place": p["place"] if p else _city(cur["to"]), "airport": cur["to_airport"]}
                continue
            if CAR.search(c) and cur is not None and not cur["mode"]:
                cur["mode"] = "car"
                continue
            if times and not places:
                pending += times
        if cur is not None and cur["to"]:
            p = _city(cur["to"])
            where = {"name": cur["to"], "place": p, "airport": cur["to_airport"]}

    # the short way of saying it ("Rome 3 nights, Florence 2") is the short reader's: this one
    # needs a bed by name or address, or a move with its time
    if not bases or not (any(b["lodging"] or b["address"] for b in bases)
                         or any(lg["dep"] or lg["arr"] for lg in legs)):
        return None
    for lg in legs:
        if lg["arr"] and lg["dep"] and not lg["arr_date"] and lg["arr"] < lg["dep"] and lg["mode"] == "flight":
            lg["arr_date"] = lg["date"] + timedelta(days=1) if lg["date"] else None
        if lg["mode"] is None:
            lg["mode"] = "car" if any(n.startswith("Border") for n in lg["notes"]) else "transfer"
    return _shape(text, bases, legs, home)


def _shape(text: str, bases: list[dict], legs: list[dict], home: dict | None) -> dict:
    first = min([b["check_in"] for b in bases] + [lg["date"] for lg in legs if lg["date"]])
    last = max([b["check_out"] for b in bases] + [lg["arr_date"] or lg["date"] for lg in legs if lg["date"]])
    stops: list[dict] = []
    for b in bases:
        s = _stop_dict(b["name"], b["place"], b["nights"], b["check_in"])
        s.update(lodging=b["lodging"], address=b["address"], day_trips=b["day_trips"], nights=b["nights"])
        arriving = [lg for lg in legs if lg["to"] and norm(lg["to"]) == norm(b["name"])
                    and (lg["arr_date"] or lg["date"]) == b["check_in"]]
        coming = [lg for lg in legs if (lg["arr_date"] or lg["date"]) == b["check_in"]]
        if arriving and arriving[-1]["arr"]:
            s["arrive_at"] = arriving[-1]["arr"]
        elif coming and coming[-1]["arr"] and coming[-1]["to"] and norm(coming[-1]["to"]) == norm(b["name"]):
            s["arrive_at"] = coming[-1]["arr"]
        s["way"] = [x["name"] for lg in coming for x in lg["stops"]]
        stops.append(s)
    # a day in a city between two flights, long enough to go out: a stop of its own
    covered = {b["check_in"] + timedelta(days=k) for b in bases for k in range(b["nights"])}
    d = first
    while d <= last:
        if d not in covered and d not in (first, last):
            todays = [lg for lg in legs if lg["date"] == d]
            ins = [lg for lg in todays if lg["arr"] and lg["to"] and (lg["arr_date"] in (None, d))]
            for lg in ins:
                nxt = [o for o in todays if o["from"] == lg["to"] and o["dep"] and o["dep"] > lg["arr"]
                       and o["mode"] == "flight"]
                if nxt and _minutes(nxt[-1]["dep"]) - _minutes(lg["arr"]) >= 5 * 60:
                    p = _city(lg["to"])
                    if p:
                        s = _stop_dict(lg["to"], p, 1, d)
                        s.update(kind="transit", transit=f"{lg['arr']}–{nxt[-1]['dep']}", arrive_at=lg["arr"], way=[])
                        stops.append(s)
                    break
        d += timedelta(days=1)
    stops.sort(key=lambda s: s["start_date"])
    month = first.month
    explore._guide_days(stops, month)
    days = []
    d = first
    n = 1
    while d <= last:
        si = next((i for i, s in enumerate(stops) if date.fromisoformat(s["start_date"]) <= d
                   < date.fromisoformat(s["start_date"]) + timedelta(days=s["days"])), None)
        night = next((b for b in bases if b["check_in"] <= d < b["check_out"]), None)
        todays = [_leg_out(lg) for lg in legs if lg["date"] == d]
        air = any(lg["mode"] == "flight" and lg["arr_date"] and lg["arr_date"] > d for lg in legs if lg["date"] == d)
        days.append({"n": n, "date": d.isoformat(), "stop": si,
                     "stop_day": (d - date.fromisoformat(stops[si]["start_date"])).days + 1 if si is not None else None,
                     "legs": todays,
                     "sleep": ({"name": night["lodging"], "address": night["address"], "town": night["name"]}
                               if night else ({"in_the_air": True} if air else None))})
        d += timedelta(days=1)
        n += 1
    hp = home["place"] if home and home.get("place") else None
    return {"text": text[:2000], "mode": "booked", "area": None, "only": [], "month": month,
            "start_date": first.isoformat(), "end_date": last.isoformat(), "days": (last - first).days + 1,
            "stops": stops, "legs": [_leg_out(lg) for lg in legs], "timeline": days,
            "home": ({"name": hp["name"], "country": hp["country"], "lat": hp["lat"], "lon": hp["lon"]} if hp else None),
            "wishes": [], "missing": [], "nights": sum(b["nights"] for b in bases)}


def _minutes(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _leg_out(lg: dict) -> dict:
    return {**lg, "date": lg["date"].isoformat() if lg["date"] else None,
            "arr_date": lg["arr_date"].isoformat() if lg["arr_date"] else None}
