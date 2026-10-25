"""Free text -> draft itinerary. LLM first, rule-based parser as fallback.

The result is always a DRAFT the user confirms in the UI; nothing is saved here.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, timedelta

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
                   "don't know": "unknown", "not sure": "unknown"}
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
"activities": [{"type": one of ["city","hiking","trek_multiday","beach","ski","cycling","safari","boat","unknown"],
"difficulty": one of ["easy","moderate","hard","technical","unknown"] or null,
"max_altitude_m": number or null, "glacier": true or false}], "notes": str or null}], "questions": [str]}
Rules:
- "name" is a real place name that a map search can find (a town, park or region).
- Consecutive stops: the next stop starts the day after the previous one ends, unless dates are given.
- If no start date is given, start 30 days after TODAY and add a question asking for the dates.
- If the traveller does not know what they will do, use type "unknown". If a hike's difficulty is unclear, use "unknown".
- "trek_multiday" only when the text says the walk lasts several days with nights in huts or tents. A day hike is "hiking".
- "boat" is for boat trips, navigation, kayak and rafting. "safari" only for wildlife game drives.
- A travel or transfer day, or a free/reserve day, adds no activity beyond "city".
- Difficulty: a hike of 7 hours or more is "hard". "glacier": true only for walking on ice with crampons.
- Read only each day's own description. General sections (what is included, clothing and gear
  advice, insurance, documents) say nothing about where or what the traveller does.
- max_altitude_m: only a number the text gives, or the well-known highest point of a famous
  named trek (Laugavegur 1100, Tour du Mont Blanc 2665, W Trek 900, Inca Trail 4215). Otherwise null. Never guess.
- Ask at most 3 short questions, only for information that changes what clothes to pack and
  that the text does not already give. Never ask for dates the text gives.
- "notes": at most 15 words about what happens at that stop that matters for clothes
  (e.g. "8-hour hike to Laguna de los Tres"), else null. Never copy general advice
  ("layered clothing, waterproof boots, sun cream") or the agency's general text into notes.
- Write trip_name, notes and questions in the language of the trip description.
- Never invent dates the traveller gave differently. Never add stops they did not mention.
- The text may be a long day-by-day itinerary from a travel agency ("Day 1", "Giorno 2", ...).
  Then make ONE stop per place, not per day: merge consecutive days spent in or around the
  same place. Ignore flights, transfers, hotels, meals, prices and booking terms. A day that is
  only travel belongs to the stop where the traveller sleeps. At most 40 stops."""

MAX_STOPS = 40
_DAY_LABEL = r"(?:day|giorno|gg|día|dia|jour|tag)"


def normalize_text(text: str) -> str:
    """Shrink a pasted itinerary without losing meaning: trim spaces, drop empty lines and
    re-join 'Giorno\n2\nLima' style headings that web pages split across lines."""
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
    max_tokens, num_ctx = _budget(len(text), s.llm_num_ctx_max)
    timeout = max(s.llm_timeout_s, min(s.llm_long_timeout_s, 60 + len(text) / 80))
    user = (f"TODAY is {today.isoformat()}. The description is in {lang}: write notes and "
            f"questions in {lang}.\nTrip description:\n{text}")
    data = client.chat_json(SYSTEM, user, max_tokens=max_tokens, num_ctx=num_ctx, timeout=timeout)
    draft = DraftItinerary(**data)
    draft.parser = "llm"
    draft.stops = merge_consecutive(draft.stops)
    refine_activities(draft.stops, text)
    return _sanitize(draft, today, text)


# ---------------------------------------------------------------- deterministic clean-up

def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def place_key(name: str) -> str:
    """'Ushuaia, Tierra del Fuego' and 'ushuaia' are the same stop."""
    return _fold(re.split(r"[,(]", name or "", maxsplit=1)[0])


_GENERIC = {"national", "park", "parque", "nacional", "parco", "nazionale", "glacier", "ghiacciaio",
            "glaciar", "city", "citta", "ciudad", "area", "region", "regione", "lake", "lago", "valle",
            "valley", "the", "del", "della", "de", "di", "la", "el", "los", "las"}


def _name_tokens(name: str) -> set[str]:
    toks = {t for t in place_key(name).split() if len(t) >= 4 and t not in _GENERIC}
    return toks or set(place_key(name).split())


_DIFF_RANK = {"easy": 1, "moderate": 2, "hard": 3, "technical": 4}


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
    if len(out) > 1:  # "city" adds nothing next to a real activity... except it is the evening
        out = [a for a in out if a.type != "unknown"] or out
    return out


def _merge_notes(notes: list[str | None]) -> str | None:
    seen, out = set(), []
    for n in notes:
        for part in re.split(r"(?<=[.;!?])\s+", (n or "").strip()):
            k = _fold(part)
            if k and k not in seen:
                seen.add(k)
                out.append(part.strip())
    return " ".join(out) or None


def merge_consecutive(stops: list[DraftStop]) -> list[DraftStop]:
    """Small models often return one stop per day. Fold runs of the same place into one."""
    out: list[DraftStop] = []
    for s in stops:
        prev = out[-1] if out else None
        if (prev is not None and place_key(prev.name) == place_key(s.name)
                and s.start_date <= prev.end_date + timedelta(days=1)):
            prev.end_date = max(prev.end_date, s.end_date)
            prev.start_date = min(prev.start_date, s.start_date)
            prev.activities = _merge_activities(prev.activities + s.activities)
            prev.notes = _merge_notes([prev.notes, s.notes])
        else:
            out.append(s.model_copy(deep=True))
    return out


def day_blocks(text: str) -> list[tuple[int, str, str]]:
    """'Giorno 2: Lima ...' -> [(2, 'Lima', '...body...')]. Empty when the text has no days."""
    heads = list(DAY_HEAD.finditer(text))
    if len(heads) < 3:
        return []
    out = []
    for i, h in enumerate(heads):
        body = text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)].strip()
        title = h[2].strip()
        if not title:
            title, _, body = body.partition("\n")
        cut = SECTION.search(body)
        if cut:
            body = body[:cut.start()]
        out.append((int(h[1]), title.strip(), strip_advice(body).strip()))
    return out


# general sections of an agency program that follow (or interrupt) the days
SECTION = re.compile(r"^\s*(?:la\s+)?(?:quota|prezzo|price|tariff|the price|il prezzo|cost)\w*\s+(?:non\s+)?(?:comprend|includ|inclu)"
                     r"|^\s*(?:non\s+)?(?:compres|inclus|included|not included|what'?s included|incluye|no incluye)\w*\s*:"
                     r"|^\s*(?:note|notes|informazioni|info utili|cosa portare|abbigliamento|equipaggiamento|attrezzatura"
                     r"|documenti|assicurazion|condizioni|termini|packing|what to bring|clothing|equipment|gear"
                     r"|qu[eé] llevar|ropa|equipo|documentos|seguro)\b[^\n]{0,40}(?::|$)", re.I | re.M)
ADVICE = re.compile(r"abbigliament|scarpon|scarpe|zaino|bastoncin|giacca|giacche|guanti|berrett|cappell|"
                    r"crema solare|protezione solare|occhiali|a strati|a cipolla|si consiglia|consigliat|"
                    r"raccomand|portare con|equipaggiament|attrezzatur|clothing|clothes|boots|backpack|"
                    r"layers|sunscreen|sun cream|recommend|bring |ropa|botas|mochila|recomend", re.I)


def strip_advice(text: str) -> str:
    """Drop sentences that are packing advice: they mention trails and boots on every day."""
    parts = re.split(r"(?<=[.!?;])\s+|\n", text or "")
    return " ".join(p for p in parts if p.strip() and not ADVICE.search(p))


def _evidence(stops: list[DraftStop], text: str) -> list[str | None]:
    """Text of the days that belong to each stop: by place names in the day titles, and by
    date for stops whose name never appears (the model may spell or translate it)."""
    blocks = day_blocks(text)
    if not blocks or not stops:
        return [None] * len(stops)
    toks = [_name_tokens(s.name) for s in stops]
    days: list[list[int]] = [[] for _ in stops]
    cur, matched = 0, set()
    for k, (_, title, body) in enumerate(blocks):
        tt = set(_fold(title).split())
        cand = [j for j in range(cur, min(cur + 4, len(stops))) if toks[j] & tt]
        if not cand:  # title says nothing ("Giornata libera"): look at the start of the body
            bt = set(_fold(body[:300]).split())
            cand = [j for j in range(cur + 1, min(cur + 2, len(stops))) if toks[j] & bt]
        if cand:
            cur = max(cand)
            matched.add(cur)
        days[cur].append(k)
    # date of block 0, learned from the stops whose names matched
    offsets = sorted((stops[j].start_date - timedelta(days=days[j][0])) for j in matched if days[j])
    day0 = offsets[len(offsets) // 2] if offsets else None
    out: list[str | None] = []
    for j, s in enumerate(stops):
        ks = days[j] if j in matched else []
        if not ks and day0 is not None:
            ks = [k for k in range(len(blocks))
                  if s.start_date <= day0 + timedelta(days=k) <= s.end_date]
        out.append("\n".join(f"{blocks[k][1]}\n{blocks[k][2]}" for k in ks) if ks else "")
    return out


MULTIDAY = re.compile(r"multi.?day|hut to hut|più giorni|piu giorni|rifugi|campeggio|in tenda|"
                      r"\btenda\b|campamento|refugio|camping|\bcamp\b|bivacco|\bw trek\b|circuito o\b", re.I)
HIKE = re.compile(r"trek|hik|escursion|camminat|sentier|caminata|senderismo|randonn|wander", re.I)
GLACIER = re.compile(r"rampon|crampon|grampon|minitrek|mini.trek|big ice|ice.?trek|sul ghiaccio|on the ice|"
                     r"sobre el hielo|glacier walk|camminata sul ghiacciaio|trekking sul ghiacciaio", re.I)
HOURS = re.compile(r"(\d{1,2})(?:[.,]\d)?\s*(?:(?:-|–|/|a|to|e)\s*(\d{1,2})(?:[.,]\d)?\s*)?"
                   r"(?:ore|ora|h|hrs?|hours?|horas|heures|stunden)\b", re.I)
TRANSPORT = re.compile(r"\bvol[oi]\b|flight|\bbus\b|pullman|trasferiment|transfer|navigazion|"
                       r"\bauto\b|\bdrive\b|\btreno\b|train", re.I)
BOAT = re.compile(r"rafting|kayak|canoa|canoe|navigazion|navegaci|\bbarca\b|battello|catamaran|"
                  r"gommone|\bboat\b|cruise|crociera|motonave|traghetto|ferry|lancha|zodiac", re.I)
BOAT_EXCURSION = re.compile(r"(escursion\w*|excursi\w*|gita|tour)\s+(in|con|en|by)\s+"
                            r"(barca|battello|catamarano|gommone|kayak|motoscafo|nave|boat|lancha)", re.I)
SAFARI = re.compile(r"safari|game drive|fotosafari", re.I)
BEACH = re.compile(r"beach|spiaggia|\bmare\b|snorkel|swim|nuoto|playa|plage", re.I)
SKI = re.compile(r"\bski|snowboard|sciare|\bsci\b|esqu[ií]", re.I)
BIKE = re.compile(r"cycling|\bbike|\bbici|bicicletta|mountain bike|bicicleta|\bvélo", re.I)
KNOWN_TREKS = {"laugavegur": 1100, "tour du mont blanc": 2665, "w trek": 900, "circuito w": 900,
               "inca trail": 4215, "cammino inca": 4215, "camino inca": 4215, "salkantay": 4630,
               "kilimanjaro": 5895, "everest base camp": 5364, "annapurna circuit": 5416}


def _numbers_m(text: str) -> list[float]:
    return [float(re.sub(r"[.,’' ]", "", m[1])) for m in ALT.finditer(text)]


def _altitude_ok(alt: float, ev: str) -> bool:
    if any(abs(alt - n) <= max(30.0, 0.03 * n) for n in _numbers_m(ev)):
        return True
    low = ev.lower()
    return any(k in low and abs(alt - v) <= 0.05 * v for k, v in KNOWN_TREKS.items())


def _hike_hours(ev: str) -> float:
    """Longest walking time mentioned in sentences about walking (not flights or buses)."""
    best = 0.0
    for sent in re.split(r"(?<=[.!?;])\s+|\n", ev):
        if not HIKE.search(sent) or TRANSPORT.search(sent):
            continue
        for m in HOURS.finditer(sent):
            best = max(best, float(m[2] or m[1]))
    return best


def _difficulty_in(ev: str) -> str | None:
    """Hardest of what the words say and what the walking time says (7 h or more is hard)."""
    word = _difficulty_word(ev)
    h = _hike_hours(ev)
    by_time = "hard" if h >= 7 else "moderate" if h >= 4 else "easy" if h > 0 else None
    cands = [d for d in (word, by_time) if d]
    return max(cands, key=lambda d: _DIFF_RANK[d]) if cands else None


def _difficulty_word(ev: str) -> str | None:
    low = ev.lower()
    for word, d in (("technical", "technical"), ("alpinistic", "technical"), ("alpinistic", "technical"),
                    ("impegnativ", "hard"), ("difficile", "hard"), ("difficult", "hard"),
                    ("hard", "hard"), ("exigente", "hard"), ("media difficolt", "moderate"),
                    ("moderat", "moderate"), ("medium", "moderate"), ("facile", "easy"),
                    ("easy", "easy"), ("semplice", "easy"), ("fácil", "easy"), ("facil", "easy")):
        if word in low:
            return d
    return None


def refine_activities(stops: list[DraftStop], text: str) -> None:
    """Keep what the model says only when the text backs it: the model likes to tag every
    day as a hard 2,500 m trek. Uses the days of each stop when the text is day-by-day,
    the whole text otherwise."""
    evs = _evidence(stops, text)
    for s, ev in zip(stops, evs):
        scope = ev if ev is not None else text
        hike_text = BOAT_EXCURSION.sub(" ", scope)
        kept: list[DraftActivity] = []
        for a in s.activities:
            if a.type in ("hiking", "trek_multiday"):
                if ev is not None and not HIKE.search(hike_text):
                    continue
                if a.type == "trek_multiday" and not MULTIDAY.search(scope):
                    a.type = "hiking"
                d = _difficulty_in(hike_text) if ev is not None else None
                if ev is not None:
                    a.glacier = bool(GLACIER.search(hike_text))
                if d:
                    a.difficulty = d
                elif ev is not None and a.difficulty in ("hard", "technical"):
                    a.difficulty = "moderate"  # the model's guess, not in the text
            elif a.type == "safari" and not SAFARI.search(scope):
                a.type = "boat" if BOAT.search(scope) else "city"
            elif a.type == "boat" and not BOAT.search(scope):
                a.type = "city"
            elif ev is not None and a.type in ("beach", "ski", "cycling") and not {
                    "beach": BEACH, "ski": SKI, "cycling": BIKE}[a.type].search(scope):
                continue
            if a.max_altitude_m and not _altitude_ok(a.max_altitude_m, scope):
                stated = _numbers_m(ev) if ev is not None else []
                a.max_altitude_m = max(stated) if stated else None  # null: the plan asks
            if a.type not in ("hiking", "trek_multiday", "ski"):
                a.max_altitude_m = None
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
                if extra.type != "city" and extra.type != "unknown" and extra.type not in have:
                    kept.append(extra)
        s.activities = _merge_activities(kept) or [DraftActivity(type="city")]


def clean_note(note: str | None, limit: int = 160) -> str | None:
    """No packing advice, and cut on a sentence or word boundary, never mid-word."""
    note = strip_advice(note or "").strip(" ,;")
    if len(note) > limit:
        cut = note[:limit]
        end = max(cut.rfind(". "), cut.rfind("; "))
        note = cut[:end + 1] if end >= 40 else cut[:cut.rfind(" ")].rstrip(" ,;:") + "…"
    return note or None


DATE_Q = re.compile(r"\b(date|dates|data|fecha|fechas|quando parti|when do you leave|when are you leaving|"
                    r"departure date|giorno di partenza|quale anno|which year)\b", re.I)


def _sanitize(d: DraftItinerary, today: date, text: str | None = None) -> DraftItinerary:
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
    if text is not None and _find_date(text, today) is not None:
        d.questions = [q for q in d.questions if not DATE_Q.search(_fold(q))]
    d.questions = d.questions[:3]
    return d


# ---------------------------------------------------------------- rule-based fallback

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
ALT = re.compile(r"(\d{1,2}[.,’' ]\d{3}|\d{3,4})\s?(?:m|mt|mslm|msnm|m\.s\.l\.m|meters|metres|metri|metros)\b\.?", re.I)
RANGE = re.compile(r"\b(\d{1,2})\s*(?:-|–|al|to|until|fino al|au|bis)\s*\d{1,2}\s+([a-zA-Z]{3,9})(?:\s+(\d{4}))?\b", re.I)
ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
DMY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-zA-Z]{3,9})(?:\s+(\d{4}))?\b")
MDY = re.compile(r"\b([a-zA-Z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b")
STOPWORDS = {"days", "day", "nights", "night", "in", "at", "a", "to", "the", "and", "then",
             "trekking", "hiking", "hike", "trek", "city", "beach", "ski", "skiing", "easy",
             "moderate", "hard", "technical", "difficult", "giorni", "notti", "di", "e", "nel",
             "nella", "al", "alla", "on", "for", "per", "from", "dal", "with", "con", "some",
             "maybe", "forse", "not", "sure", "know", "don't", "dont", "yet", "around", "visit",
             "visiting", "sightseeing", "tour", "week", "weeks", "settimana", "of", "my", "we",
             "i", "will", "be", "go", "going", "stay", "staying", "fino", "until", "then,",
             "multi-day", "multiday", "cycling", "bike", "safari", "mare", "spiaggia", "neve",
             "escursione", "escursioni", "camminata", "montagna", "mountains", "mountain"}


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


def _activities(seg: str) -> list[DraftActivity]:
    s = seg.lower()
    acts: list[DraftActivity] = []
    alts = _numbers_m(seg)
    altitude = max(alts) if alts else None
    hike_s = BOAT_EXCURSION.sub(" ", s)
    difficulty = _difficulty_in(hike_s)
    glacier = bool(GLACIER.search(hike_s))
    unknown = any(w in s for w in ("don't know", "dont know", "not sure", "boh", "non so",
                                   "maybe", "forse", "not decided"))
    if unknown:
        difficulty = "unknown"
    if HIKE.search(hike_s) and MULTIDAY.search(s):
        acts.append(DraftActivity(type="trek_multiday", difficulty=difficulty,
                                  max_altitude_m=altitude, glacier=glacier))
    elif HIKE.search(hike_s) or "montagn" in s or "mountain" in s:
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
    if any(w in s for w in ("city", "città", "citta", "museum", "museo", "sightseeing", "visit",
                            "centro storico", "ciudad")):
        acts.append(DraftActivity(type="city"))
    if not acts:
        acts.append(DraftActivity(type="unknown" if unknown else "city"))
    return acts


def _place(seg: str) -> str | None:
    cleaned = DUR.sub(" ", seg)
    cleaned = ALT.sub(" ", cleaned)
    cleaned = ISO.sub(" ", cleaned)
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
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


DAY_HEAD = re.compile(rf"^{_DAY_LABEL}\s*(\d{{1,3}})\b[\s:.\-–]*(.*)$", re.I | re.M)


def _day_by_day(text: str, today: date) -> DraftItinerary | None:
    """Agency format: 'Giorno 2: Lima ...'. One stop per run of days in the same place."""
    blocks = day_blocks(text)
    if not blocks:
        return None
    lang = detect_language(text)
    questions: list[str] = []
    start = _find_date(text, today)
    if start is None:
        start = today + timedelta(days=30)
        questions.append(_q(lang, "dates"))
    runs: list[list] = []  # [place, first_day, last_day, body]
    # "Italia - Buenos Aires" on day 1: Italia is home, not a stop
    first_parts = [p for p in re.split(r"\s+-\s+|\s*[–—/>→]\s*", blocks[0][1]) if p.strip()]
    home = place_key(first_parts[0]) if len(first_parts) > 1 else None
    for day, title, body in blocks:
        # "Lima - Cusco" or "Lima / Cusco": the traveller sleeps at the last place
        parts = [p for p in re.split(r"\s+-\s+|\s*[–—/>→]\s*", title) if p.strip()]
        title = parts[-1] if parts else title
        place = _place(title) or _place(title.title())
        if place and home and place_key(place) == home:
            continue  # leaving from or flying back home
        if not place:
            if runs:  # "Giornata libera": same place as the day before
                runs[-1][2] = day
                runs[-1][3] += " " + body
            continue
        if runs and runs[-1][0].lower() == place.lower():
            runs[-1][2] = day
            runs[-1][3] += " " + title + " " + body
        else:
            runs.append([place, day, day, title + " " + body])
    if not runs:
        return None
    first = runs[0][1]
    stops = [DraftStop(name=p, start_date=start + timedelta(days=a - first),
                       end_date=start + timedelta(days=max(b, a) - first),
                       activities=_activities(body[:2000])) for p, a, b, body in runs]
    name = " · ".join(s.name for s in stops[:3])
    return DraftItinerary(trip_name=name, stops=stops, questions=questions, parser="rules")


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
        stops.append(DraftStop(name=place, start_date=seg_start, end_date=end,
                               activities=_activities(seg)))
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
    return _sanitize(d, today, text)
