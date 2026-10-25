"""Free text -> draft itinerary. LLM first, rule-based parser as fallback.

The result is always a DRAFT the user confirms in the UI; nothing is saved here.

Two kinds of input:
- short prose ("3 days in Rome, then 4 days hiking in Chamonix"): the model reads it,
  the rule parser is the fallback;
- a day-by-day program pasted from a travel agency ("Giorno 1 ... Giorno 15"). The day
  sections are cut out deterministically: repeated agency text and packing advice are
  removed, the trip days before leaving and after coming home are dropped, and every
  stop's dates come from its day numbers. The model only names the stops and their
  activities, and each activity is checked against the text of that stop's own days.
"""
from __future__ import annotations

import datetime as _dt
import difflib
import html
import logging
import math
import re
import unicodedata
from datetime import date, timedelta
from typing import NamedTuple

from pydantic import BaseModel, Field, ValidationError, field_validator

from app import art
from app.engine.activities import ACTIVITY_TYPES, DIFFICULTIES
from app.llm.client import LLMClient, LLMUnavailable
from app.services.dates import lay_out, spread

log = logging.getLogger(__name__)


class DraftActivity(BaseModel):
    type: str = "city"
    difficulty: str | None = None
    max_altitude_m: float | None = None
    glacier: bool = False

    @field_validator("type")
    @classmethod
    def _t(cls, v):
        v = (v or "city").lower().strip()
        aliases = {"trekking": "hiking", "hike": "hiking", "trek": "hiking", "sightseeing": "city",
                   "skiing": "ski", "snowboard": "ski", "bike": "cycling", "multi-day trek":
                   "trek_multiday", "multiday trek": "trek_multiday", "dont_know": "unknown",
                   "don't know": "unknown", "not sure": "unknown", "kayak": "boat",
                   "rafting": "boat", "dunes": "desert", "sandboarding": "desert"}
        v = aliases.get(v, v)
        return v if v in ACTIVITY_TYPES else "city"

    @field_validator("difficulty")
    @classmethod
    def _d(cls, v):
        if v is None:
            return None
        v = v.lower().strip()
        v = {"difficult": "hard", "medium": "moderate", "alpine": "technical"}.get(v, v)
        return v if v in DIFFICULTIES else None


class DraftVisit(BaseModel):
    """A place seen during a stop besides where you sleep: Moray on a Cusco day."""
    name: str
    date: _dt.date | None = None


class DraftStop(BaseModel):
    name: str
    start_date: date
    end_date: date
    activities: list[DraftActivity] = Field(default_factory=list)
    notes: str | None = None
    elevation_m: float | None = None  # where the traveller sleeps, when the text says it
    visits: list[DraftVisit] = Field(default_factory=list)
    days_estimated: bool = False  # the text does not say how long: the days are a guess

    @field_validator("visits", mode="before")
    @classmethod
    def _v(cls, v):  # the model gives plain names
        return [{"name": x} if isinstance(x, str) else x for x in (v or []) if x]


class DraftEstimate(BaseModel):
    """What of the dates is a guess. The app asks for it and marks the plan as an estimate."""
    start: bool = False        # no start date in the text
    days: bool = False         # places without how long: the days are spread evenly
    total_days: int | None = None  # the trip length, when the text gives it ("2 settimane")
    questions: list[str] = Field(default_factory=list)  # the questions this covers


class DraftItinerary(BaseModel):
    trip_name: str | None = None
    stops: list[DraftStop]
    questions: list[str] = Field(default_factory=list)
    parser: str = "rules"
    estimate: DraftEstimate | None = None


SYSTEM = """You turn a traveller's description of a trip into JSON. Output ONLY a JSON object:
{"trip_name": str, "stops": [{"name": str, "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD",
"activities": [{"type": one of ["city","hiking","trek_multiday","beach","ski","cycling","safari","boat","desert","unknown"],
"difficulty": one of ["easy","moderate","hard","technical","unknown"] or null,
"max_altitude_m": number or null, "glacier": true or false}], "notes": str or null,
"visits": [str]}]}
Rules:
- "name" is a real place name that a map search can find (a town, park or region).
- Consecutive stops: the next stop starts the day after the previous one ends, unless dates are given.
- If no start date is given, start 30 days after TODAY.
- If the traveller does not know what they will do, use type "unknown". If a hike's difficulty is unclear, use "unknown".
- "trek_multiday" only when the text says the walk lasts several days with nights in huts or tents. A day hike is "hiking".
- "boat" is for boat trips, navigation, kayak and rafting. "safari" only for wildlife game drives.
  "desert" for dunes, sandboarding and desert outings.
- A travel or transfer day, or a free/reserve day, adds no activity beyond "city".
- Difficulty: a hike of 7 hours or more, or above 4,500 m, is "hard". "glacier": true only for walking on ice with crampons.
- max_altitude_m: only a number the text gives, or the well-known highest point of a famous
  named trek (Laugavegur 1100, Tour du Mont Blanc 2665, W Trek 900, Inca Trail 4215). Otherwise null. Never guess.
- "notes": at most 15 words about what happens at that stop that matters for clothes, else null.
  Never copy general advice ("layered clothing, waterproof boots, sun cream") into notes.
- "visits": the other named places seen during the stop's days besides where the traveller
  sleeps (sites, villages, islands, viewpoints), in order, as the text names them. [] if none.
- Write trip_name and notes in the language of the trip description.
- Never invent dates the traveller gave differently. Never add stops they did not mention.
- Day-by-day programs ("Day 1", "Giorno 2", ...): make ONE stop per place, not per day: merge
  consecutive days spent in or around the same place. Days marked (travel) are not stops.
  Ignore flights, transfers, hotels, meals and prices. At most 40 stops."""

MAX_STOPS = 40
_DAY_LABEL = r"(?:day|giorno|gg|día|dia|jour|tag)"


# ---------------------------------------------------------------- text helpers

def normalize_text(text: str) -> str:
    """Shrink a pasted itinerary without losing meaning: decode HTML entities, trim spaces,
    drop empty lines and re-join 'Giorno\\n2\\nLima' headings that web pages split up."""
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    out: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if re.fullmatch(_DAY_LABEL, ln, re.I) and i + 1 < len(lines) and re.fullmatch(r"\d{1,3}", lines[i + 1]):
            ln = f"{ln} {lines[i + 1]}"
            i += 1
            if i + 1 < len(lines) and len(lines[i + 1]) <= 60:
                ln = f"{ln}: {lines[i + 1]}"
                i += 1
        out.append(ln)
        i += 1
    return "\n".join(out)


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def _sentences(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?<=[.!?;])\s+|\n", text or "") if p.strip()]


# ---------------------------------------------------------------- language

_LANG_WORDS = {
    "Italian": {"il", "la", "di", "e", "del", "della", "giorno", "giorni", "con", "per", "alla",
                "nel", "una", "che", "pernottamento", "partenza", "arrivo", "visita", "poi", "dopo"},
    "English": {"the", "and", "of", "day", "days", "with", "for", "then", "to", "overnight",
                "arrival", "visit", "after", "we", "will"},
    "Spanish": {"el", "los", "las", "y", "del", "día", "dia", "con", "para", "llegada", "noche",
                "después", "visita"},
    "French": {"le", "les", "et", "du", "des", "jour", "avec", "pour", "arrivée", "nuit", "puis"},
    "German": {"der", "die", "und", "das", "tag", "mit", "für", "nach", "ankunft", "dann"},
}


def detect_language(text: str) -> str:
    words = re.findall(r"[a-zà-ÿ]+", text[:20000].lower())
    scores = {lang: sum(w in vocab for w in words) for lang, vocab in _LANG_WORDS.items()}
    best = max(scores, key=scores.get)
    others = max(v for k, v in scores.items() if k != best)
    return best if scores[best] >= 2 and scores[best] > others else "English"


Q = {
    "English": {"dates": "When do you leave? Dates were not clear, so the draft starts in 30 days.",
                "days": "How many days in {place}? The draft assumes 2.",
                "length": "How long is the whole trip? The draft gives each place {n} days.",
                "high": "How high does the hike near {place} go?"},
    "Italian": {"dates": "Quando parti? Le date non erano chiare, quindi la bozza parte tra 30 giorni.",
                "days": "Quanti giorni a {place}? La bozza ne conta 2.",
                "length": "Quanto dura il viaggio? La bozza dà {n} giorni a ogni posto.",
                "high": "Fino a che quota arriva l'escursione vicino a {place}?"},
}


def _q(lang: str, key: str, **kw) -> str:
    return Q.get(lang, Q["English"])[key].format(**kw)


# ---------------------------------------------------------------- patterns

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september",
     "october", "november", "december"], start=1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS.update({"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
               "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11,
               "dicembre": 12})
SPLIT = re.compile(r"\n|;|\bthen\b|\bpoi\b|\bafter that\b|\bquindi\b|,\s*(?=\d)|->|→", re.I)
DUR = re.compile(r"(\d{1,2})\s*(days?|nights?|giorni|notti|gg|d)\b", re.I)
WEEK = re.compile(r"(\d|a|one|una)\s*(weeks?|settimana|settimane)\b", re.I)
_NUM = r"(\d{1,2}[.,’' ]\d{3}|\d{3,4})"
ALT = re.compile(_NUM + r"\s?(?:m|mt|mslm|msnm|m\.s\.l\.m|meters|metres|metri|metros)\b\.?", re.I)
QUOTA = re.compile(r"\b(?:quota|altitudine|altitude|altitud|elevation)\s*(?:di\s+|of\s+|:\s*)?" + _NUM + r"\b", re.I)
RANGE = re.compile(r"\b(\d{1,2})\s*(?:-|–|al|to|until|fino al|au|bis)\s*\d{1,2}\s+([a-zA-Z]{3,9})(?:\s+(\d{4}))?\b", re.I)
ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
DMY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-zA-Z]{3,9})(?:\s+(\d{4}))?\b")
MDY = re.compile(r"\b([a-zA-Z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b")
DAY_HEAD = re.compile(rf"^{_DAY_LABEL}\s*(\d{{1,3}})\b[\s:.\-–]*(.*)$", re.I | re.M)
STOPWORDS = {"days", "day", "nights", "night", "in", "at", "a", "to", "the", "and", "then",
             "trekking", "hiking", "hike", "trek", "city", "beach", "ski", "skiing", "easy",
             "moderate", "hard", "technical", "difficult", "giorni", "notti", "di", "e", "nel",
             "nella", "al", "alla", "on", "for", "per", "from", "dal", "with", "con", "some",
             "maybe", "forse", "not", "sure", "know", "don't", "dont", "yet", "around", "visit",
             "visiting", "sightseeing", "tour", "week", "weeks", "settimana", "of", "my", "we",
             "i", "will", "be", "go", "going", "stay", "staying", "fino", "until", "then,",
             "multi-day", "multiday", "cycling", "bike", "safari", "mare", "spiaggia", "neve",
             "escursione", "escursioni", "camminata", "montagna", "mountains", "mountain"}

# general sections of an agency program that follow (or interrupt) the days
SECTION = re.compile(r"^\s*-{3,}\s*$"
                     r"|^\s*(?:la\s+)?(?:quota|prezzo|price|tariff|the price|il prezzo|cost)\w*\s+(?:non\s+)?(?:comprend|includ|inclu)"
                     r"|^\s*(?:non\s+)?(?:compres|inclus|included|not included|what'?s included|incluye|no incluye)\w*\s*:"
                     r"|^\s*(?:nota bene|n\.?b\.?|note|notes|informazioni|info utili|cosa portare|abbigliamento"
                     r"|equipaggiamento|attrezzatura|documenti|assicurazion|condizioni|termini|packing"
                     r"|what to bring|clothing|equipment|gear|qu[eé] llevar|ropa|equipo|documentos|seguro)"
                     r"\b[^\n]{0,40}(?::|$)", re.I | re.M)
ADVICE = re.compile(r"abbigliament|scarpon|scarpe|zaino|bastoncin|giacca|giacche|guanti|berrett|cappell|"
                    r"crema solare|protezione solare|occhiali|a strati|a cipolla|si consiglia|consigliat|"
                    r"raccomand|portare con|equipaggiament|attrezzatur|clothing|clothes|boots|backpack|"
                    r"layers|sunscreen|sun cream|recommend|bring |ropa|botas|mochila|recomend", re.I)
HIKE = re.compile(r"trek|hik|escursion|cammin|sentier|caminata|senderismo|randonn|wander", re.I)
# "potremo scegliere se esplorare i sentieri ... oppure relax alle terme": not a plan
OPTIONAL = re.compile(r"potremo scegliere|potrete scegliere|a scelta|facoltativ|opzional|optional|"
                      r"chi (?:lo )?desidera|chi vuole|if you wish|possibilità di|se si desidera|"
                      r"\boppure\b|\bor relax", re.I)


def _firm(text: str) -> str:
    """The text without optional activities."""
    return "\n".join(s for s in _sentences(text) if not OPTIONAL.search(s))


STRONG_HIKE = re.compile(r"trek|hik|cammin|sentier|caminata|senderismo|randonn|wander", re.I)
MULTIDAY = re.compile(r"multi.?day|hut to hut|più giorni|piu giorni|rifugi|campeggio|in tenda|"
                      r"\btenda\b|campamento|refugio|camping|\bcamp\b|bivacco|\bw trek\b|circuito o\b", re.I)
GLACIER = re.compile(r"rampon|crampon|grampon|minitrek|mini.trek|big ice|ice.?trek|sul ghiaccio|on the ice|"
                     r"sobre el hielo|glacier walk|camminata sul ghiacciaio|trekking sul ghiacciaio", re.I)
HOURS = re.compile(r"(\d{1,2})(?:[.,]\d)?\s*(?:(?:-|–|/|a|to|e)\s*(\d{1,2})(?:[.,]\d)?\s*)?"
                   r"(?:ore|ora|h|hrs?|hours?|horas|heures|stunden)\b", re.I)
TRANSPORT = re.compile(r"\bvol[oi]\b|flight|\bbus\b|pullman|trasferiment|transfer|navig|"
                       r"\bauto\b|\bdrive\b|\btreno\b|train|viaggio", re.I)
BOAT = re.compile(r"rafting|kayak|canoa|canoe|navig|navegaci|\bbarca\b|battello|catamaran|"
                  r"gommone|\bboat\b|cruise|crociera|motonave|traghetto|ferry|lancha|zodiac|"
                  r"verso le isole|alle isole|isole galleggianti|to the islands|a las islas", re.I)
# "La nostra barca ci riporterà a Puno": a boat used to get somewhere is not an activity
BOAT_TRANSFER = re.compile(r"(?:barca|battello|traghetto|lancha|boat|ferry)\w*\s+(?:ci\s+)?(?:riport|port|trasport|takes|brings)"
                           r"|(?:rientro|ritorno|trasferimento|transfer|return)\w*\s+(?:in\s+|by\s+)(?:barca|battello|boat|traghetto|ferry)", re.I)
BOAT_EXCURSION = re.compile(r"(escursion\w*|excursi\w*|gita|tour)\s+(in|con|en|by)\s+"
                            r"(barca|battello|catamarano|gommone|kayak|motoscafo|nave|boat|lancha)", re.I)
SAFARI = re.compile(r"safari|game drive|fotosafari", re.I)
DESERT = re.compile(r"sandboard|dune buggy|\bdune\b|deserto|desert|desierto|\boasi\b|oasis", re.I)
BEACH = re.compile(r"beach|spiaggia|\bmare\b|snorkel|swim|nuoto|playa|plage", re.I)
SKI = re.compile(r"\bski|snowboard|sciare|\bsci\b|esqu[ií]", re.I)
BIKE = re.compile(r"cycling|\bbike|\bbici|bicicletta|mountain bike|bicicleta|\bvélo", re.I)
CITY = re.compile(r"city|città|citta|museum|museo|sightseeing|visit|centro storico|ciudad", re.I)
# facts about a stop that matter for clothes (kept in notes)
FACT = re.compile(r"vento|neve|pioggia|freddo|gelo|caldo|nebbia|quota\s*(?:di\s*)?\d|altitudin|ghiacci|"
                  r"rampon|ripid|homestay|deserto|dune|sandboard|rafting|\bwind|\bsnow|\brain\b|\bcold\b|\bheat\b|"
                  r"\bice\b|steep|altitude|crampon|viento|nieve|lluvia|frío|frio|\d\s*metri|\d\s*m\b|"
                  r"\bore\b|\bhours?\b", re.I)
NOT_FACT = re.compile(r"comprend|includ|inclus|prezz|price|€|euro|assicurazion|insurance|supplement", re.I)
HOME = {"italia", "italy", "home", "casa"}
FLIGHTISH = re.compile(r"\bvol[oi]\b|aeroport|flight|airport|vuelo|aereo|scal[oi]\b|rientro|ritorno|"
                       r"\barrivo\b|return", re.I)
OVERNIGHT = re.compile(r"pernottament\w*\b(?!\s+a\s+bordo)(?!\s+in\s+volo)|\bhotel\b|overnight in|night in", re.I)
KNOWN_TREKS = {"laugavegur": 1100, "tour du mont blanc": 2665, "w trek": 900, "circuito w": 900,
               "inca trail": 4215, "cammino inca": 4215, "camino inca": 4215, "salkantay": 4630,
               "kilimanjaro": 5895, "everest base camp": 5364, "annapurna circuit": 5416,
               "vinicunca": 5200, "rainbow mountain": 5200}
_DIFF_RANK = {"easy": 1, "moderate": 2, "hard": 3, "technical": 4}


# ---------------------------------------------------------------- day-by-day programs

class Day(NamedTuple):
    n: int          # the number the program gives ("Giorno 7" -> 7)
    title: str      # short heading, usually the place
    body: str       # the day's own text, without repeated agency text and packing advice
    travel: bool    # leaving home or flying back: not a stop
    subtitle: str = ""            # "Dune buggy e sandboarding": a tagline, not a sentence
    sleep: str | None = None      # "Pernottamento a Puno" -> "Puno"
    sleep_alt: float | None = None  # "... / Quota 3827 mt" -> 3827


_PLACE = r"((?-i:[A-ZÀ-Ý][\w'’-]+)(?:\s+(?:de|del|di|da|la|las|los|el|y)?\s*(?-i:[A-ZÀ-Ý][\w'’-]+)){0,3})"
SLEEP = [
    re.compile(r"pernottament\w*\s+(?:a|ad|in|presso|al|all['’])\s*" + _PLACE, re.I),
    re.compile(r"(?:passeremo|trascorreremo|dormiremo)\s+la\s+(?:nostra\s+)?(?:prima\s+|ultima\s+)?notte\s+(?:a|ad|in)\s+" + _PLACE, re.I),
    re.compile(r"\b(?:a|ad|verso|in)\s+" + _PLACE + r"\s*(?:\([^)]*\))?,?\s*dove\s+(?:passeremo|trascorreremo|dormiremo)\s+la\s+(?:nostra\s+)?(?:prima\s+|ultima\s+)?notte", re.I),
    re.compile(r"\b(?:overnight|night|stay)\s+(?:in|at)\s+" + _PLACE, re.I),
    re.compile(r"\b(?:noche|alojamiento)\s+en\s+" + _PLACE, re.I),
]


def overnight(body: str) -> tuple[str | None, float | None]:
    """Where the traveller sleeps that day and, if the line says it, at what altitude."""
    best = None
    for line in _sentences(body):  # the last mention wins: "Pernottamento a ..." closes the day
        for rx in SLEEP:
            for m in rx.finditer(line):
                best = (line, m[1])
    if best is None:
        return None, None
    line, place = best
    alts = _numbers_m(line)
    return place.strip(" .,"), (max(alts) if alts else None)


def _home_words(first: str) -> set[str]:
    home = set(HOME)
    m = re.search(r"(?:partenza|partiamo|partiremo|departure|departing|salida)\s+(?:dall['’]\s*|da\s+|dal\s+|from\s+|desde\s+)([A-ZÀ-Ý][\w]+)", first)
    if m:
        home.add(_fold(m[1]))
    return home


def _is_home_travel(title: str, body: str, home: set[str]) -> bool:
    words = set(_fold(f"{title} {body}").split())
    first_part = _fold(re.split(r"\s+-\s+|\s*[–—/>→]\s*", title)[0])
    return bool((words & home or first_part in home) and FLIGHTISH.search(f"{title} {body}")
                and not OVERNIGHT.search(body))


def day_blocks(text: str) -> list[Day]:
    """'Giorno 2: Lima ...' -> Day(2, 'Lima', '...'). Empty when the text is not day-by-day."""
    heads = list(DAY_HEAD.finditer(text))
    if len(heads) < 3:
        return []
    raw: list[list] = []
    for i, h in enumerate(heads):
        body = text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)].strip()
        title = h[2].strip()
        if not title:
            title, _, body = body.partition("\n")
        else:
            m = re.match(r"([^:]{2,60}?)\s*:\s+(.+)$", title)
            if m:  # "Giorno 1 - Buenos Aires: Arrivo all'aeroporto ..."
                title, body = m[1], m[2] + "\n" + body
            elif len(title) > 60:
                body = title + "\n" + body
                title = re.split(r"(?<=[.!?])\s", title)[0][:80]
        cut = SECTION.search(body)
        if cut:
            body = body[:cut.start()]
        sub = ""
        first, nl, rest = body.strip().partition("\n")
        if nl and len(first) <= 60 and not re.search(r"[.:;,]$", first):
            sub, body = first, rest  # web pages put a tagline under the heading
        raw.append([int(h[1]), title.strip(" -–"), _sentences(body), sub])
    # a sentence repeated on many days is agency boilerplate ("guida in italiano, assicurazione...")
    seen: dict[str, int] = {}
    for _, _, sents, _ in raw:
        for k in {_fold(s) for s in sents}:
            seen[k] = seen.get(k, 0) + 1
    limit = max(3, math.ceil(len(raw) / 3))
    days = [[n, title, "\n".join(s for s in sents if seen[_fold(s)] < limit and not ADVICE.search(s)), sub]
            for n, title, sents, sub in raw]
    home = _home_words(f"{days[0][1]} {days[0][2]}")
    travel = [False] * len(days)
    for order in (range(len(days)), range(len(days) - 1, -1, -1)):
        for k in order:  # only at the start and at the end of the program
            if not _is_home_travel(days[k][1], days[k][2], home):
                break
            travel[k] = True
    out = []
    for (n, t, b, sub), tr in zip(days, travel):
        sleep, alt = overnight(b)
        out.append(Day(n, t, b, tr, sub, sleep, alt))
    return out


def condense(days: list[Day], text: str, lang: str) -> str:
    """What the model reads for a day-by-day program: the header and each day's own text."""
    head = text[:DAY_HEAD.search(text).start()]
    cut = SECTION.search(head)
    head = " ".join(s for s in _sentences(head[:cut.start()] if cut else head) if not ADVICE.search(s))
    label = "Giorno" if lang == "Italian" else "Day"
    lines = [head[:600]] if head else []
    for d in days:
        sub = f" ({d.subtitle})" if d.subtitle else ""
        lines.append(f"{label} {d.n}: {d.title} (travel)" if d.travel
                     else f"{label} {d.n}: {d.title}{sub}. {d.body.replace(chr(10), ' ')}")
    return "\n".join(lines)


def _day_dates(days: list[Day], text: str, today: date) -> tuple[date, bool]:
    """Date of the first day of the program, and whether the text gave it."""
    start = _find_date(text, today)
    if start is not None:
        return start, True
    return today + timedelta(days=30), False  # day 1 is the (unknown) departure day


def _date_of(days: list[Day], start: date, n: int) -> date:
    return start + timedelta(days=n - days[0].n)


# ---------------------------------------------------------------- measures in the text

def _numbers_m(text: str) -> list[float]:
    nums = [m[1] for m in ALT.finditer(text)] + [m[1] for m in QUOTA.finditer(text)]
    return [float(re.sub(r"[.,’' ]", "", n)) for n in nums]


def _hike_numbers(text: str) -> list[float]:
    """Altitudes said in sentences about walking (not where the hotel is)."""
    return [n for s in _sentences(text) if HIKE.search(BOAT_EXCURSION.sub(" ", s))
            for n in _numbers_m(s)]


def _altitude_ok(alt: float, ev: str) -> bool:
    if any(abs(alt - n) <= max(30.0, 0.03 * n) for n in _numbers_m(ev)):
        return True
    low = ev.lower()
    return any(k in low and abs(alt - v) <= 0.05 * v for k, v in KNOWN_TREKS.items())


def _hike_hours(ev: str) -> float:
    """Longest walking time mentioned in sentences about walking (not flights or buses)."""
    best = 0.0
    for sent in _sentences(ev):
        if not HIKE.search(sent) or TRANSPORT.search(sent):
            continue
        for m in HOURS.finditer(sent):
            best = max(best, float(m[2] or m[1]))
    return best


_DIFF_WORDS = [(re.compile(rx, re.I), d) for rx, d in (
    (r"\btechnical\b|\balpinistic", "technical"),
    (r"\bimpegnativ\w*|\bdifficil[ei]\b|\bdifficult\b|\bhard\b|\bexigente\b|\bduro\b", "hard"),
    (r"\bmedia difficolt|\bmoderat\w*|\bmedium\b", "moderate"),
    # whole words only: "non facilitano la respirazione" is not an easy walk
    (r"\bfacil[ei]\b|\beasy\b|\bsemplic[ei]\b|\bfácil\b", "easy"))]


def _difficulty_word(ev: str) -> str | None:
    for rx, d in _DIFF_WORDS:
        if rx.search(ev):
            return d
    return None


def _difficulty_in(ev: str, altitude: float | None = None) -> str | None:
    """Hardest of what the words say, the walking time (7 h or more is hard) and the
    altitude (above 4,500 m every step is hard work)."""
    h = _hike_hours(ev)
    cands = [_difficulty_word(ev),
             "hard" if h >= 7 else "moderate" if h >= 4 else "easy" if h > 0 else None,
             "hard" if altitude and altitude >= 4500 else None]
    cands = [d for d in cands if d]
    return max(cands, key=lambda d: _DIFF_RANK[d]) if cands else None


def facts_note(ev: str | None, name: str = "") -> str | None:
    """The one or two sentences of a stop's days that matter for clothes. "Pernottamento a
    Cuzco (quota 3400)" on the Lima day is about the next stop, so it is left out there."""
    if not ev:
        return None
    toks = _name_tokens(name) if name else set()

    def about_here(s: str) -> bool:
        # the overnight altitude goes to the stop itself; keep the line only when the
        # kind of night matters ("in homestay", "in tenda") and it is about this place
        if not (re.search(r"pernott|overnight|notte", s, re.I) or any(rx.search(s) for rx in SLEEP)):
            return True
        if not re.search(r"homestay|tenda|tent|rifugio|refugio|hut|campo|camp", s, re.I):
            return False
        return not toks or _tok_match(toks, set(_fold(s).split()))
    sents = [_fact_part(s) for s in _sentences(ev) if FACT.search(s) and not ADVICE.search(s)
             and not NOT_FACT.search(s) and not (TRANSPORT.search(s) and not HIKE.search(s))
             and about_here(s)]
    out: list[str] = []
    for part in sorted(sents, key=lambda s: -len(FACT.findall(s))):
        if len(" ".join(out + [part])) <= 200:
            out.append(part)
        if len(out) == 2:
            break
    return clean_note(" ".join(p for p in sents if p in out), limit=200)


def _fact_part(sentence: str) -> str:
    """Of a long sentence keep only the clauses with the facts:
    'Oggi visiteremo la Rainbow Mountain: sfioreremo i 5200 metri e ..., ma ne varrà la pena!'
    -> 'Sfioreremo i 5200 metri e ...'."""
    if len(sentence) <= 120:
        return sentence
    parts = [p.strip() for p in re.split(r"[:;,]\s+|\s+[-–]\s+", sentence) if p.strip()]
    keep = [p for p in parts if FACT.search(p)] or parts[:1]
    text = ", ".join(keep).rstrip(".!?") + "."
    return text[0].upper() + text[1:]


def clean_note(note: str | None, limit: int = 160) -> str | None:
    """No packing advice, and cut on a sentence or word boundary, never mid-word."""
    note = " ".join(s for s in _sentences(note or "") if not ADVICE.search(s)).strip(" ,;")
    if len(note) > limit:
        cut = note[:limit]
        end = max(cut.rfind(". "), cut.rfind("; "))
        note = cut[:end + 1] if end >= 40 else cut[:cut.rfind(" ")].rstrip(" ,;:") + "…"
    return note or None


# ---------------------------------------------------------------- activities from text

def _activities(seg: str, allow_unknown: bool = True) -> list[DraftActivity]:
    if not allow_unknown:  # day-by-day programs: optional extras are not the plan
        seg = _firm(seg)
    s = seg.lower()
    acts: list[DraftActivity] = []
    hike_s = BOAT_EXCURSION.sub(" ", s)
    alts = _hike_numbers(seg)
    altitude = max(alts) if alts else None
    difficulty = _difficulty_in(hike_s, altitude)
    glacier = bool(GLACIER.search(hike_s))
    unknown = allow_unknown and any(w in s for w in ("don't know", "dont know", "not sure", "boh",
                                                     "non so", "maybe", "forse", "not decided"))
    if unknown:
        difficulty = "unknown"
    hike = _is_hike(s)
    if hike and MULTIDAY.search(s):
        acts.append(DraftActivity(type="trek_multiday", difficulty=difficulty,
                                  max_altitude_m=altitude, glacier=glacier))
    elif hike:
        acts.append(DraftActivity(type="hiking",
                                  difficulty=difficulty or ("unknown" if unknown else "moderate"),
                                  max_altitude_m=altitude, glacier=glacier))
    if SKI.search(s):
        acts.append(DraftActivity(type="ski", max_altitude_m=altitude))
    if BEACH.search(s) or "coast" in s:
        acts.append(DraftActivity(type="beach"))
    if BIKE.search(s):
        acts.append(DraftActivity(type="cycling"))
    if SAFARI.search(s):
        acts.append(DraftActivity(type="safari"))
    if any(BOAT.search(x) and not BOAT_TRANSFER.search(x) for x in _sentences(s)):
        acts.append(DraftActivity(type="boat"))
    if DESERT.search(s):
        acts.append(DraftActivity(type="desert"))
    if CITY.search(s):
        acts.append(DraftActivity(type="city"))
    if not acts:
        acts.append(DraftActivity(type="unknown" if unknown else "city"))
    return acts


class _BoatTrip:
    """A boat in the text that is a trip, not a ride to the next place."""
    @staticmethod
    def search(text: str):
        return any(BOAT.search(x) and not BOAT_TRANSFER.search(x) for x in _sentences(text))


_CHECKS = {"beach": BEACH, "ski": SKI, "cycling": BIKE, "safari": SAFARI, "boat": _BoatTrip,
           "desert": DESERT}


def _is_hike(text: str) -> bool:
    """Italian "escursione" is any outing: alone, next to dunes or a boat, it is not a hike."""
    t = BOAT_EXCURSION.sub(" ", text)
    if STRONG_HIKE.search(t):
        return True
    return bool(HIKE.search(t)) and not any(rx.search(t) for rx in _CHECKS.values())


def refine_activities(stops: list[DraftStop], evs: list[str | None], text: str) -> None:
    """Keep what the model says only when the text backs it: the model likes to tag every
    day as a hard 2,500 m trek. `evs` is the text of each stop's own days (None when the
    input is not day-by-day: then only the whole text can be checked)."""
    for s, ev in zip(stops, evs):
        if ev is not None:
            ev = _firm(ev)
        scope = ev if ev is not None else text
        hike_text = BOAT_EXCURSION.sub(" ", scope)
        kept: list[DraftActivity] = []
        for a in s.activities:
            if a.type in ("hiking", "trek_multiday"):
                if ev is not None and not _is_hike(scope):
                    continue
                if a.type == "trek_multiday" and not MULTIDAY.search(scope):
                    a.type = "hiking"
            elif a.type in _CHECKS and not _CHECKS[a.type].search(scope):
                if a.type == "safari" and _BoatTrip.search(scope):
                    a.type = "boat"
                elif ev is not None or a.type in ("safari", "boat"):
                    continue
            if a.type in ("hiking", "trek_multiday", "ski"):
                if a.max_altitude_m and not _altitude_ok(a.max_altitude_m, scope):
                    a.max_altitude_m = None  # invented: the plan asks for it instead
                stated = _hike_numbers(ev) if ev is not None else []
                if stated:  # the model may take the hotel's altitude for the hike's top
                    a.max_altitude_m = max(stated)
            else:
                a.max_altitude_m = None
            if a.type in ("hiking", "trek_multiday") and ev is not None:
                a.glacier = bool(GLACIER.search(hike_text))
                d = _difficulty_in(hike_text, a.max_altitude_m)
                if d:
                    a.difficulty = d
                elif a.difficulty in ("hard", "technical"):
                    a.difficulty = "moderate"  # the model's guess, not in the text
            if a.type not in ("hiking", "trek_multiday", "unknown"):
                a.difficulty = None
                a.glacier = False
            kept.append(a)
        if ev is not None:  # add what the days clearly say and the model missed
            have = {a.type for a in kept}
            walking = have & {"hiking", "trek_multiday"}
            for extra in _activities(ev, allow_unknown=False):
                if extra.type in ("hiking", "trek_multiday") and walking:
                    continue
                if extra.type not in ("city", "unknown") and extra.type not in have:
                    kept.append(extra)
        s.activities = _merge_activities(kept) or [DraftActivity(type="city")]


# ---------------------------------------------------------------- stops

def place_key(name: str) -> str:
    """'Ushuaia, Tierra del Fuego' and 'ushuaia' are the same stop."""
    return _fold(re.split(r"[,(]", name or "", maxsplit=1)[0])


_GENERIC = {"national", "park", "parque", "nacional", "parco", "nazionale", "glacier", "ghiacciaio",
            "glaciar", "city", "citta", "ciudad", "area", "region", "regione", "lake", "lago", "valle",
            "valley", "the", "del", "della", "de", "di", "la", "el", "los", "las", "isole", "islands",
            "islas", "isla", "isola", "oasi", "oasis", "monte", "mount", "mountain", "montagne"}


def _name_tokens(name: str) -> set[str]:
    toks = {t for t in place_key(name).split() if len(t) >= 4 and t not in _GENERIC}
    return toks or set(place_key(name).split())


def _tok_match(toks: set[str], words: set[str]) -> bool:
    if toks & words:
        return True  # "Cusco" / "Cuzco", "Chalten" / "Chaltén" below
    return any(difflib.get_close_matches(t, words, n=1, cutoff=0.8) for t in toks if len(t) >= 5)


def _merge_activities(acts: list[DraftActivity]) -> list[DraftActivity]:
    by: dict[str, DraftActivity] = {}
    for a in acts:
        cur = by.get(a.type)
        if cur is None:
            by[a.type] = a.model_copy()
            continue
        if _DIFF_RANK.get(a.difficulty or "", 0) > _DIFF_RANK.get(cur.difficulty or "", 0):
            cur.difficulty = a.difficulty
        elif cur.difficulty is None:
            cur.difficulty = a.difficulty
        if a.max_altitude_m and (not cur.max_altitude_m or a.max_altitude_m > cur.max_altitude_m):
            cur.max_altitude_m = a.max_altitude_m
        cur.glacier = cur.glacier or a.glacier
    out = list(by.values())
    if len(out) > 1:
        out = [a for a in out if a.type != "unknown"] or out
    return out


def _merge_notes(notes: list[str | None]) -> str | None:
    seen, out = set(), []
    for n in notes:
        for part in _sentences(n or ""):
            k = _fold(part)
            if k and k not in seen:
                seen.add(k)
                out.append(part)
    return " ".join(out) or None


def merge_consecutive(stops: list[DraftStop], evs: list[str | None] | None = None):
    """Small models often return one stop per day. Fold runs of the same place into one.
    With `evs`, returns (stops, evs) with each stop's day text joined the same way."""
    out: list[DraftStop] = []
    out_ev: list[str | None] = []
    for i, s in enumerate(stops):
        prev = out[-1] if out else None
        ev = evs[i] if evs else None
        if (prev is not None and place_key(prev.name) == place_key(s.name)
                and s.start_date <= prev.end_date + timedelta(days=1)):
            prev.end_date = max(prev.end_date, s.end_date)
            prev.start_date = min(prev.start_date, s.start_date)
            prev.activities = _merge_activities(prev.activities + s.activities)
            prev.notes = _merge_notes([prev.notes, s.notes])
            prev.visits = prev.visits + [v for v in s.visits
                                         if not any(_dupe(v.name, w.name) for w in prev.visits)]
            prev.days_estimated = prev.days_estimated or s.days_estimated
            if evs:
                out_ev[-1] = "\n".join(e for e in (out_ev[-1], ev) if e)
        else:
            out.append(s.model_copy(deep=True))
            out_ev.append(ev)
    return (out, out_ev) if evs is not None else out


def assign_days(stops: list[DraftStop], days: list[Day]) -> list[list[int]]:
    """Which program days belong to which stop, by place names in the day headings.
    Walks forward only: a day goes to the latest stop its heading names, a day whose
    heading names no stop ("Giornata libera") stays with the stop before it."""
    toks = [_name_tokens(s.name) for s in stops]
    out: list[list[int]] = [[] for _ in stops]
    cur, pending = -1, []
    for k, d in enumerate(days):
        if d.travel:
            continue
        lo = max(cur, 0)
        tt = set(_fold(f"{d.title} {d.sleep or ''}").split())
        cand = [j for j in range(lo, min(lo + 4, len(stops))) if _tok_match(toks[j], tt)]
        if not cand:  # the heading is not a place: try the start of the day's text
            bt = set(_fold(f"{d.subtitle} {d.body[:200]}").split())
            cand = [j for j in range(cur + 1, min(cur + 3, len(stops))) if _tok_match(toks[j], bt)][:1]
        if cand:
            cur = max(cand)
        if cur < 0:
            pending.append(k)
        else:
            out[cur].extend(pending)
            pending = []
            out[cur].append(k)
    return out


def _same_place(a: str, b: str) -> bool:
    ka, kb = place_key(a), place_key(b)
    return ka == kb or difflib.SequenceMatcher(None, ka, kb).ratio() >= 0.8  # Cuzco / Cusco


def _heading_place(title: str) -> str | None:
    # "Lima - Cusco" or "Lima / Cusco": the traveller ends the day at the last place
    parts = [p for p in re.split(r"\s+-\s+|\s*[–—/>→]\s*", title) if p.strip()]
    title = parts[-1] if parts else title
    return _place(title) or _place(title.title())


class _Seg(NamedTuple):
    place: str
    from_sleep: bool
    ks: list[int]


def segments(days: list[Day]) -> list[_Seg]:
    """Cut the program into stops. A day belongs to the place where the traveller sleeps
    ("Pernottamento a Puno"); without that line, to the place in the heading; a day with
    neither ("Giornata libera") stays with the stop before it."""
    home = _home_words(f"{days[0].title} {days[0].body}")
    segs: list[_Seg] = []
    for k, d in enumerate(days):
        if d.travel:
            continue
        place, from_sleep = (d.sleep, True) if d.sleep else (_heading_place(d.title), False)
        if place and place_key(place) in home:
            continue
        if not place or (segs and _same_place(segs[-1].place, place)):
            if segs:
                segs[-1].ks.append(k)
                if from_sleep and not segs[-1].from_sleep:
                    segs[-1] = _Seg(place, True, segs[-1].ks)
            continue
        segs.append(_Seg(place, from_sleep, [k]))
    return segs


# ---------------------------------------------------------------- places visited during a stop

# words that start with a capital in a heading but are not places ("Giornata libera")
NOT_PLACE = {"giornata", "libera", "libero", "free", "day", "relax", "natura", "riserva", "rientro",
             "ritorno", "partenza", "arrivo", "trasferimento", "volo", "escursione", "escursioni",
             "visita", "mattinata", "pomeriggio", "sera", "notte", "arrival", "departure", "transfer",
             "flight", "rest", "leisure", "libre", "llegada", "salida", "ciao", "benvenuti", "welcome",
             "pronti", "oggi", "today", "domani", "alla", "scoperta", "tempo", "il", "grande", "fine",
             "end", "programma", "program", "viaggio", "trip", "tour", "giro", "cena", "pranzo"}
_VISIT_TYPE = (r"((?:sito\s+archeologico|sito|rovine|citt[aà]|cittadina|villaggio|paese|isola|isole|"
               r"lago|laguna|baia|valle|piazza|chiesa|cattedrale|museo|monastero|ghiacciaio|monte|cerro|"
               r"fiordo|canyon|cascata|cascate|town|village|city|island|islands|lake|ruins|site|"
               r"glacier|mount|falls|ciudad|pueblo|isla|islas|glaciar)\s+(?:di\s+|de\s+|of\s+)?)?")
VISIT_VERB = re.compile(
    r"\b(?:visiteremo|visitiamo|visiterete|visitaremos|visitamos|conoceremos|esploreremo|scopriremo|"
    r"raggiungeremo|ammireremo|we\s+(?:visit|explore|reach|see)|visiting|visit|explore|"
    r"(?:continu|prosegu)(?:eremo|iamo)\s+(?:verso|per|fino\s+a|alla\s+volta\s+di)|"
    r"(?:continue|head|go\s+on)\s+to|(?:continuamos|seguimos)\s+hacia|"
    r"(?:partiremo|partiamo|partenza)(?:\s+\w+){0,3}?\s+(?:verso|per|alla\s+volta\s+di)|"
    r"(?:ci\s+)?dirig(?:iamo|eremo|erci)\s+verso|"
    r"(?:trekking|trek|escursione|camminata|navigazione|hike|walk|excursi[oó]n|caminata|navegaci[oó]n)"
    r"\s+(?:a|al|alla|allo|ai|agli|alle|all['’]|fino\s+a(?:l|lla|llo)?|verso|to|up\s+to|hacia|a\s+la|"
    r"sul|sulla|sui|nel|nella|nei|lungo|tra|on|along|in|en|por))\s+"
    r"(?:[«“\"']\s*)?(?:(?:il|lo|la|l['’]|i|gli|le|the|el|los|las)\s+)?" + _VISIT_TYPE
    + r"((?-i:[A-ZÀ-Ý][\w'’-]+)(?:\s+(?:(?:de|del|di|da|la|las|los|el|y|of|the)\s+){0,2}(?-i:[A-ZÀ-Ý][\w'’-]+)){0,3})",
    re.I)
VISIT_CUE = re.compile(r"\b(?:visit\w*|seeing|see|including|incl|vedere|tra cui|compres[oaie]|"
                       r"conoc\w*|incluye\w*)\b|[:(]", re.I)


def _place_like(part: str) -> str | None:
    """'Le isole Uros' -> 'Isole Uros'; 'Giornata libera' -> None."""
    part = re.sub(r"[!?.:;«»“”\"]", " ", part).strip()
    part = re.sub(r"^(?:il|lo|la|i|gli|le|l['’]|the|el|los|las)\s+", "", part, flags=re.I).strip()
    words = part.split()
    if not words or len(words) > 5:
        return None
    if art.match(part, None, None):
        return part[0].upper() + part[1:]
    caps = [w for w in words if w[:1].isupper() and _fold(w) not in STOPWORDS
            and _fold(w) not in NOT_PLACE and _fold(w) not in MONTHS]
    if not caps or any(_fold(w) in NOT_PLACE for w in words):
        return None
    return part[0].upper() + part[1:]


def _title_places(title: str) -> list[str]:
    """Places named in a day heading. 'Moray, Maras e Chinchero' -> three; 'Lima - Cusco'
    is a transfer (the stop is where you sleep), so it gives none."""
    if re.search(r"\s[-–—/>→]\s|→|->", title):
        return []
    parts = re.split(r"\s*,\s*|\s+(?:e|ed|and|y|et|und)\s+|\s*&\s*", title)
    return [p for p in (_place_like(x) for x in parts) if p]


def _text_places(body: str) -> list[str]:
    """Places the day's own text says you visit: 'Partiremo per Moray', 'visiteremo il sito
    archeologico di Chinchero', 'Trekking alla Laguna de los Tres'."""
    out: list[str] = []
    for sent in _sentences(_firm(body)):
        moving = TRANSPORT.search(sent) or BOAT_TRANSFER.search(sent)
        for m in VISIT_VERB.finditer(sent):
            if moving and re.match(r"partenza", m[0], re.I):  # "partenza in bus per Paracas"
                continue
            # "il sito archeologico di Chinchero" -> Chinchero, but "Lago Grey" keeps its "Lago"
            p = _place_like(f"{m[1]}{m[2]}" if m[1] and m[1][0].isupper() else m[2])
            if p:
                out.append(p)
    return out


def _dupe(a: str, b: str, by_landmark: bool = True) -> bool:
    """Same place: 'Salineras de Maras' and 'Maras', or two names of one landmark."""
    ta, tb = set(_name_tokens(a)), set(_name_tokens(b))
    if _same_place(a, b) or (ta and tb and (ta <= tb or tb <= ta)):
        return True
    if not by_landmark:
        return False
    la, lb = art.match(a, None, None), art.match(b, None, None)
    return bool(la and lb and la.id == lb.id)


def add_visit(visits: list[DraftVisit], name: str, on: date | None, skip: list[str],
              limit: int = 12) -> None:
    """Add a visit unless it is one of the skip places (by name: Machu Picchu is not
    Aguas Calientes even if they share a picture) or a visit already listed."""
    name = name.strip(" .,;:-")
    if (not name or len(visits) >= limit or any(_dupe(name, x, False) for x in skip if x)
            or any(_dupe(name, v.name) for v in visits) or place_key(name) in HOME):
        return
    visits.append(DraftVisit(name=name, date=on))


def day_visits(days: list[Day], ks: list[int], stop: str, dates: list[date]) -> list[DraftVisit]:
    """The places of a stop's days besides the stop itself, in order, each on its day. The
    place you slept the night before is where the day starts, not something you go to see."""
    out: list[DraftVisit] = []
    for k, on in zip(ks, dates):
        d = days[k]
        before = days[k - 1].sleep if k > 0 else None
        for name in _title_places(d.title) + _text_places(d.body):
            add_visit(out, name, on, [stop, d.sleep, before])
    return out


def backed_visits(names: list[DraftVisit], ev: str, have: list[DraftVisit], stop: str,
                  dated: list[tuple[date, str]] | None = None) -> None:
    """The model's visits, kept only when the stop's own text names them."""
    words = set(_fold(ev).split())
    for v in names:
        toks = _name_tokens(v.name)
        if not toks or not all(_tok_match({t}, words) for t in toks):
            continue
        on = next((d for d, t in dated or [] if _tok_match(toks, set(_fold(t).split()))), v.date)
        add_visit(have, v.name, on, [stop])


def _segment_visits(seg: str, place: str | None) -> list[DraftVisit]:
    """'4 days in Cusco visiting Moray, Maras and Chinchero' -> Moray, Maras, Chinchero."""
    at = seg.find(place) if place else -1
    cue = VISIT_CUE.search(seg, at + len(place)) if at >= 0 else None
    if not cue:
        return []
    tail = seg[cue.start():]
    out: list[DraftVisit] = []
    for part in re.split(r"\s*[,;()]\s*|\s+(?:e|ed|and|y|et|und|or|o)\s+|\s*&\s*", tail):
        part = re.sub(r"^\W*(?:visit\w*|seeing|see|including|incl|vedere|tra cui|compres\w*|"
                      r"conoc\w*|incluye\w*)\b", "", part, flags=re.I).strip(" :")
        p = _place_like(DUR.sub(" ", part)) if part else None
        if p:
            add_visit(out, p, None, [place])
    return out


def build_from_days(days: list[Day], text: str, today: date,
                    model_stops: list[DraftStop] | None = None):
    """Stops, dates, sleeping altitude and day texts of a day-by-day program, decided by the
    program itself. The model's stops only lend their activities (and a cleaner name when
    the heading is not a place) to the days they match."""
    start, _ = _day_dates(days, text, today)
    owner: dict[int, int] = {}
    if model_stops:
        for j, ks in enumerate(assign_days(model_stops, days)):
            for k in ks:
                owner.setdefault(k, j)
    stops, evs, note_evs = [], [], []
    for seg in segments(days):
        js = list(dict.fromkeys(owner[k] for k in seg.ks if k in owner))
        name = seg.place
        if not seg.from_sleep and js:
            name = model_stops[js[0]].name
        ev = "\n".join(f"{days[k].title}. {days[k].subtitle}. {days[k].body}" for k in seg.ks)
        if model_stops is not None:
            acts = [a.model_copy() for j in js for a in model_stops[j].activities]
        else:
            acts = _activities(ev, allow_unknown=False)  # "patate (forse)" is not "I don't know"
        alts = [days[k].sleep_alt for k in seg.ks
                if days[k].sleep_alt and days[k].sleep and _same_place(days[k].sleep, seg.place)]
        on = [_date_of(days, start, days[k].n) for k in seg.ks]
        visits = day_visits(days, seg.ks, name, on)
        if model_stops is not None:
            dated = [(d, f"{days[k].title} {days[k].body}") for k, d in zip(seg.ks, on)]
            backed_visits([v for j in js for v in model_stops[j].visits], ev, visits, name, dated)
        stops.append(DraftStop(name=name, start_date=on[0], end_date=on[-1],
                               activities=_merge_activities(acts), elevation_m=max(alts) if alts else None,
                               visits=visits))
        evs.append(ev)
        note_evs.append("\n".join(days[k].body for k in seg.ks))
    return stops, evs, note_evs


def questions_for(text: str, today: date, lang: str) -> list[str]:
    """Only what the text does not say and the plan cannot find out: the weather is looked
    up and the plan itself asks about missing altitudes, so the start date is all."""
    return [] if _find_date(text, today) is not None else [_q(lang, "dates")]


def _sanitize(d: DraftItinerary, today: date) -> DraftItinerary:
    fixed = []
    for s in d.stops[:MAX_STOPS]:
        if s.end_date < s.start_date:
            s.end_date = s.start_date
        if (s.end_date - s.start_date).days > 90:
            s.end_date = s.start_date + timedelta(days=90)
        if not s.activities:
            s.activities = [DraftActivity(type="city")]
        s.notes = clean_note(s.notes)
        s.visits = s.visits[:12]
        fixed.append(s)
    # the same note on several stops is agency boilerplate, not about the place
    counts: dict[str, int] = {}
    for s in fixed:
        if s.notes:
            counts[_fold(s.notes)] = counts.get(_fold(s.notes), 0) + 1
    if len(fixed) >= 3:
        for s in fixed:
            if s.notes and counts[_fold(s.notes)] >= 2:
                s.notes = None
    d.stops = fixed
    d.questions = d.questions[:3]
    return d


# ---------------------------------------------------------------- LLM path

def _budget(n_chars: int, max_ctx: int) -> tuple[int, int]:
    """(max_tokens, num_ctx) for a text of n_chars. ~3 chars per token is a safe estimate
    for Italian/Spanish; the system prompt is ~900 tokens."""
    max_tokens = 4096 if n_chars > 3000 else 1500
    need = n_chars // 3 + 1100 + max_tokens
    for ctx in (4096, 8192, 16384, 32768, 65536):
        if ctx >= need:
            return max_tokens, min(ctx, max_ctx)
    return max_tokens, max_ctx


def parse_with_llm(text: str, today: date, client: LLMClient | None = None) -> DraftItinerary:
    client = client or LLMClient()
    s = client.s
    lang = detect_language(text)
    days = day_blocks(text)
    prompt = condense(days, text, lang) if days else text
    max_tokens, num_ctx = _budget(len(prompt), s.llm_num_ctx_max)
    timeout = max(s.llm_timeout_s, min(s.llm_long_timeout_s, 60 + len(prompt) / 80))
    user = (f"TODAY is {today.isoformat()}. The description is in {lang}: write notes in "
            f"{lang}.\nTrip description:\n{prompt}")
    data = client.chat_json(SYSTEM, user, max_tokens=max_tokens, num_ctx=num_ctx, timeout=timeout)
    data.pop("questions", None)  # small models invent them; we ask only what is missing
    draft = DraftItinerary(**data)
    draft.parser = "llm"
    draft.stops = merge_consecutive(draft.stops)
    if days:
        draft.stops, evs, note_evs = build_from_days(days, text, today, draft.stops)
    else:
        evs = note_evs = [None] * len(draft.stops)
        for st in draft.stops:
            kept: list[DraftVisit] = []
            backed_visits(st.visits, text, kept, st.name)
            st.visits = kept
        if draft.stops and not _has_lengths(text):
            # "Lima, then Cusco, then Titicaca": the model makes up how long. Spread evenly
            # instead, and say it is a guess.
            start = _find_date(text, today) or today + timedelta(days=30)
            for st, (a, b) in zip(draft.stops, lay_out(spread([None] * len(draft.stops), None), start)):
                st.start_date, st.end_date, st.days_estimated = a, b, True
    refine_activities(draft.stops, evs, text)
    for st, ev in zip(draft.stops, note_evs):
        if ev is not None:
            st.notes = facts_note(ev, st.name)
    draft.questions = questions_for(text, today, lang)
    draft.estimate = estimate_for(draft, text, today, lang)
    return _sanitize(draft, today)


def _has_lengths(text: str) -> bool:
    return bool(DUR.search(text) or WEEK.search(text) or RANGE.search(text))


def estimate_for(d: DraftItinerary, text: str, today: date, lang: str,
                 total: int | None = None) -> DraftEstimate | None:
    """What the app must mark as a guess, and the questions that cover it. The length
    question joins d.questions here (the start date one is already there)."""
    start = _find_date(text, today) is None
    days = any(s.days_estimated for s in d.stops)
    if not d.stops or not (start or days):
        return None
    qs = [_q(lang, "dates")] if start else []
    if days and total is None:
        n = next(((s.end_date - s.start_date).days + 1 for s in d.stops if s.days_estimated), 2)
        qs.append(_q(lang, "length", n=n))
        d.questions.insert(1 if start else 0, qs[-1])
    return DraftEstimate(start=start, days=days, total_days=total, questions=qs)


# ---------------------------------------------------------------- rule-based fallback

def _find_date(text: str, today: date) -> date | None:
    m = ISO.search(text)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            pass
    for rx, order in ((RANGE, "dm"), (DMY, "dm"), (MDY, "md")):
        for m in rx.finditer(text):
            day_s, mon_s = (m[1], m[2]) if order == "dm" else (m[2], m[1])
            mon = MONTHS.get(mon_s.lower())
            if not mon:
                continue
            year = int(m[3]) if m[3] else today.year
            try:
                d = date(year, mon, int(day_s))
            except ValueError:
                continue
            if not m[3] and d < today:
                d = date(year + 1, mon, int(day_s))
            return d
    return None


def _place(seg: str) -> str | None:
    cleaned = DUR.sub(" ", seg)
    cleaned = ALT.sub(" ", cleaned)
    cleaned = ISO.sub(" ", cleaned)
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    # "Le isole Uros" -> "isole Uros", but "El Calafate" and "La Paz" stay whole
    cleaned = re.sub(r"^\s*(?:il|lo|la|i|gli|le|l['’]|the|el|los|las)\s+(?=(?-i:[a-zà-ÿ]))", "", cleaned, flags=re.I)
    m = re.search(r"\b(?:in|at|a|to|around|near|nel|nella|al|alla|ad)\s+([A-Z][\w'’.-]*(?:\s+(?:de|del|di|da|du|la|le|d'|of)?\s*[A-Z][\w'’.-]*)*)", cleaned)
    if m:
        return m.group(1).strip(" .,")
    caps = re.findall(r"\b[A-Z][\w'’.-]+(?:\s+(?:de|del|di|da|du|la|le|of)\s+[A-Z][\w'’.-]+|\s+[A-Z][\w'’.-]+)*", cleaned)
    caps = [c for c in caps if c.lower() not in STOPWORDS and c.lower() not in MONTHS]
    if caps:
        return caps[0].strip(" .,")
    words = [w for w in re.findall(r"[\w'’-]+", cleaned) if w.lower() not in STOPWORDS
             and w.lower() not in MONTHS and not w.isdigit()]
    return " ".join(words[:3]).title() if words else None


def _day_by_day(text: str, today: date) -> DraftItinerary | None:
    """Agency format: 'Giorno 2: Lima ...'. One stop per run of days in the same place."""
    days = day_blocks(text)
    if not days:
        return None
    stops, _, note_evs = build_from_days(days, text, today)
    if not stops:
        return None
    for st, ev in zip(stops, note_evs):
        st.notes = facts_note(ev, st.name)
    name = " · ".join(s.name for s in stops[:3])
    return DraftItinerary(trip_name=name, stops=stops,
                          questions=questions_for(text, today, detect_language(text)), parser="rules")


_LIST_SEP = re.compile(r"\s*(?:,|;|->|→|–|—|\s-\s|\s+(?:e|ed|and|y|et|und|then|poi|quindi)\s+)\s*", re.I)
_BULLET = " -•*·\t"


def _lengths(item: str) -> int | None:
    m, w = DUR.search(item), WEEK.search(item)
    if m:
        return max(int(m[1]), 1)
    if w:
        return 7 * (1 if w[1].lower() in ("a", "one", "una") else int(w[1]))
    return None


def place_list(text: str, today: date) -> tuple[str, list[tuple[str, list[str]]]] | None:
    """'Lima, Cusco, Machu Picchu, Titicaca', one place per line, or 'Lima -> Cusco': the
    places in order (each with the places in its brackets, 'Cusco (Moray, Maras)'), and the
    header before a colon ('Perù, 2 settimane: ...'). None when the text is prose or when
    every place already says how long."""
    t = text.strip()
    lines = [ln.strip(_BULLET) for ln in t.split("\n") if ln.strip(_BULLET)]
    header = ""
    if len(lines) >= 2:
        first = lines[0]
        if first.endswith(":") or (len(lines) >= 3 and (_lengths(first) or _find_date(first, today))
                                   and not _place(DUR.sub(" ", WEEK.sub(" ", first)))):
            header, lines = first.rstrip(":"), lines[1:]
        raw = []
        for ln in lines:  # "Cusco: Moray, Maras" on its own line
            head, colon, rest = ln.partition(":")
            raw.append(f"{head} ({rest})" if colon and rest.strip() else ln)
    else:
        line = lines[0] if lines else ""
        head, colon, rest = line.partition(":")
        if colon and len(_LIST_SEP.split(_protect(rest))) >= 2:
            header, line = head, rest
        raw = _LIST_SEP.split(_protect(line))
    items: list[tuple[str, list[str]]] = []
    for r in raw:
        r = r.replace("\x00", ",").replace("\x01", " ").strip(_BULLET + " .")
        if not r:
            continue
        inner = re.findall(r"\(([^)]*)\)", r)
        core = re.sub(r"\([^)]*\)", " ", r).strip()
        bare = WEEK.sub(" ", DUR.sub(" ", core))
        if (len(bare.split()) > 6 or re.search(r"[.!?]\s+\w", core) or VISIT_CUE.search(core)
                or not _place(bare)):
            return None  # prose: "3 days in Cusco visiting Moray, Maras and Chinchero"
        subs = [x for part in inner for x in re.split(r"\s*[,;]\s*|\s+(?:e|and|y)\s+", part) if x.strip()]
        items.append((core, subs))
    if len(items) < 2 or all(_lengths(c) for c, _ in items):
        return None
    return header, items


def _protect(s: str) -> str:
    """Commas and 'e' inside brackets are not list separators."""
    return re.sub(r"\([^)]*\)", lambda m: m[0].replace(",", "\x00").replace(" ", "\x01"), s)


def _from_list(text: str, today: date, header: str, items) -> DraftItinerary:
    lang = detect_language(text)
    total = _lengths(header) if header else None
    start = _find_date(header, today) if header else None
    start = start or _find_date(text, today)
    stops = []
    for core, subs in items:
        place = _place(WEEK.sub(" ", DUR.sub(" ", core)))
        visits: list[DraftVisit] = []
        for x in subs:
            p = _place_like(x) or _place(x)
            if p:
                add_visit(visits, p, None, [place])
        stops.append((place, _lengths(core), _activities(core), visits))
    first = start or today + timedelta(days=30)
    dates = lay_out(spread([k for _, k, _, _ in stops], total), first)
    d = DraftItinerary(stops=[DraftStop(name=p, start_date=a, end_date=b, activities=acts, visits=v,
                                        days_estimated=k is None)
                              for (p, k, acts, v), (a, b) in zip(stops, dates)], parser="rules")
    d.trip_name = " · ".join(s.name for s in d.stops[:3])
    d.questions = [_q(lang, "dates")] if start is None else []
    d.estimate = estimate_for(d, text, today, lang, total)
    return d


def parse_with_rules(text: str, today: date) -> DraftItinerary:
    dbd = _day_by_day(text, today)
    if dbd is not None:
        dbd.estimate = estimate_for(dbd, text, today, detect_language(text))
        return dbd
    pl = place_list(text, today)
    if pl is not None:
        return _from_list(text, today, *pl)
    lang = detect_language(text)
    questions: list[str] = []
    start = _find_date(text, today)
    if start is None:
        start = today + timedelta(days=30)
        questions.append(_q(lang, "dates"))
    found = []  # (place, days or None, own date, activities, visits)
    for seg in SPLIT.split(text):
        seg = seg.strip(" .,-")
        if not seg:
            continue
        place = _place(seg)
        if not place:
            continue
        acts = _activities(seg)
        for a in acts:  # in a one-line description a stated altitude belongs to the hike
            if a.type in ("hiking", "trek_multiday", "ski") and not a.max_altitude_m:
                nums = _numbers_m(seg)
                a.max_altitude_m = max(nums) if nums else None
        found.append((place, _lengths(seg), _find_date(seg, today), acts, _segment_visits(seg, place)))
    days = spread([k for _, k, _, _, _ in found], None)
    stops: list[DraftStop] = []
    cursor = start
    for (place, known, own, acts, visits), n in zip(found, days):
        seg_start = own or cursor
        end = seg_start + timedelta(days=max(n, 1) - 1)
        stops.append(DraftStop(name=place, start_date=seg_start, end_date=end, activities=acts,
                               visits=visits, days_estimated=known is None))
        cursor = end + timedelta(days=1)
    for s in stops:
        for a in s.activities:
            if a.type == "hiking" and not a.max_altitude_m:
                questions.append(_q(lang, "high", place=s.name))
                break
    name = " · ".join(s.name for s in stops[:3]) if stops else None
    d = DraftItinerary(trip_name=name, stops=stops, questions=questions[:4], parser="rules")
    d.estimate = estimate_for(d, text, today, lang)
    return d


def parse_itinerary(text: str, today: date | None = None, client: LLMClient | None = None,
                    use_llm: bool = True) -> DraftItinerary:
    today = today or date.today()
    text = normalize_text(text)
    if use_llm and place_list(text, today) is None:  # a list of places needs no model
        try:
            d = parse_with_llm(text, today, client)
            if d.stops:
                return d
        except (LLMUnavailable, ValidationError, ValueError, KeyError, TypeError) as e:
            log.info("LLM itinerary parse failed, using rules: %s", e)
    d = parse_with_rules(text, today)
    d.stops = merge_consecutive(d.stops)
    return _sanitize(d, today)
