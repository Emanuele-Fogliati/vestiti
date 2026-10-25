"""The traveller profile: quiz before the plan, chat that updates it, and the plan diff."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, own_trip, rate_limit
from app.llm import assistant
from app.llm.profile_chat import read_message
from app.models import Trip, User
from app.schemas import ChatIn, QuizIn
from app.services import profile as P
from app.services.planner import Planner

router = APIRouter(prefix="/api", tags=["profile"])
ai_limit = rate_limit("ai", "ai_rate_limit_per_minute")


def _tier(t: str | None) -> str:
    return t if t in ("cheap", "medium", "premium") else "medium"


def _plans(db: Session, user: User, trip: Trip | None) -> dict | None:
    if trip is None or not trip.stops:
        return None
    return P.plan_snapshot(Planner(db, user, trip).plans())


@router.get("/me/profile")
def get_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return P.profile_json(db, user)


@router.post("/me/quiz")
def quiz(body: QuizIn, trip_id: str | None = None, tier: str = "medium",
         user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Save the quiz answers (any can be skipped). With trip_id, also say what changed in
    that trip's kit."""
    trip = None
    if trip_id:
        trip = db.get(Trip, trip_id)
        if trip is None or trip.user_id != user.id:
            raise HTTPException(404, "Trip not found")
    before = _plans(db, user, trip)
    changes, undo = P.apply_quiz(db, user, body.cold, body.pace, body.evenings, body.owned)
    db.commit()
    db.refresh(user)
    after = _plans(db, user, trip)
    added = [w for w in P.user_wardrobe(db, user) if w.id in undo["wardrobe_ids"]]
    return {"profile": P.profile_json(db, user), "changes": changes, "undo": undo,
            "plan": P.plan_diff(before, after, _tier(tier), added)}


@router.post("/trips/{trip_id}/chat", dependencies=[Depends(ai_limit)])
def chat(body: ChatIn, trip: Trip = Depends(own_trip), user: User = Depends(current_user),
         db: Session = Depends(get_db)):
    """'I'm always cold', 'I have an old Decathlon fleece': update the profile and wardrobe,
    recompute the kit, and show what changed. Anything else is answered as a question."""
    tier = _tier(body.tier)
    up, reader = read_message(body.message)
    if up.empty():
        strat = Planner(db, user, trip).strategy(tier)
        if strat.get("empty"):
            return {"kind": "answer", "text": strat["message"], "source": "rules", "reader": reader}
        ans = assistant.ask(body.message, _ask_facts(trip, strat))
        return {"kind": "answer", "text": ans["text"], "source": ans["source"], "reader": reader}
    before = _plans(db, user, trip)
    changes, undo = P.apply_updates(db, user, up)
    db.commit()
    db.refresh(user)
    after = _plans(db, user, trip)
    added = [w for w in P.user_wardrobe(db, user) if w.id in undo["wardrobe_ids"]]
    diff = P.plan_diff(before, after, tier, added)
    text = P.summary(diff, bool(changes))
    return {"kind": "update", "text": text, "changes": changes, "plan": diff, "undo": undo,
            "profile": P.profile_json(db, user), "reader": reader}


def _ask_facts(trip: Trip, strat: dict) -> dict:
    return {
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
