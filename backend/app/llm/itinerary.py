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

import difflib
import html
import logging
import math
import re
import unicodedata
from datetime import date, timedelta
from typing import NamedTuple

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.engine.activities import ACTIVITY_TYPES, DIFFICULTIES
from app.llm.client import LLMClient, LLMUnavailable

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


class DraftStop(BaseModel):
    name: str
    start_date: date
    end_date: date
    activities: list[DraftActivity] = Field(default_factory=list)
    notes: str | None = None


class DraftItinerary(BaseModel):
    trip_name: str | None = None
    stops: list[DraftStop]
    questions: list[str] = Field(default_factory=list)
    parser: str = "rules"


SYSTEM = """You turn a traveller's description of a trip into JSON. Output ONLY a JSON object:
{"trip_name": str, "stops": [{"name": str, "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD",
"activities": [{"type": one of ["city","hiking","trek_multiday","beach","ski","cycling","safari","boat","desert","unknown"],
"difficulty": one of ["easy","moderate","hard","technical","unknown"] or null,
"max_altitude_m": number or null, "glacier": true or false}], "notes": str or null}]}
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
                "high": "How high does the hike near {place} go?"},
    "Italian": {"dates": "Quando parti? Le date non erano chiare, quindi la bozza parte tra 30 giorni.",
                "days": "Quanti giorni a {place}? La bozza ne conta 2.",
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
                  r"rampon|ripid|homestay|deserto|dune|sandboard|rafting|\bwind|snow|rain|cold|heat|"
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
        raw.append([int(h[1]), title.strip(" -–"), _sentences(body)])
    # a sentence repeated on many days is agency boilerplate ("guida in italiano, assicurazione...")
    seen: dict[str, int] = {}
    for _, _, sents in raw:
        for k in {_fold(s) for s in sents}:
            seen[k] = seen.get(k, 0) + 1
    limit = max(3, math.ceil(len(raw) / 3))
    days = [[n, title, "\n".join(s for s in sents if seen[_fold(s)] < limit and not ADVICE.search(s))]
            for n, title, sents in raw]
    home = _home_words(f"{days[0][1]} {days[0][2]}")
    travel = [False] * len(days)
    for order in (range(len(days)), range(len(days) - 1, -1, -1)):
        for k in order:  # only at the start and at the end of the program
            if not _is_home_travel(days[k][1], days[k][2], home):
                break
            travel[k] = True
    return [Day(n, t, b, tr) for (n, t, b), tr in zip(days, travel)]


def condense(days: list[Day], text: str, lang: str) -> str:
    """What the model reads for a day-by-day program: the header and each day's own text."""
    head = text[:DAY_HEAD.search(text).start()]
    cut = SECTION.search(head)
    head = " ".join(s for s in _sentences(head[:cut.start()] if cut else head) if not ADVICE.search(s))
    label = "Giorno" if lang == "Italian" else "Day"
    lines = [head[:600]] if head else []
    for d in days:
        lines.append(f"{label} {d.n}: {d.title} (travel)" if d.travel else f"{label} {d.n}: {d.title}. {d.body.replace(chr(10), ' ')}")
    return "\n".join(lines)


def _day_dates(days: list[Day], text: str, today: date) -> tuple[date, bool]:
    """Date of the first day of the program, and whether the text gave it."""
    start = _find_date(text, today)
    if start is not None:
        return start, True
    first = next((d.n for d in days if not d.travel), days[0].n)
    return today + timedelta(days=30) - timedelta(days=first - days[0].n), False


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


def _difficulty_word(ev: str) -> str | None:
    low = ev.lower()
    for word, d in (("technical", "technical"), ("alpinistic", "technical"),
                    ("impegnativ", "hard"), ("difficile", "hard"), ("difficult", "hard"),
                    ("hard", "hard"), ("exigente", "hard"), ("media difficolt", "moderate"),
                    ("moderat", "moderate"), ("medium", "moderate"), ("facile", "easy"),
                    ("easy", "easy"), ("semplice", "easy"), ("fácil", "easy"), ("facil", "easy")):
        if word in low:
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
        if not re.search(r"pernott|overnight|passeremo la notte", s, re.I):
            return True
        return not toks or "homestay" in s.lower() or _tok_match(toks, set(_fold(s).split()))
    sents = [s for s in _sentences(ev) if FACT.search(s) and not ADVICE.search(s)
             and not NOT_FACT.search(s) and not (TRANSPORT.search(s) and not HIKE.search(s))
             and about_here(s)]
    ranked = sorted(sents, key=lambda s: -len(FACT.findall(s)))[:2]
    return clean_note(" ".join(s for s in sents if s in ranked))


def clean_note(note: str | None, limit: int = 160) -> str | None:
    """No packing advice, and cut on a sentence or word boundary, never mid-word."""
    note = " ".join(s for s in _sentences(note or "") if not ADVICE.search(s)).strip(" ,;")
    if len(note) > limit:
        cut = note[:limit]
        end = max(cut.rfind(". "), cut.rfind("; "))
        note = cut[:end + 1] if end >= 40 else cut[:cut.rfind(" ")].rstrip(" ,;:") + "…"
    return note or None


# ---------------------------------------------------------------- activities from text

def _activities(seg: str) -> list[DraftActivity]:
    s = seg.lower()
    acts: list[DraftActivity] = []
    hike_s = BOAT_EXCURSION.sub(" ", s)
    alts = _hike_numbers(seg)
    altitude = max(alts) if alts else None
    difficulty = _difficulty_in(hike_s, altitude)
    glacier = bool(GLACIER.search(hike_s))
    unknown = any(w in s for w in ("don't know", "dont know", "not sure", "boh", "non so",
                                   "maybe", "forse", "not decided"))
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
    if BOAT.search(s):
        acts.append(DraftActivity(type="boat"))
    if DESERT.search(s):
        acts.append(DraftActivity(type="desert"))
    if CITY.search(s):
        acts.append(DraftActivity(type="city"))
    if not acts:
        acts.append(DraftActivity(type="unknown" if unknown else "city"))
    return acts


_CHECKS = {"beach": BEACH, "ski": SKI, "cycling": BIKE, "safari": SAFARI, "boat": BOAT,
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
                if a.type == "safari" and BOAT.search(scope):
                    a.type = "boat"
                elif ev is not None or a.type in ("safari", "boat"):
                    continue
            if a.type in ("hiking", "trek_multiday", "ski"):
                if a.max_altitude_m and not _altitude_ok(a.max_altitude_m, scope):
                    a.max_altitude_m = None  # invented: the plan asks for it instead
                if not a.max_altitude_m and ev is not None:
                    stated = _hike_numbers(ev)
                    a.max_altitude_m = max(stated) if stated else None
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
            for extra in _activities(ev):
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
        tt = set(_fold(d.title).split())
        cand = [j for j in range(lo, min(lo + 4, len(stops))) if _tok_match(toks[j], tt)]
        if not cand:  # the heading is not a place: try the start of the day's text
            bt = set(_fold(d.body[:200]).split())
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


def align_to_days(stops: list[DraftStop], days: list[Day], text: str, today: date):
    """Give the model's stops the dates of their days. Stops that own no day are dropped
    (the model invented or split them). None when too few stops match the program."""
    assigned = assign_days(stops, days)
    matched = [j for j, ks in enumerate(assigned) if ks]
    if len(matched) < 2 and len([d for d in days if not d.travel]) >= 3:
        return None
    start, _ = _day_dates(days, text, today)
    new, evs = [], []
    for j in matched:
        ks = assigned[j]
        s = stops[j].model_copy(deep=True)
        s.start_date = _date_of(days, start, days[ks[0]].n)
        s.end_date = _date_of(days, start, days[ks[-1]].n)
        new.append(s)
        evs.append("\n".join(f"{days[k].title}. {days[k].body}" for k in ks))
    return merge_consecutive(new, evs)


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
        aligned = align_to_days(draft.stops, days, text, today)
        if aligned is None:
            raise ValueError("the model's stops do not match the program days")
        draft.stops, evs = aligned
    else:
        evs = [None] * len(draft.stops)
    refine_activities(draft.stops, evs, text)
    for st, ev in zip(draft.stops, evs):
        if ev is not None:
            st.notes = facts_note(ev, st.name)
    draft.questions = questions_for(text, today, lang)
    return _sanitize(draft, today)


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
    lang = detect_language(text)
    start, _ = _day_dates(days, text, today)
    home = _home_words(f"{days[0].title} {days[0].body}")
    runs: list[list] = []  # [place, first_day, last_day, day texts]
    for d in days:
        if d.travel:
            continue
        # "Lima - Cusco" or "Lima / Cusco": the traveller sleeps at the last place
        parts = [p for p in re.split(r"\s+-\s+|\s*[–—/>→]\s*", d.title) if p.strip()]
        title = parts[-1] if parts else d.title
        place = _place(title) or _place(title.title())
        if place and place_key(place) in home:
            continue
        if not place:
            if runs:  # "Giornata libera": same place as the day before
                runs[-1][2] = d.n
                runs[-1][3].append(d.body)
            continue
        if runs and place_key(runs[-1][0]) == place_key(place):
            runs[-1][2] = d.n
            runs[-1][3].append(f"{d.title}. {d.body}")
        else:
            runs.append([place, d.n, d.n, [f"{d.title}. {d.body}"]])
    if not runs:
        return None
    stops = []
    for p, a, b, texts in runs:
        ev = "\n".join(texts)
        stops.append(DraftStop(name=p, start_date=_date_of(days, start, a),
                               end_date=_date_of(days, start, max(a, b)),
                               activities=_merge_activities(_activities(ev)), notes=facts_note(ev, p)))
    name = " · ".join(s.name for s in stops[:3])
    return DraftItinerary(trip_name=name, stops=stops, questions=questions_for(text, today, lang),
                          parser="rules")


def parse_with_rules(text: str, today: date) -> DraftItinerary:
    dbd = _day_by_day(text, today)
    if dbd is not None:
        return dbd
    lang = detect_language(text)
    questions: list[str] = []
    start = _find_date(text, today)
    if start is None:
        start = today + timedelta(days=30)
        questions.append(_q(lang, "dates"))
    stops: list[DraftStop] = []
    cursor = start
    for seg in SPLIT.split(text):
        seg = seg.strip(" .,-")
        if not seg:
            continue
        place = _place(seg)
        if not place:
            continue
        m = DUR.search(seg)
        w = WEEK.search(seg)
        if m:
            n = int(m[1])
            if m[2].lower().startswith(("night", "nott")):
                n = max(n, 1)
        elif w:
            n = 7 * (1 if w[1].lower() in ("a", "one", "una") else int(w[1]))
        else:
            n = 2
            questions.append(_q(lang, "days", place=place))
        seg_start = _find_date(seg, today) or cursor
        end = seg_start + timedelta(days=max(n, 1) - 1)
        acts = _activities(seg)
        for a in acts:  # in a one-line description a stated altitude belongs to the hike
            if a.type in ("hiking", "trek_multiday", "ski") and not a.max_altitude_m:
                nums = _numbers_m(seg)
                a.max_altitude_m = max(nums) if nums else None
        stops.append(DraftStop(name=place, start_date=seg_start, end_date=end, activities=acts))
        cursor = end + timedelta(days=1)
    for s in stops:
        for a in s.activities:
            if a.type == "hiking" and not a.max_altitude_m:
                questions.append(_q(lang, "high", place=s.name))
                break
    name = " · ".join(s.name for s in stops[:3]) if stops else None
    return DraftItinerary(trip_name=name, stops=stops, questions=questions[:4], parser="rules")


def parse_itinerary(text: str, today: date | None = None, client: LLMClient | None = None,
                    use_llm: bool = True) -> DraftItinerary:
    today = today or date.today()
    text = normalize_text(text)
    if use_llm:
        try:
            d = parse_with_llm(text, today, client)
            if d.stops:
                return d
        except (LLMUnavailable, ValidationError, ValueError, KeyError, TypeError) as e:
            log.info("LLM itinerary parse failed, using rules: %s", e)
    d = parse_with_rules(text, today)
    d.stops = merge_consecutive(d.stops)
    return _sanitize(d, today)
