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


NO_BOAT = re.compile(r"\b(niente|no|senza|non)\s+(barc|batt|traghett|boat|ferr|catamaran|navigaz)|mal di mare|seasick"
                     r"|sin barcos?|pas de bateau|keine boot", re.I)
SLOW = re.compile(r"\b(piano|lent[aoie]|lentamente|tranquill|rilassat|con calma|senza fretta|poco allenat|non allenat"
                  r"|anzian|bambin|slow|easy|gentle|relax|older|kids|not fit|despacio|tranquilo|doucement)", re.I)
BOATY = re.compile(r"\b(boat|catamaran|ferry|barca|battello)\b", re.I)


def wants(wishes: str) -> dict:
    """What the traveller's words rule out for sure, so the code keeps it out even when the model
    does not: no boats, an easy pace."""
    return {"no_boat": bool(NO_BOAT.search(wishes or "")), "slow": bool(SLOW.search(wishes or ""))}


def _fit(items: list[dict], w: dict) -> tuple[list[dict], list[str]]:
    """The day's things for these wishes: boats out (and things that need one marked), hard things
    optional for an easy pace. Returns the things kept and the names left out."""
    kept, out = [], []
    for it in items:
        if w["no_boat"] and it.get("kind") == "boat":
            out.append(it["name"])
            continue
        it = dict(it)
        tips = []
        if w["no_boat"] and BOATY.search(" ".join([it["name"], it.get("hours") or ""]
                                                   + [st["what"] + " " + (st.get("note") or "") for st in it.get("steps") or []])):
            it["optional"] = True
            tips.append("Needs a boat to get there")
        if w["slow"] and it.get("effort") == "hard":
            it["optional"] = True
            tips.append("Hard for an easy pace: only if you feel good")
        it["tips"] = tips
        kept.append(it)
    return kept, out


LENGTH_MIN = {"full": 9 * 60, "half": 4 * 60 + 30, "short": 2 * 60}


def _start_clock(d: dict) -> int | None:
    """Minutes from midnight when the day's things can start: 08:30 on a day at the base, an hour
    after landing or arriving by car on a travel day, none when the arrival time is not known."""
    if not d["legs"]:
        return 8 * 60 + 30
    last = d["legs"][-1]
    arr = last.get("arr") or {"morning": "11:00", "afternoon": "16:00", "evening": "19:00"}.get(last.get("arr_part") or "")
    if not arr or (last.get("arr_date") or d["date"]) != d["date"]:
        return None
    h, m = map(int, arr.split(":"))
    return h * 60 + m + 60


def rules_days(reading: dict, wishes: str = "") -> dict:
    """The draft from facts only: every day with its moves and the guide's things, hour by hour,
    fitted to what the wishes rule out."""
    stops, out = reading["stops"], []
    w = wants(wishes)
    for d in reading["timeline"]:
        rows: list[dict] = []
        for lg in d["legs"]:
            rows += _leg_rows(lg)
        title, prio = "", None
        s = stops[d["stop"]] if d["stop"] is not None else None
        pd = _plan_day(s, d["stop_day"]) if s else None
        left: list[str] = []
        if pd:
            items, left = _fit(pd.get("items") or [], w)
            title = " · ".join(i["name"] for i in items) or ("Free day" if pd["kind"] == "free" or left else "")
            clock = _start_clock(d)
            for it in items:
                eff = EFFORT.get(it.get("effort") or "", "low")
                start = len(rows)
                if it.get("steps"):
                    for st in it["steps"]:
                        rows.append({"at": st["at"], "what": st["what"] + (f": {st['note']}" if st.get("note") else ""),
                                     "effort": eff, "optional": bool(it.get("optional")), "fixed": False})
                else:
                    # no hours in the guide: an approximate start, one thing after the other
                    if clock is not None and not d["legs"] and re.search(r"\b(dawn|alba|sunrise)\b", f"{it['name']} {it.get('hours')}", re.I):
                        clock = 6 * 60
                    at = f"~{clock // 60:02d}:{clock % 60:02d}" if clock is not None and clock < 21 * 60 else None
                    if clock is not None:
                        clock += LENGTH_MIN.get(it.get("length") or "", 120)
                    rows.append({"at": at, "what": it["name"] + (f" ({it['hours']})" if it.get("hours") else ""),
                                 "effort": eff, "optional": bool(it.get("optional")), "fixed": False})
                tips = " ".join((it.get("tips") or []) + (it.get("extras") or [])[:2])
                if tips:  # the guide's advice goes under the first row of the thing, not as a row
                    rows[start]["note"] = tips[:200]
            if pd["kind"] == "day" and items and s.get("kind") != "transit":
                prio = sum(1 for k in range(1, d["stop_day"] + 1)
                           if (_plan_day(s, k) or {}).get("kind") == "day" and _fit((_plan_day(s, k) or {}).get("items") or [], w)[0])
        if left:
            rows.append({"at": None, "what": "Left out for you: " + ", ".join(left), "effort": None,
                         "optional": False, "fixed": False})
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


def _facts_for(reading: dict, idx: list[int], w: dict | None = None) -> dict:
    stops = {reading["timeline"][k]["stop"] for k in idx if reading["timeline"][k]["stop"] is not None}
    facts = []
    for i in sorted(stops):
        s = reading["stops"][i]
        things = [t for d in (s.get("plan") or []) for t in (d.get("items") or [])] + (s.get("more_things") or [])
        things = _fit(things, w or wants(""))[0]
        facts.append({"base": s["name"], "lodging": s.get("lodging"), "address": s.get("address"),
                      "nights": s["days"], "arrive_at": s.get("arrive_at"), "day_trips_from_here": s.get("day_trips"),
                      "between_flights": s.get("transit"),
                      "things": [{k: t.get(k) for k in ("name", "hours", "length", "effort", "need", "book", "steps", "extras",
                                                    "optional", "tips")}
                                 for t in things]})
    return {"bases": facts}


def check(raw: dict, draft_days: list[dict], w: dict | None = None) -> list[dict]:
    """What the model wrote, made safe: only the days asked, good times, every fixed row there,
    and what the wishes rule out kept optional (an easy pace, no boats) whatever the model says."""
    w = w or wants("")
    by_date = {d["date"]: d for d in draft_days}
    got = {d.get("date"): d for d in (raw.get("days") or []) if isinstance(d, dict)}
    out = []
    for date_, draft in by_date.items():
        m = got.get(date_)
        if not m or not isinstance(m.get("rows"), list) or not m["rows"]:
            out.append(draft)
            continue
        rows, seen = [], set()
        for r in m["rows"][:30]:
            if not isinstance(r, dict) or not str(r.get("what") or "").strip():
                continue
            what = str(r["what"]).strip()[:140]
            if what.lower() in seen:
                continue  # the same row twice
            seen.add(what.lower())
            at = _hhmm(str(r.get("at"))) if r.get("at") else None
            eff = r.get("effort") if r.get("effort") in EFFORTS else None
            opt = bool(r.get("optional")) or (w["slow"] and eff == "high") or (w["no_boat"] and bool(BOATY.search(what)))
            rows.append({"at": at, "what": what, "note": str(r.get("note") or "")[:200],
                         "effort": eff, "optional": opt, "fixed": False})
        for f in draft["rows"]:
            if not f["fixed"]:
                continue
            free = [r for r in rows if not r["fixed"]]
            # a timed fact matches a row at its time; one without a time, a row without a time
            same = [r for r in free if (_key(r["at"]) == _key(f["at"]) if f["at"] else not r["at"])]
            like = [r for r in same if _words(f["what"]) & _words(r["what"])
                    or (_nums(f["what"]) and _nums(f["what"]) == _nums(r["what"]))]
            hit = like[0] if like else same[0] if f["at"] and len(same) == 1 else None
            if hit is None:
                rows.append(dict(f))  # the model lost it, or moved it: the fact goes back as written
                continue
            # the model kept it in its own words: it stays a fact (time, overnight arrival, the bed last)
            hit.update({"fixed": True, "at": f["at"] or hit["at"], "effort": f["effort"], "optional": False,
                        **{k: True for k in ("next_day", "sleep") if f.get(k)}})
        # a move the model wrote again at a wrong time (the fact is already there): out
        facts = [r for r in rows if r["fixed"]]
        rows = [r for r in rows if r["fixed"] or not MOVE.search(r["what"])
                or not any(len(_words(r["what"]) & _words(f["what"])) >= 2 for f in facts)]
        # the effort the model left out: the guide's, for the row at the same time
        guide = {_key(r["at"]): r["effort"] for r in draft["rows"] if not r["fixed"] and r["at"] and r["effort"]}
        for r in rows:
            if not r["fixed"] and r["effort"] is None and r["at"]:
                r["effort"] = guide.get(_key(r["at"]))
        prio = m.get("priority")
        out.append({"date": date_, "title": str(m.get("title") or draft["title"])[:90],
                    "priority": prio if isinstance(prio, int) and 0 < prio < 10 else draft["priority"],
                    "rows": _sorted(rows)})
    return out


MOVE = re.compile(r"\b(volo|flight|vuelo|vol|flug|drive|guida|in auto|on the road|transfer|taxi|bus)\b", re.I)


def _nums(s: str) -> list[str]:
    return re.findall(r"\d+", s)


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-zà-ÿ]{5,}", s.lower())}


def ai_days(reading: dict, group: int, wishes: str = "", lang: str = "English",
            client: LLMClient | None = None) -> dict:
    """One group of days written by the model, checked; the draft when no model answers."""
    draft = rules_days(reading, wishes)
    gs = groups(reading)
    if not 0 <= group < len(gs):
        raise ValueError("no such group")
    idx = gs[group]
    mine = [draft["days"][k] for k in idx]
    weather = [w for w in draft["weather"] if any(w["drop"] == d["date"] for d in mine)]
    client = client or LLMClient()
    user = ("WISHES: " + (wishes.strip()[:1500] or "none") + "\n\nFACTS:\n"
            + json.dumps(_facts_for(reading, idx, wants(wishes)), ensure_ascii=False, default=str)[:24000]
            + "\n\nDRAFT (fixed rows have \"fixed\": true):\n"
            + json.dumps([{**d, "weekday": date.fromisoformat(d["date"]).strftime("%A")} for d in mine],
                         ensure_ascii=False)[:16000]
            + f"\n\nWrite these {len(mine)} days: {', '.join(d['date'] for d in mine)}."
            + f" Write every title, row, note and the weather rule in {lang}, even where the traveller writes in another language: translate their places' descriptions, keep proper names."
            + (f" Follow the WISHES: leave out or mark optional what they rule out, lighten the days for them."
               if wishes.strip() else ""))
    try:
        raw = client.chat_json(SYSTEM.format(lang=lang), user, max_tokens=6000,
                               num_ctx=16384, timeout=client.s.llm_long_timeout_s)
        days = check(raw, mine, wants(wishes))
        w = raw.get("weather") if isinstance(raw.get("weather"), dict) else None
        if w and w.get("drop") in {d["date"] for d in mine}:
            area = next((x["area"] for x in weather), "") or next(
                (reading["stops"][reading["timeline"][k]["stop"]]["name"] for k in idx
                 if reading["timeline"][k]["stop"] is not None
                 and reading["stops"][reading["timeline"][k]["stop"]].get("kind") != "transit"), "")
            weather = [{"area": area, "drop": w["drop"], "how": str(w.get("how") or "")[:300]}]
        return {"group": group, "groups": len(gs), "days": days, "weather": weather,
                "source": "llm", "model": client.s.llm_model}
    except (LLMUnavailable, ValueError, KeyError, TypeError) as e:  # json errors are ValueError
        return {"group": group, "groups": len(gs), "days": mine, "weather": weather, "source": "rules",
                "model": None, "why": str(e)[:200]}
