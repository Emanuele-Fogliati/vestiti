"""Manu's real Peru program (an agency page pasted as is) and a plausible bad model answer."""
from pathlib import Path

PERU = (Path(__file__).parent / "fixtures" / "peru.txt").read_text(encoding="utf-8")


def _s(name, a, b, acts, notes=None):
    return {"name": name, "start_date": f"2026-11-{a:02d}", "end_date": f"2026-11-{b:02d}",
            "activities": acts, "notes": notes}


_HARD = [{"type": "hiking", "difficulty": "hard", "max_altitude_m": 2500}]
_CITY = [{"type": "city"}]
PERU_BAD_LLM = {"trip_name": "Perù", "questions": ["Che tempo farà a Machu Picchu?"], "stops": [
    _s("Lima", 24, 24, _CITY), _s("Cusco", 24, 25, _CITY, "Abbigliamento a strati consigliato"),
    _s("Valle Sacra", 25, 25, _HARD), _s("Machu Picchu", 26, 26, _HARD),
    _s("Aguas Calientes", 26, 27, _CITY),
    _s("Rainbow Mountain", 27, 27, [{"type": "hiking", "difficulty": "moderate", "max_altitude_m": None}]),
    _s("Lago Titicaca", 28, 28, [{"type": "safari"}]), _s("Chivay", 29, 29, _CITY),
    _s("Valle del Colca", 29, 29, _HARD), _s("Arequipa", 30, 30, _CITY),
    _s("Huacachina", 30, 30, [{"type": "beach"}, {"type": "hiking", "difficulty": "hard"}]),
    _s("Paracas", 30, 30, _CITY), _s("Isole Ballestas", 30, 30, _CITY), _s("Lima", 30, 30, _CITY),
]}
