"""Free text -> draft itinerary. LLM first, rule-based parser as fallback.

The result is always a DRAFT the user confirms in the UI; nothing is saved here.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.engine.activities import ACTIVITY_TYPES, DIFFICULTIES
from app.llm.client import LLMClient, LLMUnavailable

log = logging.getLogger(__name__)


class DraftActivity(BaseModel):
    type: str = "city"
    difficulty: str | None = None
    max_altitude_m: float | None = None

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
"activities": [{"type": one of ["city","hiking","trek_multiday","beach","ski","cycling","safari","unknown"],
"difficulty": one of ["easy","moderate","hard","technical","unknown"] or null,
"max_altitude_m": number or null}], "notes": str or null}], "questions": [str]}
Rules:
- "name" is a real place name that a map search can find (a town, park or region), in English.
- Consecutive stops: the next stop starts the day after the previous one ends, unless dates are given.
- If no start date is given, start 30 days after TODAY and add a question asking for the dates.
- If the traveller does not know what they will do, use type "unknown". If a hike's difficulty is unclear, use "unknown".
- Put a famous trek's highest point in max_altitude_m when you know it (e.g. Laugavegur 1100, Tour du Mont Blanc 2665, W Trek 900, Inca Trail 4215).
- Ask at most 3 short questions, only for information that changes what clothes to pack.
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
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
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


def _budget(n_chars: int, max_ctx: int) -> tuple[int, int]:
    """(max_tokens, num_ctx) for a text of n_chars. ~3 chars per token is a safe estimate
    for Italian/Spanish; the system prompt is ~700 tokens."""
    max_tokens = 4096 if n_chars > 3000 else 1500
    need = n_chars // 3 + 900 + max_tokens
    for ctx in (4096, 8192, 16384, 32768, 65536):
        if ctx >= need:
            return max_tokens, min(ctx, max_ctx)
    return max_tokens, max_ctx


def parse_with_llm(text: str, today: date, client: LLMClient | None = None) -> DraftItinerary:
    client = client or LLMClient()
    s = client.s
    max_tokens, num_ctx = _budget(len(text), s.llm_num_ctx_max)
    timeout = max(s.llm_timeout_s, min(s.llm_long_timeout_s, 60 + len(text) / 80))
    data = client.chat_json(SYSTEM, f"TODAY is {today.isoformat()}.\nTrip description:\n{text}",
                            max_tokens=max_tokens, num_ctx=num_ctx, timeout=timeout)
    draft = DraftItinerary(**data)
    draft.parser = "llm"
    return _sanitize(draft, today)


def _sanitize(d: DraftItinerary, today: date) -> DraftItinerary:
    fixed = []
    for s in d.stops[:MAX_STOPS]:
        if s.end_date < s.start_date:
            s.end_date = s.start_date
        if (s.end_date - s.start_date).days > 90:
            s.end_date = s.start_date + timedelta(days=90)
        if not s.activities:
            s.activities = [DraftActivity(type="city")]
        fixed.append(s)
    d.stops = fixed
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
ALT = re.compile(r"(\d{3,4})\s?(?:m|mt|meters|metres|metri)\b", re.I)
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
    for rx, order in ((DMY, "dm"), (MDY, "md")):
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
    alt = ALT.search(seg)
    altitude = float(alt[1]) if alt else None
    difficulty = None
    for word, d in (("technical", "technical"), ("alpine", "technical"), ("hard", "hard"),
                    ("difficult", "hard"), ("difficile", "hard"), ("moderate", "moderate"),
                    ("medium", "moderate"), ("easy", "easy"), ("facile", "easy")):
        if word in s:
            difficulty = d
            break
    unknown = any(w in s for w in ("don't know", "dont know", "not sure", "boh", "non so",
                                   "maybe", "forse", "not decided"))
    if unknown:
        difficulty = "unknown"
    if "multi-day" in s or "multiday" in s or "hut to hut" in s or "rifugi" in s:
        acts.append(DraftActivity(type="trek_multiday", difficulty=difficulty,
                                  max_altitude_m=altitude))
    elif any(w in s for w in ("trek", "hik", "escursion", "camminat", "montagn", "mountain")):
        acts.append(DraftActivity(type="hiking",
                                  difficulty=difficulty or ("unknown" if unknown else "moderate"),
                                  max_altitude_m=altitude))
    if any(w in s for w in ("ski", "snowboard", "sciare", "sci ")):
        acts.append(DraftActivity(type="ski", max_altitude_m=altitude))
    if any(w in s for w in ("beach", "mare", "spiaggia", "coast", "snorkel", "swim")):
        acts.append(DraftActivity(type="beach"))
    if any(w in s for w in ("cycling", "bike", "bici")):
        acts.append(DraftActivity(type="cycling"))
    if "safari" in s:
        acts.append(DraftActivity(type="safari"))
    if any(w in s for w in ("city", "città", "citta", "museum", "sightseeing", "visit")):
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
    heads = list(DAY_HEAD.finditer(text))
    if len(heads) < 3:
        return None
    questions: list[str] = []
    start = _find_date(text, today)
    if start is None:
        start = today + timedelta(days=30)
        questions.append("When do you leave? Dates were not clear, so the draft starts in 30 days.")
    runs: list[list] = []  # [place, first_day, last_day, body]
    for i, h in enumerate(heads):
        body = text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        title = h[2].strip() or body.strip().split("\n", 1)[0]
        # "Lima - Cusco" or "Lima / Cusco": the traveller sleeps at the last place
        parts = [p for p in re.split(r"\s+-\s+|\s*[–—/>→]\s*", title) if p.strip()]
        title = parts[-1] if parts else title
        place = _place(title) or _place(title.title())
        if not place:
            continue
        day = int(h[1])
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
    questions: list[str] = []
    start = _find_date(text, today)
    if start is None:
        start = today + timedelta(days=30)
        questions.append("When do you leave? Dates were not clear, so the draft starts in 30 days.")
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
            questions.append(f"How many days in {place}? The draft assumes 2.")
        seg_start = _find_date(seg, today) or cursor
        end = seg_start + timedelta(days=max(n, 1) - 1)
        stops.append(DraftStop(name=place, start_date=seg_start, end_date=end,
                               activities=_activities(seg)))
        cursor = end + timedelta(days=1)
    for s in stops:
        for a in s.activities:
            if a.type == "hiking" and not a.max_altitude_m:
                questions.append(f"How high does the hike near {s.name} go?")
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
    return _sanitize(parse_with_rules(text, today), today)
