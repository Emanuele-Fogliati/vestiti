# Trekking trails: how to write one

Manu, 2026-11-13: the app must tell a traveller exactly where to hike, trail by trail, and dress
them for that trail. Countries first: Italy, Argentina, Chile, Peru, Iceland. About 12 trails each,
3-4 new drawings per trail. 2026-11-14: + New Zealand, Japan, Vietnam, Namibia, and ~140 more top
treks (tier A) across the 8 trekking countries; slots `<CC>-A` … `<CC>-F`.

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
| `published` | `{km, gain_m, source}`: distance and TOTAL climb of the whole walk (there and back for `out_and_back`) as the park/hut publishes them. Many parks give only the one-way distance and the NET height difference (top minus start): double the distance for a there-and-back, and put `gain_m: null` rather than a net difference (the page then shows our computed climb) |
| `why` | one sentence that makes you want to go. No hype words |
| `book` | permits, tickets, compulsory guides, huts to book, how to reach the trailhead |
| `water`, `dangers`, `turnaround` | short, concrete, true. `turnaround` = the rule to turn back (time or place) |
| `osm` | OpenStreetMap hiking relation id of THIS trail, if one exists (find it at hiking.waymarkedtrails.org) |
| `points` | 3-5 key points in walking order: first `role: start`, last `role: goal`; multiday: `night: true` where you sleep. Each has a `note` (what you find there, 1-2 sentences) and later its `scene` |
| `osm_ways` | OSM way ids of the path in walking order, when there is no relation and the router goes wrong |
| `router` | `auto` (default: local router on all OSM paths for compact trails, OSRM for long ones), `local`, `osrm` |
| `style` | `trek` (default) or `city`: a city walk through famous sights (Manu 2026-11-14: plan the whole trip on foot) |
| `tier` | `A` (default) = a top trek of its country, written by hand, 2-4 drawings. `B` = the long tail, generated into `tail/`: waymarked OSM routes (`tail/<cc>.json`, tools/trails/osm_tail.py), walks from the road to a named peak, pass, hut, lake, waterfall or lookout (`tail/<cc>-goals.json`) DOC New Zealand tracks (`tail/nz-doc.json`), both by tools/trails/goal_walks.py, and city walks through famous sights (`tail/<cc>-city.json`, `style: city`, tools/trails/city_walks.py). Computed numbers; a picture only where a drawing of the goal exists (Manu 2026-11-14: only the famous ones get drawn) |
| `area` | the guide area id of its zone (`ar-el-chalten`), when one exists |
| `scores` | `{effort, nature, culture, relax, history, landscape}`, 0-5 each, all six on every trek, by the zone-ranking rubric. Effort from the hours and climb: 1 = under 2 h and under 200 m, 3 = 5-7 h or 500-900 m, 5 = over 9 h, over 1,200 m, multiday with a pack, or above 4,500 m |
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

## Every trek in the world (`world/`, Manu 2026-11-14)

Outside the 8 trekking countries, every waymarked hiking route of OpenStreetMap that passes the
tier-B rules (named, 4-250 km, no city, park, fitness or cycle loops, no containers) and every
footpath to a named peak, pass, hut, lake or falls (2-25 km), as dots with their numbers and no
drawings. Generated, never edited by hand:

    osmium tags-filter <country>.osm.pbf r/route=hiking,foot -o routes/<country>.pbf   # per extract
    node tools/trails/pbf_paths.js <country>.osm.pbf goals/<country>.json            # walks to goals
    osmium merge routes/*.pbf -o region-routes.pbf                                    # whole cross-border routes
    python tools/trails/pbf_routes.py region-routes.pbf census.json
    python tools/trails/world_tail.py build census.json <region> lon0 lat0 lon1 lat1
    python tools/trails/world_tail.py goals <region> goals/*.json lon0 lat0 lon1 lat1
    python tools/trails/world_tail.py dots
    python tools/trails/iconic.py                                                     # iconic.tsv -> rank 6

Only walks with a real text (Manu 2026-11-16): after any build, `python tools/trails/walk_text.py apply`
puts the English "why" from `tools/trails/walk_text.json` (OSM description, Wikipedia, official page,
DOC NZ; source first in `sources`) and drops the generated walks without one, before `dots`.

`world/<cc>.json` holds a country's treks (the Trail schema) and their geo with the line as an
encoded polyline (`enc`); `world/_dots.json` one row per trek; `world/_iconic.json` the world's
iconic treks (seen from space, drawn later). They are not in `trails()` (hundreds of thousands):
`trails.find()` and `trails.geo()` read them on demand. On the globe a trek's dot shows by the same
zoom ladder as the places (rank 1-6): ranks 4+ come with `/api/trails/dots`, the rest by 10-degree
cell from `/api/trails/dots/cell/{i}/{j}`.

## Walks near every drawn place (Manu 2026-11-15)

The traveller plans the days on foot around the places they already visit, so the long tail grows
around the app's drawings, not everywhere (`tools/trails/near_walks.py`, tier B, generated):

- `tail/<cc>-city.json` outside the 8 countries: city walks through famous sights in every drawn
  city and town (the rules of `city_walks.py`; the sights are Wikidata items, CC0, with 3+ Wikipedia
  languages and a sight class, found around the town; routed on foot by OSRM on OpenStreetMap);
- `tail/<cc>-sights.json`: a short walk to a drawn spot (a falls, a lookout, a monastery on a hill)
  from where the road ends: the foot route from the town is cut where a car can no longer follow
  it; kept when that is 0.5-3.5 km each way and more than a flat stroll from a car park.

## Official trails of the United States and Canada (2026-11-15)

OpenStreetMap is thin there; the park agencies publish their trail lines as open data:
NPS Public Trails and the Forest Service's National Forest System Trails (US public domain),
Parks Canada's Trails APCA (Open Government Licence - Canada). `tools/trails/parks_na.py` joins
each trail's segments, keeps the named ones for walkers (no motor, ski, horse or water trails,
no connectors or spurs), 0.5-250 km, not already an OSM trek of the same name, and adds them to
`world/us.json` and `world/ca.json` (ids `us-nps-...`, `us-usfs-...`, `ca-pc-...`; a short trail
that does not come back is walked there and back). Then `world_tail.py dots`.
