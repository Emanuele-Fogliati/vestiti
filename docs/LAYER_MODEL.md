# The warmth model (clo)

> **This is an estimate, not a validated physiological model.** It is a heavily reduced
> version of the IREQ approach (ISO 11079), with garment values from published clo tables.
> It has not been checked against real trips yet. It is good for comparing options and
> for spotting obvious gaps, not for safety decisions in the mountains. The app says this
> in the UI (How it works page, model note on every plan).

Code: `backend/app/engine/thermal.py`, `strategy.py`, `fit.py`, `outfit.py`. Pure Python,
no I/O, no AI: same input, same plan.

## 1. Conditions per moment

For every stop, day and activity we build two moments: **moving** and **at rest**.

- Temperature at the activity's highest point: `T = T_station − 6.5 °C × Δh_km`.
  Moving uses a daytime temperature (65 % of the way from the day's min to max); rest
  uses the cold side of the day (early start, evening outdoors, or the night at camp for
  multi-day treks).
- Wind at altitude: `+15 % per 500 m` of climb, capped at 2×.
- Feels-like: NWS / Environment Canada wind chill (only below 10 °C and above 4.8 km/h).
- Activity profiles (`activities.py`): metabolic rate while moving / resting, extra air
  speed (cycling, skiing, safari jeeps), mountain flag, footwear type and ankle support.
  "Don't know yet" = both the easy and the hard version are planned.

| Activity | MET moving | MET rest | Footwear |
|---|---|---|---|
| City | 3.0 | 1.8 | sneaker |
| Easy / moderate hike | 4.0 / 5.0 | 2.0 | trail runner |
| Hard hike | 6.0 | 2.0 | hiking boot, ankle support |
| Technical / alpine | 6.5 | 2.0 | mountaineering boot |
| Multi-day trek | 5.5 | 1.6 | hiking boot |
| Beach | 2.0 | 1.4 | sandal |
| Ski | 6.0 (+6 m/s air) | 1.8 | (rented) |
| Cycling | 7.0 (+5 m/s air) | 2.0 | sneaker |
| Safari | 1.8 (+4 m/s air) | 1.5 | sneaker |

## 2. Required insulation

```
H        = 58.2 × MET × f          f = 0.6 moving, 0.7 at rest   (W/m², heat to shed)
I_total  = (33 − T) / (0.155 × H)                                 (clo)
I_air    = 1 / (0.155 × (8.3 √v + 4.7))                            (still-air layer)
I_req    = I_total − I_air  (+ personal offset ±0.3)
```

Short stops on a hike (not overnight) get 0.8 × I_req: a 10-minute break is not a night
outside.

## 3. Provided insulation

Garments are combined with McCullough's ensemble formula: `0.835 × Σ clo + 0.161`.

Penalties:
- Wind ≥ 18 km/h, no windproof outer layer, T < 15 °C: −15 %.
- Rain, no waterproof outer layer, T < 18 °C: −30 % (−45 % if wearing down).

Status: covered if margin ≥ 0, **marginal** if short by ≤ 0.15 clo (fine for short stops),
**cold** beyond that.

Reference garment values (clo), by warmth level light / medium / warm / very warm:

| Slot | clo |
|---|---|
| Base top | 0.09 / 0.15 / 0.22 / 0.28 |
| Base bottom | 0.08 / 0.12 / 0.16 / 0.20 |
| Fleece / mid | 0.22 / 0.32 / 0.40 / 0.48 |
| Insulated jacket | 0.45 / 0.60 / 0.80 / 1.00 |
| Shell jacket | 0.10 / 0.14 / 0.18 / 0.22 |
| Trousers | 0.06 / 0.20 / 0.26 / 0.32 |
| Shell pants | 0.06 / 0.08 / 0.10 / 0.12 |
| Beanie, gloves, socks, footwear | 0.02–0.08 |

Product feeds rarely publish clo. For feed products we estimate it from the category,
fill type and weight (`catalog/classify.py`) and mark it "estimated".

## 4. From numbers to a layer strategy

1. **Requirements** (pass 1): for every moment we try five presets (T-shirt → full
   winter system) and take the lightest that covers it. Each slot gets the highest level
   any moment needs. Hard rules on top: shell if rain ≥ 30 % or wind ≥ 20 km/h or any
   mountain day; rain trousers only in the mountains (rain ≥ 40 %) or for downpours
   (≥ 60 % and ≥ 10 mm); beanie, gloves and long underwear only if feels-like ≤ 10 °C
   (above 2,500 m they are carried anyway, as a precaution);
   footwear type and ankle support from the hardest activity.
2. **Dressing** (pass 2): with the concrete kit (reference, chosen products or your own
   clothes), each moment starts from base layer, trousers, socks and shoes, adds the shell
   when it rains or blows, then adds the single lightest layer that closes the gap, and
   repeats. That is the "worn" set for that moment.
3. **Statuses per stop**: worn while moving / on at stops / in the pack (carried for a
   precaution: e.g. above 2,000 m always an emergency warm layer) / not needed. Days that
   differ from the usual day are listed as exceptions.
4. **Warmth check and upgrade**: for the worst moment of each stop, if the kit is short,
   we try every single-item swap in the catalog and offer the one with the lowest extra
   cost that closes (or most reduces) the gap.

## 5. Products: stars and tiers

- Fit stars (1–5): weighted score of warmth vs. need, waterproof rating vs. need
  (≥ 10,000 mm when rain is likely), windproofing, breathability for hard efforts,
  weight, footwear type and ankle support, shopper rating. A product that fails a hard
  requirement is capped at 2 stars and never auto-picked.
- Tiers: among products that pass (3+ stars when possible), cheap = the cheapest,
  medium = best fit in the middle price third, premium = best fit in the top price third.
- Your wardrobe: an owned item that passes is used in every tier at zero cost. If it
  falls short, the app says why and what it would cost to fix.
- Rental: suggested when an item is needed on ≤ 50 % of the trip days and renting costs
  < 70 % of buying.

## What would make it better

- Validate on real trips: ask users after the trip "were you cold / hot / fine at stage X".
  That data is the moat, and the way to calibrate the constants above.
- Humidity, solar radiation and sweat accumulation are ignored.
- Sleeping (tents, huts) is out of scope.
