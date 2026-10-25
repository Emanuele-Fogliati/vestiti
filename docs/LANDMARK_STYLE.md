# Landmark illustration style

Every stop card shows a small illustration of the place itself: Machu Picchu, the Uros reed
islands, the Colca condor. This guide is the one style all of them follow, whoever draws them.
`python -m app.art.lint` (run from `backend/`) checks the hard rules automatically; the rest is
judged by eye at review.

The official look is **"58, la 17 pulita"**, chosen by Manu on 2026-10-25 after six rounds of
style tests. It is **"Fumetto in carta"**: flat shapes in the real colours of the place, a dark
comic outline, and a soft paper-cut shadow under every shape. Picking it ruled out frames,
panoramas, zoom crops, symbol-only versions, grain, gradients and generic theme colours.

## 1. What you draw and what the app adds

You draw a **flat scene**. The app adds the look on top when it serves the scene
(`backend/app/art/render.py`):

| You draw | The app adds |
|---|---|
| Flat shapes, coloured only with the 10 `--il-*` tokens | The place's **palette**: the real colour of each token |
| A palette file with the real colours of the place | A **1 px outline** in `--il-near` on every filled shape (not the sky) |
| | A **paper drop shadow** under every filled shape (not the sky) |

So **never draw outlines or shadows yourself**, and never write a colour in the SVG. Draw shapes
with fills, set the palette, and preview with the renderer (section 7).

- The scene is an **SVG fragment** (no `<svg>` wrapper) on a **300 × 200** canvas. The app crops
  the edges a little on narrow cards, so keep the landmark inside x 30-270, y 20-185.
- `fill`/`stroke` are only `var(--il-<token>)` or `none`.

## 2. The tokens and the palette

Each place has its own palette: the **real colours** of that place (sand-coloured dunes, a green
Huayna Picchu, ochre Lima cliffs, a grey Lima sky). The same token means the same role everywhere:

| Token | Role | Example (Huacachina) |
|---|---|---|
| `sky` | the sky, always the first shape | `#DDEEF6` pale blue |
| `far` | far terrain, distant land, light details | `#EBCF98` light sand |
| `mid` | the landmark body, middle ground | `#CF9E5C` dune sand |
| `ice` | snow, white walls, foam, highlights | `#FFFFFF` |
| `water` | lakes, sea, rivers | `#3E9C93` green lagoon |
| `near` | the darkest details **and the outline colour** | `#2E3B26` near black |
| `sun` | the sun, plus at most one small warm accent | `#F6C431` |
| `leaf` | vegetation: palms, trees, grass, terraces | `#4F8A3E` |
| `acc` | one local accent: a red lighthouse stripe, red tile roofs, reed boats | `#F1DFA8` |
| `obj` | one local object: a sandboard, a boat, a flag | `#2F7FB5` |

Palette rules (the linter checks the first three):
- All 10 tokens, each written `#RRGGBB` in uppercase.
- `near` stays near black (luminance ≤ 0.1), because it is also the outline.
- `sky` is light (luminance ≥ 0.5). Scenes are by day.
- Colours are **realistic** for the place, not decorative. Take them from what the place really
  looks like. If you are not sure (is the stone grey or ochre?), look it up before choosing.
- `acc` and `obj` are small touches. If the place has no local accent or object, set them to a
  sensible colour and do not use them.

## 3. Content rules (from Manu)

1. **No people.** The only exception is **one small figure that explains the activity** of the
   place: the Lima surfer and paraglider, the Huacachina sandboarder. Never a crowd.
2. **No clouds**, unless clouds or mist are what the place is known for.
3. **Animals are welcome** when they belong to the place (llama, condor, sea lions, penguins).
   Never add one just to fill space.
4. **Never half-cut background shapes.** A mountain partly hidden by a foreground object must still
   read as a whole mountain. The bad example was the old Colca trapezoid behind the condor.
5. **One clear scene** from the postcard viewpoint. No frames, no panoramas, no zoom crops, no
   symbol-only versions.
6. **The sun is always there**: exactly one `<circle fill="var(--il-sun)">`, radius 10-22, in the
   top quarter, away from the landmark's tallest point.

## 4. Recognisable, not generic

The point of the library is that someone who has been there says "that's it". Before drawing,
write down the **2-4 signature features** of the place and draw those, big and with enough detail
to read on their own:

- Lima: the Miraflores cliffs, the red-and-white lighthouse, the towers on top, a paraglider.
- Arequipa: the white sillar cathedral with its two towers, El Misti behind.
- Machu Picchu: Huayna Picchu's sugar-loaf peak, the terraces, the stone houses.
- Uros: the yellow reed boats with the puma head, the reed huts, the lake.

Rules:
- One landmark per scene, seen from its most famous viewpoint.
- Real proportions (number of towers, arches, domes, peaks). Never invent: look it up if unsure.
- No text, no letters, no flags with emblems, no logos, no faces.
- Only real places. Never copy a photo or another illustration: draw from what the place is.
- Cities: the one view that stands for the city (Lima = the Miraflores cliffs and lighthouse,
  Cusco = the cathedral and Inca walls), not a generic skyline.
- Nature: the shape only that place has (the canyon profile, the striped mountain).
- The detail level is the 10 Peru references: usually **20-40 elements, 2-4 KB**.

## 5. Layer order (back to front)

1. `<rect width="300" height="200" fill="var(--il-sky)"/>`, always the very first element.
2. The sun.
3. Far terrain in `far` (horizon roughly y 90-125), with `ice` snow caps if the place has them.
4. The landmark in `mid`, with details in `near`, `ice`, `far`, `leaf`, `acc`.
5. Foreground (y 160-200): ground, water, the animal or the activity figure if any.

`<defs>`/`<clipPath>` may come anywhere after the sky rect.

## 6. Drawing rules

- Elements: `rect circle ellipse path polygon polyline line g defs clipPath`. Nothing else: no
  `text`, `image`, `use`, `filter`, gradients, `style` or `class`.
- Strokes only for thin details (cables, terrace lines, wings, stripes): `stroke-width` 0.5-5,
  `stroke-linecap="round"` for open lines, `fill="none"` on stroked paths. A shape with its own
  `stroke` keeps it and gets no extra outline.
- `opacity`/`fill-opacity` 0.3-1 only for a reflection or a faint far detail.
- `transform` only `translate(x y)` and `scale(k)`; with `scale`, add
  `vector-effect="non-scaling-stroke"` to stroked shapes.
- Integer coordinates where possible; at most one decimal.
- Size: ≤ 6 KB and ≤ 90 elements. Merge shapes of the same colour into one `path` (`M...Z M...Z`).
- Ids are shared by the whole page: any `id` must start with `il-<cc>-<slug>-` (e.g.
  `il-pe-rainbow-mountain-clip`).
- Use at least 4 tokens, always including `near`.

## 7. Names, files, preview

- A place id is `<cc>-<slug>`: ISO 3166 alpha-2 country code in lowercase + a short English ascii
  slug (`pe-machu-picchu`, `is-godafoss`, `ar-iguazu-falls`). One place belongs to one country,
  the one it is physically in. Border places get one entry per side.
- **In a batch:** save two files per place in the batch's `out/` folder, with the exact id the
  batch file gives you:
  - `<cc>-<slug>.svg`: the flat scene;
  - `<cc>-<slug>.palette.json`: `{"sky": "#…", "far": "#…", … all 10 tokens}`.
  Do not rename, and do not add places that are not in your batch.
- **Preview** what the app will show:
  `cd backend && python -m app.art.render out/<cc>-<slug>.svg > /tmp/<cc>-<slug>.preview.svg`
  then open it in a browser or screenshot it with Playwright. Look at it at card size too (about
  180 × 120 px).
- **In the library** (organizer only): `backend/app/art/landmarks/<cc>/<slug>.svg` plus an entry in
  `backend/app/art/catalog/<cc>.json`:
  `{"slug", "label", "lat", "lon", "radius_km", "aliases", "palette"}`.
  - `label`: what the scene shows, in English ("Lima's Costa Verde cliffs").
  - `radius_km`: how far a stop can be and still get this scene (a city 15-30, a single site 5-15,
    a big park or canyon 30-60).
  - `aliases`: lowercase ascii names agencies write for this place (local and Italian spellings).
    Only other names of the **same** place. Each alias belongs to one place.
- A place already in the catalog is never redrawn. `python -m app.art.lint <folder>` flags it.
- The API serves the rendered scene at `/api/art/landmarks/<id>.svg` and the flat drawing at
  `?flat=1`.

## 8. Checklist before handing in

- [ ] `cd backend && python -m app.art.lint <your out/ folder>` prints only `ok`.
- [ ] Rendered preview looked at, full size and at card size: the place is recognisable.
- [ ] 2-4 signature features present, proportions right, nothing invented.
- [ ] Palette = the real colours of the place; `near` near black; light sky.
- [ ] No people except one activity figure; no clouds unless they are the place's trait; animals
      only if they belong; no half-cut background shapes; one clear scene; one sun.
- [ ] No two scenes in the batch look like the same generic mountain.

## 9. Reference scenes

The ten Peru scenes in `backend/app/art/landmarks/pe/` (palettes in `catalog/pe.json`) are the
approved references. Read at least three before drawing. One in full:

### pe-lima-costa-verde (cliffs + lighthouse + towers + paraglider + surfer)

Palette: `{"sky": "#DCE3E8", "far": "#BFC5CA", "mid": "#B9945F", "ice": "#FFFFFF", "water": "#4A88AD", "near": "#26292C", "sun": "#F6C431", "leaf": "#6E9A4E", "acc": "#C63A32", "obj": "#E8833A"}`

```svg
<rect width="300" height="200" fill="var(--il-sky)"/>
<circle cx="40" cy="32" r="12" fill="var(--il-sun)"/>
<path d="M150 92V60H162V92ZM166 92V48H180V92ZM186 92V56H196V92ZM204 86V36H218V86ZM250 80V44H264V80ZM270 78V54H284V78ZM286 76V40H300V76Z" fill="var(--il-far)"/>
<path d="M170 54V88M210 42V82M256 50V76M292 46V72" stroke="var(--il-sky)" stroke-width="2" stroke-dasharray="3 3"/>
<rect y="112" width="300" height="88" fill="var(--il-water)"/>
<path d="M30 114L120 96L200 80L300 66V174L52 122Z" fill="var(--il-mid)"/>
<path d="M70 114L300 82M96 118L300 98M130 124L300 116M170 134L300 134M210 146L300 150" stroke="var(--il-far)" stroke-width="1.2"/>
<path d="M120 100L118 112M160 92L156 116M200 84L194 124M240 78L236 136M276 72L272 150" stroke="var(--il-far)" stroke-width="1" stroke-linecap="round"/>
<path d="M26 113L120 94L200 78L300 63V70L200 84L120 99L30 117Z" fill="var(--il-leaf)"/>
<path d="M52 122L300 174V186L44 126Z" fill="var(--il-near)"/>
<path d="M58 124L300 180" stroke="var(--il-ice)" stroke-width="0.8" stroke-dasharray="4 4"/>
<path d="M44 126L300 186V194L38 130Z" fill="var(--il-far)"/>
<path d="M38 132L300 198M0 150Q20 146 40 150T80 150M10 170Q34 165 58 170T106 170M60 186Q86 181 112 186T164 186" stroke="var(--il-ice)" stroke-width="1.5" fill="none" stroke-linecap="round"/>
<path d="M227 77L231 30H241L245 77Z" fill="var(--il-ice)"/>
<path d="M230.2 40H241.8L242.5 49H229.5ZM228.9 58H243.1L243.8 67H228.2Z" fill="var(--il-acc)"/>
<path d="M226 30H246V26H226Z" fill="var(--il-near)"/>
<rect x="230" y="15" width="12" height="11" fill="var(--il-sun)" stroke="var(--il-near)" stroke-width="1"/>
<path d="M229 15Q236 5 243 15Z" fill="var(--il-acc)"/>
<path d="M236 8V3" stroke="var(--il-near)" stroke-width="1.2"/>
<path d="M262 70Q263 58 260 48M274 68Q274 60 276 52" stroke="var(--il-near)" stroke-width="1.8" fill="none" stroke-linecap="round"/>
<path d="M260 48Q252 46 248 52Q254 48 260 50ZM260 48Q268 44 272 50Q266 47 260 50ZM260 48Q256 40 250 40Q256 43 260 49ZM276 52Q270 49 266 54Q271 51 276 54ZM276 52Q283 48 287 53Q282 51 276 54Z" fill="var(--il-leaf)" stroke="var(--il-leaf)" stroke-width="1"/>
<path d="M86 50Q110 32 134 50Q110 42 86 50Z" fill="var(--il-sun)" stroke="var(--il-near)" stroke-width="1"/>
<path d="M88 50L108 72M132 50L112 72M100 44L109 72M120 44L111 72" stroke="var(--il-near)" stroke-width="0.6"/>
<path d="M107 71H113V77H107Z" fill="var(--il-near)"/>
<path d="M62 166L82 163" stroke="var(--il-near)" stroke-width="2.4" stroke-linecap="round"/>
<path d="M70 163L71 155M71 156L66 159M71 156L76 158" stroke="var(--il-near)" stroke-width="1.6" stroke-linecap="round" fill="none"/>
<circle cx="71" cy="153" r="2" fill="var(--il-near)"/>
```
