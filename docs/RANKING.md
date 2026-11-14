# What to do in each zone: the ranking (Manu, 2026-11-14)

Every zone (a hand-written area in `backend/app/guide/todo.json` and `areas/<cc>.json`) lists its
things to do **in rank order**: the first is the one not to miss with a single day (Laguna de los
Tres at El Chaltén). Each thing also carries six scores. The planner asks the traveller two
questions (what they like, how hard) and `app.guide.rank` reorders the things by code, never by
the model: same answers, same trip. Treks come from `app/trails` with the same six scores.

## The six scores, 0 to 5

A score says **how much of that thing you get**, not how good it is: Fitz Roy has culture 0.
Levels 2 and 4 sit halfway between the anchors.

| score | 0 | 1 | 3 | 5 |
|---|---|---|---|---|
| effort | sitting: boat, bus, museum | under 2 h on foot and under 200 m of climb | 5-7 h, or 500-900 m of climb, or half a day of kayak | over 9 h, or over 1,200 m of climb, or several days with a pack, or above 4,500 m |
| nature | inside a city | a city park, a seafront | a nature park with a trail, common wildlife | wild nature of world rank (Fitz Roy, Vatnajökull, Sossusvlei) |
| culture (living: people, food, rites, art) | nothing | a village on the way | a market, a quarter, a ceremony | the heart of a living culture (Kyoto's temples, Hoi An) |
| history | nothing | a plaque, a curious fact | a site that matters to the country's history | world history, mostly UNESCO (Machu Picchu, Hiroshima) |
| relax | up at dawn, effort, crowds | busy all day | slow pace, long breaks | hot springs, a beach, no timetable |
| landscape (views, photos) | nothing to photograph | pretty | one of the country's fine views | one of the world's iconic pictures |

Rules:

1. **Effort is measured, not felt**: from the hours and climb the park publishes.
2. **A 5 is explained** in the thing's `why`. The test fails a zone where more than half of the
   things (with at least four scored) have a 5 in the same column.
3. **Difficulty stays a separate label** (`effort` easy / moderate / hard on the thing, and the
   trail's easy / moderate / hard / technical): it picks the boots and filters; the score ranks.
   Whether a thing is a trek is its `kinds`, not a score.

## Other fields of a thing

`tier` A (do it with one day) / B (with 2-3 days) / C (with more) · `kinds` (trek, walk, boat,
city, museum, wildlife, thermal, beach, food, view, drive, night, culture, adventure) · `alt_of`
(the thing it can replace for who wants less effort: Laguna Capri for Laguna de los Tres) ·
`cost` free / $ / $$ / $$$ · `kids` yes / 12+ / no · `needs` car / guide / transfer. Plus what
was there before: length, need (weather), months, book, steps (hour by hour), extras.

Zone: `nights` = [least, ideal, most] and `buffer` = days kept free for the weather from three
days on (El Chaltén: [2, 4, 6], 1).

## How a traveller's order is computed

- Too hard: with "Easy, no treks" the cap is effort 2, "Some walking" 4, "Big treks" 5. A thing
  above the cap leaves the plan (it stays in "more"); its `alt_of` takes its place.
- Then, with w = 2 for what they like (and for effort when they want big treks), 1 for the rest,
  and N the things of the zone:

  score = 0.6 × Σ w·s / (5 Σ w) + 0.4 × (1 − (rank − 1) / N)

  The 40% on the rank is on purpose: who wants culture at El Chaltén still gets Fitz Roy.
- No answer: the written order, unchanged.

## Ready-made trips

`backend/app/guide/trips.json`: per region, trips of about 7, 14 and 21 nights, the zones in
travel order with their nights (`app.guide.ready`). The planner uses one when the length asked is
within 2 days and nothing was kept or dropped. With answers, a zone whose three best things give
less than 0.35 of what the traveller likes drops to its least nights and the nights go to the
zone that gives most, up to its most.

## Writing scores

`python tools/guide/score.py patch.json` merges scores, tiers and new things into the areas,
keeping each file's layout. Sources as for any thing to do: never invented, checked pages only.
