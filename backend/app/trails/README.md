# Trekking trails: how to write one

Manu, 2026-11-13: the app must tell a traveller exactly where to hike, trail by trail, and dress
them for that trail. Countries first: Italy, Argentina, Chile, Peru, Iceland. About 12 trails each,
3-4 new drawings per trail.

`list.json` is the plan: every trail, its **slot** (the helper thread that owns it: `AR-A` … `IT-B`),
its status and the scenes to draw. A helper only touches the trails of its own slot.

## Never copy AllTrails, Komoot, Wikiloc, Outdooractive

Their trails, tracks, photos and texts are proprietary. Use them only to know a trail exists. Facts
come from the park authority, the hut, the tourist board, Wikivoyage or OpenStreetMap. Every trail
lists its `sources`.

## Files

- `data/<cc>/<trail id>.json`: one file per trail, written by hand (schema: `Trail` in `__init__.py`).
- `geo/<trail id>.json`: computed, never by hand: `python tools/trails/build_trails.py <trail id>`.
- Drawings: ordinary landmark scenes of `app/art` (catalog `art/catalog/<cc>.json` + SVG in
  `art/landmarks/<cc>/<slug>.svg`), drawn with the official procedure of `docs/LANDMARK_STYLE.md`
  section 0 ('58 la 17 pulita', 4 sunny reference photos, recompose, permanent snow only,
  MANDATORY critical self-check, separate reviewer). A point links its drawing with `"scene": "<cc>-<slug>"`.

## A trail, field by field

| field | what |
|---|---|
| `id` | `<cc>-<slug>`, as in list.json |
| `name` | the name walkers use, in English, with the local name where it is the known one |
| `base` | the town you sleep in the night before (matches trip stops by name) |
| `kind`, `days` | `day` (days 1) or `multiday` (days ≥ 2) |
| `shape` | `out_and_back` (same way back: write only the way out), `loop`, `one_way` |
| `difficulty` | `easy` / `moderate` / `hard` / `technical` (needs crampons, ropes, a guide, scrambling with exposure). It drives the boots in the kit |
| `glacier` | true when you walk on ice with crampons |
| `months` | best months, 1-12 (the trail open and the weather sane) |
| `hours` | walking time `[low, high]` as the park or a guide publishes it (total for multiday) |
| `start_by` | when to leave, HH:MM |
| `published` | `{km, gain_m, source}`: the round-trip distance and climb the park/hut publishes |
| `why` | one sentence that makes you want to go. No hype words |
| `book` | permits, tickets, compulsory guides, huts to book, how to reach the trailhead |
| `water`, `dangers`, `turnaround` | short, concrete, true. `turnaround` = the rule to turn back (time or place) |
| `osm` | OpenStreetMap hiking relation id of THIS trail, if one exists (find it at hiking.waymarkedtrails.org) |
| `points` | 3-5 key points in walking order: first `role: start`, last `role: goal`; multiday: `night: true` where you sleep. Each has a `note` (what you find there, 1-2 sentences) and later its `scene` |
| `osm_ways` | OSM way ids of the path in walking order, when there is no relation and the router goes wrong |
| `router` | `auto` (default: local router on all OSM paths for compact trails, OSRM for long ones), `local`, `osrm` |
| `via` | `[[lat, lon], …]` extra routing points, only if the router takes a wrong path |

## Coordinates: check every one

Hand-typed coordinates are often 1-3 km wrong, and the routed line then follows roads.
For every point: find it on OpenStreetMap (`python tools/trails/geocode.py <trail id>` lists the
OSM feature with that name and its distance; also look at osm.org). Put the point ON the path
(the viewpoint, the hut, the lake shore where the trail arrives), not in the middle of the lake.

## Build and check

```
python tools/trails/build_trails.py <trail id>
```

It takes the OSM relation when it covers start and goal, else the `osm_ways`, else routes on all
OSM paths of the area through the points (local router: mountain paths included; the public OSRM
foot router skips `sac_scale=mountain_hiking` paths and is only the fallback for long trails),
then reads the altitude (Open-Meteo, Copernicus DEM 90 m).
It prints `!` when a point is more than 0.8 km off the path, or when the distance or climb is more
than 30% off the published numbers (the climb only for day trails with a published climb of 200 m or more: a 90 m DEM is noise on flat walks and misses the small ups of long treks; the page shows the published numbers). **Fix every `!`** (coordinates, `via`, the right relation,
or the published numbers if you used the wrong source) before you mark the trail `checked`.
The tests (`tests/test_trails.py`) fail on the same conditions.

## Scenes

`list.json` scenes = the 3-4 points to draw. `reuse` = an existing scene that may already show the
point: open it; if it really shows that view, set the point's `scene` to it and don't redraw it.
Otherwise draw a new scene named after the point (slug of the point's place, e.g.
`ar-campamento-poincenot`). Never two points of one trail with the same scene. When a trail's
scenes are all done, set its status to `drawn` in list.json.

## Status in list.json

`todo` → `draft` (data file written) → `checked` (coordinates on OSM, geo built, no `!`) → `drawn`.
