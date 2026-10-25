from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, own_trip, rate_limit
from app.llm import assistant
from app.llm.client import LLMClient
from app.llm.itinerary import parse_itinerary
from app.models import Trip, User
from app.schemas import AskIn, ExplainIn, ParseIn
from app.services.planner import Planner
from app.weather import geocode

router = APIRouter(prefix="/api", tags=["ai"])
ai_limit = rate_limit("ai", "ai_rate_limit_per_minute")


@router.get("/ai/status")
def ai_status():
    return LLMClient().status()


@router.post("/ai/parse-itinerary", dependencies=[Depends(ai_limit)])
def parse(body: ParseIn, user: User = Depends(current_user)):
    """Free text -> draft stops with map matches. Nothing is saved: the UI confirms."""
    draft = parse_itinerary(body.text, today=date.today())
    stops = []
    for s in draft.stops:
        matches = geocode.search(s.name, limit=3)
        place = dict(matches[0]) if matches else None
        if place and s.elevation_m:
            # the program says where you sleep and how high ("Quota 3827 mt"): nights at
            # altitude are what makes the warm layers necessary
            place["elevation_m"] = s.elevation_m
        stops.append({**s.model_dump(mode="json"), "matches": matches, "place": place})
    return {"trip_name": draft.trip_name, "stops": stops, "questions": draft.questions,
            "parser": draft.parser}


def _facts(strategy: dict, stage_index: int | None, slot: str | None) -> tuple[dict, str]:
    stages = strategy.get("stages", [])
    st = next((s for s in stages if s["index"] == stage_index), stages[0] if stages else None)
    if st is None:
        return {}, "Add a stop first."
    facts = {"stage": st["name"], "dates": [st["start"], st["end"]], "notes": st["notes"],
             "moving": {k: st["modes"]["moving"][k] for k in ("required", "provided", "status")},
             "at_rest": {k: st["modes"]["rest"][k] for k in ("required", "provided", "status")},
             "coldest_moment": st["modes"]["rest"]["condition"], "model_note": strategy["model_note"]}
    fallback = " ".join(st["notes"])
    if slot and slot in st["slots"]:
        facts["layer"] = {"slot": slot, **st["slots"][slot],
                          "item": strategy["kit"].get(slot, {}).get("name")}
        fallback = st["slots"][slot]["why"]
    return facts, fallback


@router.post("/trips/{trip_id}/explain", dependencies=[Depends(ai_limit)])
def explain(body: ExplainIn, trip: Trip = Depends(own_trip), user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    strat = Planner(db, user, trip).strategy(body.tier if body.tier in ("cheap", "medium", "premium") else "medium")
    if strat.get("empty"):
        return {"text": strat["message"], "source": "rules", "model": None}
    facts, fallback = _facts(strat, body.stage_index, body.slot)
    return assistant.explain(body.topic, facts, fallback)


@router.post("/trips/{trip_id}/ask", dependencies=[Depends(ai_limit)])
def ask(body: AskIn, trip: Trip = Depends(own_trip), user: User = Depends(current_user),
        db: Session = Depends(get_db)):
    p = Planner(db, user, trip)
    strat = p.strategy(body.tier if body.tier in ("cheap", "medium", "premium") else "medium")
    if strat.get("empty"):
        return {"text": strat["message"], "source": "rules", "model": None}
    facts = {
        "trip": trip.name,
        "stages": [{"name": s["name"], "dates": [s["start"], s["end"]],
                    "activities": s["activities"], "notes": s["notes"],
                    "layers": {k: {"status": v["status"], "why": v["why"]} for k, v in s["slots"].items()},
                    "exceptions": [e["summary"] for e in s["exceptions"]]}
                   for s in strat["stages"]],
        "kit": {k: v["name"] for k, v in strat["kit"].items()},
        "totals": strat["totals"],
        "model_note": strat["model_note"],
    }
    return assistant.ask(body.question, facts)
