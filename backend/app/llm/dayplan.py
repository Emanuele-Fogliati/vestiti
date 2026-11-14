"""The days of a booked trip, hour by hour (Manu, 2026-11-14: "deve essere collegato con un AI che
in base a cosa vuole fare l'utente o alle sue esigenze ti crea il viaggio ad hoc").

Two layers, so that the AI never decides a fact:
1. rules_days(): a draft from facts only. The moves read from the traveller's text (flights, car,
   borders, times) and the hand-written guide's things with their hours, effort and order.
2. ai_days(): the model rewrites one base at a time around those facts, in the traveller's
   language and for what they asked ("we are slow walkers", "no boat"): practical rows (check-in,
   fuel, supermarket, meals), effort per row, optional things, the order of priority and what to
   drop when the weather turns. It may only use places from the facts. Then check(): bad times
   dropped, every move of the text put back if the model lost or moved it.

Without a model (or when it fails) the draft is the answer: the page always gets a plan.
"""
from __future__ import annotations

import json
import re
from datetime import date

from app.llm.client import LLMClient, LLMUnavailable

EFFORT = {"easy": "low", "moderate": "medium", "hard": "high"}
EFFORTS = {"zero", "low", "medium", "high"}
AT = re.compile(r"^~?([01]?\d|2[0-3])[:.]([0-5]\d)(?:\s*[-–]\s*([01]?\d|2[0-3])[:.]([0-5]\d))?$")


def _hhmm(t: str | None) -> str | None:
    m = AT.match((t or "").strip())
    if not m:
        return None
    out = f"{int(m.group(1)):02d}:{m.group(2)}"
    if m.group(3):
        out += f"–{int(m.group(3)):02d}:{m.group(4)}"
    return ("~" + out) if t.strip().startswith("~") else out


def _key(t: str | None) -> str:
    """Sort key of a row's time: rows without one go where they were."""
    m = re.search(r"(\d{1,2})[:.](\d{2})", t or "")
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else ""


def _leg_rows(leg: dict) -> list[dict]:
    """A move as rows: leaving, the notes on the way, arriving."""
    at = lambda name, ap: f"{name} ({ap})" if name and ap and ap != name else (ap or name or "")  # noqa: E731
    mode = {"flight": "Flight", "car": "Drive"}.get(leg["mode"], (leg["mode"] or "Transfer").capitalize())
    what = f"{mode} {at(leg['from'], leg['from_airport'])} → {at(leg['to'], leg['to_airport'])}"
    if leg.get("flight"):
        what = f"{mode} {leg['flight']} {at(leg['from'], leg['from_airport'])} → {at(leg['to'], leg['to_airport'])}"
    if leg["via"]:
        what += f", via {', '.join(leg['via'])}"
    rows = []
    pickup = [n for n in leg["notes"] if n.startswith("Pick up")]
    leave = [n for n in leg["notes"] if n.startswith("Leave at")]
    for n in leave:
        rows.append({"at": n.removeprefix("Leave at ").strip(), "what": "Leave for the airport", "effort": None,
                     "optional": False, "fixed": True})
    for n in pickup:
        rows.append({"at": leg["dep"], "what": n, "effort": None, "optional": False, "fixed": True})
    rows.append({"at": leg["dep"], "what": what, "effort": None, "optional": False, "fixed": True})
    for s in leg["stops"]:
        rows.append({"at": None, "what": f"Stop at {s['name']}" + (f" ({s['when']})" if s.get("when") else ""),
                     "effort": "low", "optional": False, "fixed": True})
    for n in leg["notes"]:
        if n in pickup or n in leave:
            continue
        m = re.search(r"\b(?:by|at) (\d{2}:\d{2})", n)
        rows.append({"at": m.group(1) if m else None, "what": n, "effort": None, "optional": False, "fixed": True})
    if leg["arr"] or leg.get("arr_part"):
        nxt = leg.get("arr_date") and leg["arr_date"] != leg["date"]
        rows.append({"at": leg["arr"], "what": f"Arrive in {at(leg['to'], leg['to_airport'])}"
                     + (" (next day)" if nxt else "") + ("" if leg["arr"] else f", {leg['arr_part']}"),
                     "effort": None, "optional": False, "fixed": True, **({"next_day": True} if nxt else {})})
    return rows


def _plan_day(stop: dict, n: int) -> dict | None:
    plan = stop.get("plan") or []
    return plan[n - 1] if 0 < n <= len(plan) else None


def rules_days(reading: dict) -> dict:
    """The draft from facts only: every day with its moves and the guide's things, hour by hour."""
    stops, out = reading["stops"], []
    for d in reading["timeline"]:
        rows: list[dict] = []
        for lg in d["legs"]:
            rows += _leg_rows(lg)
        title, prio = "", None
        s = stops[d["stop"]] if d["stop"] is not None else None
        pd = _plan_day(s, d["stop_day"]) if s else None
        if pd:
            items = pd.get("items") or []
            title = " · ".join(i["name"] for i in items) or ("Free day" if pd["kind"] == "free" else "")
            for it in items:
                eff = EFFORT.get(it.get("effort") or "", "low")
                start = len(rows)
                if it.get("steps"):
                    for st in it["steps"]:
                        rows.append({"at": st["at"], "what": st["what"] + (f": {st['note']}" if st.get("note") else ""),
                                     "effort": eff, "optional": False, "fixed": False})
                else:
                    rows.append({"at": None, "what": it["name"] + (f" ({it['hours']})" if it.get("hours") else ""),
                                 "effort": eff, "optional": False, "fixed": False})
                tips = " ".join((it.get("extras") or [])[:2])
                if tips:  # the guide's advice goes under the first row of the thing, not as a row
                    rows[start]["note"] = tips[:200]
            if pd["kind"] == "day" and items and s.get("kind") != "transit":
                prio = sum(1 for k in range(1, d["stop_day"] + 1)
                           if (_plan_day(s, k) or {}).get("kind") == "day" and (_plan_day(s, k) or {}).get("items"))
        if d["sleep"] and not d["sleep"].get("in_the_air"):
            rows.append({"at": None, "what": f"Sleep: {d['sleep'].get('name') or d['sleep']['town']}"
                         + (f", {d['sleep']['address']}" if d['sleep'].get("address") else ""),
                         "effort": None, "optional": False, "fixed": True, "sleep": True})
        out.append({"date": d["date"], "title": title or _travel_title(d), "priority": prio, "rows": _sorted(rows)})
    return {"days": out, "weather": _weather_rules(reading, out), "source": "rules", "model": None}


def _travel_title(d: dict) -> str:
    if not d["legs"]:
        return ""
    lg = d["legs"][-1]
    return f"To {lg['to']}" if lg.get("to") else "Travel day"


def _sorted(rows: list[dict]) -> list[dict]:
    """By time; a row without one stays after the row before it (and sleep goes last)."""
    last = ""
    keyed = []
    for i, r in enumerate(rows):
        k = _key(r["at"]) or last
        last = k
        last_k = "99" if r.get("sleep") else "98" if r.get("next_day") else k
        keyed.append((last_k, i, r))
    return [r for _, _, r in sorted(keyed, key=lambda x: (x[0], x[1]))]


def _weather_rules(reading: dict, days: list[dict]) -> list[dict]:
    rules = []
    for i, s in enumerate(reading["stops"]):
        if s.get("kind") == "transit":
            continue
        mine = [d for d, t in zip(days, reading["timeline"]) if t["stop"] == i and d["priority"]]
        if len(mine) < 2:
            continue
        last = max(mine, key=lambda d: d["priority"])
        rules.append({"area": s["name"], "drop": last["date"],
                      "how": f"Bad day: rest, then do each day one day later; {last['title']} is the one to drop."})
    return rules


SYSTEM = """You are a meticulous local trip planner. You write the days of a trip that is already booked,
hour by hour, in {lang}. Output JSON only.

Hard rules:
- FIXED rows (flights, drives, car pick-up and return, borders, sleep) are facts from the traveller.
  Keep every one with its time; you may translate it, never change times, places or order.
- Use ONLY places and activities listed in FACTS or DRAFT. Never invent a place, a trail, a price,
  a flight number or an opening time. Practical rows are welcome without a source: check-in,
  immigration, fuel, cash, supermarket, packed lunch, meals, rest, early night, packing.
- Times are realistic: driving times between the base and each activity, daylight, the arrival
  time on travel days (landing at 18:40 means an evening in town only).
- Effort per row: "zero" (look, short walk), "low", "medium", "high" (steep, long); null for logistics.
- Mark as optional what is extra ("optional": true).
- priority: 1 = the day not to miss at this base, 2 next, ...; null on travel days.
- weather: what to drop first if a day is lost to bad weather and how to shift.
- Respect what the traveller asked for in WISHES (pace, fitness, interests) when choosing and ordering.
- Short rows: max 120 characters in "what"; add detail in "note" (max 160) only when useful.

JSON shape:
{{"days":[{{"date":"YYYY-MM-DD","title":"...","priority":1,"rows":[{{"at":"07:15","what":"...","note":"","effort":"medium","optional":false}}]}}],
 "weather":{{"drop":"YYYY-MM-DD","how":"..."}}}}"""


LANGS = {"Italian": {"il", "che", "di", "per", "con", "una", "sono", "dormo", "giorno", "volo", "alle", "poi", "notti"},
         "Spanish": {"el", "que", "de", "para", "con", "una", "los", "las", "vuelo", "noches", "luego", "día"},
         "French": {"le", "que", "de", "pour", "avec", "une", "les", "vol", "nuits", "puis", "jour"},
         "German": {"der", "die", "und", "mit", "für", "ein", "eine", "flug", "nächte", "dann", "tag"}}


def lang_of(text: str) -> str:
    """The language the traveller writes in, by its common words; English when unsure."""
    words = re.findall(r"[a-zà-ÿ]+", text.lower())[:3000]
    best, n = "English", sum(w in {"the", "and", "then", "with", "flight", "nights", "day", "we", "to"} for w in words)
    for lang, common in LANGS.items():
        k = sum(w in common for w in words)
        if k > n:
            best, n = lang, k
    return best


def groups(reading: dict) -> list[list[int]]:
    """Days in groups of one base each (the days before the first base go with it, the days
    after the last base with the last): one model call per group keeps every call small."""
    tl = reading["timeline"]
    out: list[list[int]] = []
    cur: int | None = None
    for k, d in enumerate(tl):
        s = d["stop"]
        if s is None or (cur is not None and reading["stops"][s].get("kind") == "transit"):
            s = cur
        if not out or (s is not None and s != cur and cur is not None):
            out.append([])
        if s is not None:
            cur = s
        out[-1].append(k)
    return out


def _facts_for(reading: dict, idx: list[int]) -> dict:
    stops = {reading["timeline"][k]["stop"] for k in idx if reading["timeline"][k]["stop"] is not None}
    facts = []
    for i in sorted(stops):
        s = reading["stops"][i]
        things = [t for d in (s.get("plan") or []) for t in (d.get("items") or [])] + (s.get("more_things") or [])
        facts.append({"base": s["name"], "lodging": s.get("lodging"), "address": s.get("address"),
                      "nights": s["days"], "arrive_at": s.get("arrive_at"), "day_trips_from_here": s.get("day_trips"),
                      "between_flights": s.get("transit"),
                      "things": [{k: t.get(k) for k in ("name", "hours", "length", "effort", "need", "book", "steps", "extras")}
                                 for t in things]})
    return {"bases": facts}


def check(raw: dict, draft_days: list[dict]) -> list[dict]:
    """What the model wrote, made safe: only the days asked, good times, every fixed row there."""
    by_date = {d["date"]: d for d in draft_days}
    got = {d.get("date"): d for d in (raw.get("days") or []) if isinstance(d, dict)}
    out = []
    for date_, draft in by_date.items():
        m = got.get(date_)
        if not m or not isinstance(m.get("rows"), list) or not m["rows"]:
            out.append(draft)
            continue
        rows = []
        for r in m["rows"][:30]:
            if not isinstance(r, dict) or not str(r.get("what") or "").strip():
                continue
            at = _hhmm(str(r.get("at"))) if r.get("at") else None
            eff = r.get("effort") if r.get("effort") in EFFORTS else None
            rows.append({"at": at, "what": str(r["what"]).strip()[:140], "note": str(r.get("note") or "")[:200],
                         "effort": eff, "optional": bool(r.get("optional")), "fixed": False})
        times = {_key(r["at"]) for r in rows if r["at"]}
        for f in draft["rows"]:
            if not f["fixed"]:
                continue
            if f["at"] and _key(f["at"]) in times:
                continue  # the model kept it (in its own words) at its time
            if not f["at"] and any(_words(f["what"]) & _words(r["what"]) for r in rows):
                continue
            rows.append(dict(f))
        prio = m.get("priority")
        out.append({"date": date_, "title": str(m.get("title") or draft["title"])[:90],
                    "priority": prio if isinstance(prio, int) and 0 < prio < 10 else draft["priority"],
                    "rows": _sorted(rows)})
    return out


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-zà-ÿ]{5,}", s.lower())}


def ai_days(reading: dict, group: int, wishes: str = "", lang: str = "English",
            client: LLMClient | None = None) -> dict:
    """One group of days written by the model, checked; the draft when no model answers."""
    draft = rules_days(reading)
    gs = groups(reading)
    if not 0 <= group < len(gs):
        raise ValueError("no such group")
    idx = gs[group]
    mine = [draft["days"][k] for k in idx]
    weather = [w for w in draft["weather"] if any(w["drop"] == d["date"] for d in mine)]
    client = client or LLMClient()
    user = ("WISHES: " + (wishes.strip()[:1500] or "none") + "\n\nFACTS:\n"
            + json.dumps(_facts_for(reading, idx), ensure_ascii=False, default=str)[:24000]
            + "\n\nDRAFT (fixed rows have \"fixed\": true):\n"
            + json.dumps([{**d, "weekday": date.fromisoformat(d["date"]).strftime("%A")} for d in mine],
                         ensure_ascii=False)[:16000]
            + f"\n\nWrite these {len(mine)} days: {', '.join(d['date'] for d in mine)}.")
    try:
        raw = client.chat_json(SYSTEM.format(lang=lang), user, max_tokens=6000,
                               num_ctx=16384, timeout=client.s.llm_long_timeout_s)
        days = check(raw, mine)
        w = raw.get("weather") if isinstance(raw.get("weather"), dict) else None
        if w and w.get("drop") in {d["date"] for d in mine}:
            weather = [{"area": "", "drop": w["drop"], "how": str(w.get("how") or "")[:300]}]
        return {"group": group, "groups": len(gs), "days": days, "weather": weather,
                "source": "llm", "model": client.s.llm_model}
    except (LLMUnavailable, ValueError, KeyError, TypeError) as e:  # json errors are ValueError
        return {"group": group, "groups": len(gs), "days": mine, "weather": weather, "source": "rules",
                "model": None, "why": str(e)[:200]}
