"""What to do first in a zone, for this traveller (Manu, 2026-11-14).

The things to do of an area (app.guide.todo) are written in rank order: the first is the one
not to miss (Laguna de los Tres at El Chaltén). Each also carries six scores, 0 to 5, on a
fixed rubric (docs/RANKING.md): effort, nature, culture, relax, history, landscape. The
traveller answers two questions (what they like, how hard they want it) and the order is
recomputed here, by code, never by the model: same answers, same trip.

- too hard: a thing above the effort the traveller accepts leaves the plan (it stays in
  "more"), and its easier alternative (`alt_of`) takes its place;
- score = 0.6 x how much of what they like it gives + 0.4 x the zone's own rank. The rank keeps
  weight on purpose: who says "culture" at El Chaltén still gets Fitz Roy, because there is no
  culture there and pretending otherwise is worse.
- no answers: the written order, unchanged.
"""
from __future__ import annotations

from typing import Iterable, Literal

from pydantic import BaseModel, Field

Like = Literal["nature", "culture", "history", "relax", "landscape"]
Effort = Literal["easy", "some", "hard"]
LIKES: tuple[str, ...] = ("nature", "culture", "history", "relax", "landscape")
# the most effort each answer accepts (the rubric's 0-5)
CAP = {"easy": 2, "some": 4, "hard": 5}
INTEREST, RANK = 0.6, 0.4
LIKED, OTHER = 2.0, 1.0
NEUTRAL = 0.3  # a thing with no scores yet (a trail of the long tail, a sight near the stop)
# the effort of a thing with no scores, from its label and length
LABEL_EFFORT = {"easy": 1, "moderate": 3, "hard": 4}


class Prefs(BaseModel):
    likes: list[Like] = Field(default_factory=list, max_length=3)
    effort: Effort | None = None

    def empty(self) -> bool:
        return not self.likes and self.effort is None


def effort_of(it) -> int:
    s = getattr(it, "scores", None)
    if s is not None:
        return s.effort
    e = LABEL_EFFORT.get(getattr(it, "effort", "easy"), 1)
    if getattr(it, "length", "short") == "short":
        e = min(e, 2)
    return e


def interest(it, p: Prefs) -> float:
    """0..1: how much of what the traveller likes this thing gives."""
    s = getattr(it, "scores", None)
    if s is None:
        return NEUTRAL
    dims = list(LIKES) + (["effort"] if p.effort == "hard" else [])
    w = {d: (LIKED if d in p.likes or d == "effort" else OTHER) for d in dims}
    return sum(w[d] * getattr(s, d) for d in dims) / (5 * sum(w.values()))


def ordered(items: Iterable, prefs: Prefs | None) -> tuple[list, list]:
    """(the things in the order to do them, the things too hard for this traveller)."""
    items = list(items)
    if prefs is None or prefs.empty():
        return items, []
    cap = CAP[prefs.effort] if prefs.effort else 5
    hard = [it for it in items if effort_of(it) > cap]
    hard_ids = {it.id for it in hard}
    # an easier alternative stands where the thing it replaces stood
    rank = {it.id: i for i, it in enumerate(items)}
    for it in items:
        alt = getattr(it, "alt_of", None)
        if alt in hard_ids and it.id not in hard_ids:
            rank[it.id] = min(rank[it.id], rank[alt])
    n = max(1, len(items))
    keep = [it for it in items if it.id not in hard_ids]

    def score(it) -> float:
        return INTEREST * interest(it, prefs) + RANK * (1 - rank[it.id] / n)

    keep.sort(key=lambda it: (-score(it), rank[it.id]))
    return keep, hard


# ---------------------------------------------------------------- from what the traveller says

WORDS: dict[str, list[str]] = {
    "nature": ["natura", "nature", "naturaleza", "parchi", "parks", "wildlife", "animali", "animals", "fauna"],
    "culture": ["cultura", "culture", "spirituale", "spiritual", "spiritualita", "templi", "temples",
                "cibo", "food", "gastronomia", "local life", "tradizioni", "traditions"],
    "history": ["storia", "history", "historia", "storico", "historic", "rovine", "ruins", "ruinas",
                "archeologia", "archaeology", "musei", "museums"],
    "relax": ["relax", "rilassante", "relaxing", "terme", "hot springs", "spa", "slow", "tranquillo",
              "tranquilla", "calma", "calm", "riposo", "rest"],
    "landscape": ["foto", "fotografia", "photos", "photography", "paesaggi", "paesaggio", "landscapes",
                  "landscape", "panorami", "views", "viewpoints"],
}
EASY = ["facile", "facili", "easy", "senza fatica", "no trekking", "niente trekking", "senza trekking",
        "no hiking", "no hikes", "anziani", "elderly", "bambini", "kids", "children", "spirituale", "spiritual",
        "poco faticoso", "not too hard", "rilassante", "relaxing"]
HARD = ["trekking impegnativi", "trekking duri", "hard treks", "hard hikes", "challenging", "impegnativo",
        "impegnativi", "multi day", "piu giorni di trekking", "tanta fatica", "duro", "tough"]
SOME = ["trekking", "hiking", "escursioni", "camminare", "hike", "hikes", "walks", "camminate", "senderismo"]


def read(text: str) -> Prefs:
    """What a sentence says the traveller likes ("un viaggio spirituale, niente trekking")."""
    from app.guide import _norm
    t = f" {_norm(text)} "

    def has(ws: list[str]) -> bool:
        return any(f" {_norm(w)} " in t for w in ws)

    likes = [k for k in LIKES if has(WORDS[k])][:3]
    effort = "easy" if has(EASY) else "hard" if has(HARD) else "some" if has(SOME) else None
    if effort == "some" and "nature" not in likes and len(likes) < 3:
        likes.append("nature")
    return Prefs(likes=likes, effort=effort)
