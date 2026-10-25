# Landmark illustration style

Every stop card shows a small flat illustration of the place itself: Machu Picchu, the Uros reed
islands, the Colca condors. This guide is the one style all of them follow, whoever draws them.
`python -m app.art.lint` (run from `backend/`) checks the hard rules automatically; the rest is
judged by eye at review.

## 1. What a scene is

- A **fragment of SVG** (no `<svg>` wrapper) drawn on a **300 × 200** canvas. The app wraps it in
  `<svg viewBox="0 0 300 200" preserveAspectRatio="xMidYMid slice">`, so anything outside the
  canvas is cropped and the edges may be cut a little on narrow cards: keep the landmark inside
  x 30-270, y 20-185.
- **Flat shapes, no outlines by default.** Depth comes from the layer colours, not from strokes,
  gradients or shadows.
- **Colours are theme tokens only.** The app has three themes and each one recolours every scene,
  so a scene never names a colour. Allowed: `fill`/`stroke` = `var(--il-<token>)` or `none`.

| Token | Role | Yellow/black theme |
|---|---|---|
| `--il-sky` | sky background, always the first shape | light grey |
| `--il-far` | far mountains, distant land, light details on dark shapes | grey |
| `--il-mid` | the landmark body, middle ground terrain, buildings | dark grey |
| `--il-ice` | snow caps, white walls, highlights, foam | white |
| `--il-water` | lakes, sea, rivers, glass | blue grey |
| `--il-near` | the darkest accents: doors, windows, people, boats, birds, foreground silhouettes | near black |
| `--il-sun` | the sun, plus at most one small accent (reed boats, a flag, lit windows) | yellow |

## 2. Layer order (back to front)

1. `<rect width="300" height="200" fill="var(--il-sky)"/>`, always the very first element.
2. The sun: exactly one `<circle fill="var(--il-sun)">`, radius 10-22, in the top quarter, on the
   side away from the landmark's tallest point.
3. Far terrain in `--il-far` (horizon line roughly y 90-125), with `--il-ice` snow caps if the
   place has snowy peaks.
4. The landmark in `--il-mid`, with details in `--il-near`, `--il-ice` and `--il-far`.
5. Foreground in `--il-mid`/`--il-near`: ground, water, one local touch (a llama, a reed boat, a
   condor, a tuk-tuk). The foreground band is y 160-200.

`<defs>`/`<clipPath>` may come anywhere after the sky rect.

## 3. Recognisable, not generic

The point of the library is that someone who has been there says "that's it". Before drawing,
write down the **2-3 signature features** of the place and draw only those, big:

- Machu Picchu: Huayna Picchu's sugar-loaf peak behind, the terraces, the little stone houses.
- Uros: the yellow reed boats with the puma head, the reed huts, the lake.
- Colca: the steep canyon walls with terraces, the condor with white neck and wing bands.

Rules:
- One landmark per scene, seen from its most famous viewpoint (the postcard angle).
- Proportions of the real thing (number of towers, arches, domes, peaks). Never invent: if you are
  not sure how many towers the cathedral has, look it up before drawing.
- No text, no letters, no flags with emblems, no logos, no people's faces. Small people as
  silhouettes are fine.
- Only real places. Never copy a photo or another illustration: draw from what the place is.
- Cities: draw the single monument that stands for the city (Cusco = the cathedral and Inca
  walls), not a generic skyline.
- Nature: draw the shape that only that place has (the canyon profile, the striped mountain).

## 4. Drawing rules

- Elements: `rect circle ellipse path polygon polyline line g defs clipPath`. Nothing else: no
  `text`, `image`, `use`, `filter`, gradients, `style` or `class`.
- Strokes only for thin details (cables, ropes, terrace lines, birds' wings): `stroke-width`
  0.8-5, `stroke-linecap="round"` for open lines, `fill="none"` on stroked paths.
- Integer coordinates where possible; at most one decimal.
- `transform` only as `translate(x y)`.
- Size: ≤ 6 KB and ≤ 90 elements. Most good scenes are 1.3-2.5 KB and 15-25 elements. Merge
  shapes of the same colour into one `path` (`M...Z M...Z`).
- Ids are shared by the whole page: any `id` must start with `il-<cc>-<slug>-` (e.g.
  `il-pe-rainbow-mountain-clip`).
- Use at least 4 tokens, always including `--il-near`. Yellow (`--il-sun`) covers at most about a
  tenth of the canvas: it is the accent, not the fill.

## 5. Names, files, catalog

- A place id is `<cc>-<slug>`: ISO 3166 alpha-2 country code in lowercase + a short English slug
  (`pe-machu-picchu`, `it-colosseum`, `jp-fushimi-inari`). One place belongs to one country, the
  one it is physically in, whatever the trip title says.
- In a batch thread: save each scene as `<cc>-<slug>.svg` in the batch's `out/` folder, with the
  exact id the batch file gives you. Do not rename, do not add places that are not in your batch.
- In the library (organizer only): `backend/app/art/landmarks/<cc>/<slug>.svg` plus an entry in
  `backend/app/art/catalog/<cc>.json`:
  `{"slug", "label", "lat", "lon", "radius_km", "aliases"}`.
  - `label`: what the scene shows, in English ("Cusco Cathedral and Inca walls").
  - `radius_km`: how far a stop can be and still get this scene (a city 15-30, a single site 5-15,
    a big park or canyon 30-60).
  - `aliases`: lowercase ascii names that agencies write in a stop's name, including local and
    Italian spellings and the sub-places that should show this scene (`cuzco`, `qosqo`). Each
    alias belongs to one place only.
- A place already in the catalog is never redrawn. `python -m app.art.lint <folder>` flags it.

## 6. Checklist before handing in

- [ ] `cd backend && python -m app.art.lint <your out/ folder>` prints only `ok`.
- [ ] Rendered preview looked at in at least the yellow/black theme (see below): the landmark reads
      at card size (about 180 × 120 px).
- [ ] 2-3 signature features present, proportions right, nothing invented.
- [ ] Sun on the opposite side of the tallest point, horizon in the same band as the references.
- [ ] No two scenes in the batch look like the same generic mountain.

Preview: wrap the fragment in `<svg viewBox="0 0 300 200">`, add the token values for a theme
(`frontend/src/theme/tokens.css`), open it in a browser or render it with Playwright.

## 7. Reference scenes

The ten Peru scenes in `backend/app/art/landmarks/pe/` are the approved references. Three of them
in full:

### pe-machu-picchu (mountain + ruins + terraces + llama)

```svg
<rect width="300" height="200" fill="var(--il-sky)"/>
<circle cx="48" cy="38" r="13" fill="var(--il-sun)"/>
<path d="M0 116L30 86L60 104L96 70L130 100L160 90L300 96V200H0Z" fill="var(--il-far)"/>
<path d="M232 200L236 84L246 62L262 76L280 112L300 124V200Z" fill="var(--il-far)"/>
<path d="M118 200L128 128Q136 112 146 120L156 134L166 92Q176 48 200 42Q220 40 228 70Q236 104 246 128L262 200Z" fill="var(--il-mid)"/>
<path d="M190 50Q200 44 208 48M180 70Q192 64 202 70M216 64Q224 64 228 74" stroke="var(--il-far)" stroke-width="1.4" fill="none"/>
<path d="M0 200V150L70 144L150 146L230 142L300 146V200Z" fill="var(--il-far)"/>
<path d="M96 146V136L104 128L112 136V140H136V146ZM150 146V138H186V130L194 122L202 130V138H222V146ZM240 144V134L248 126L256 134V144Z" fill="var(--il-ice)"/>
<path d="M102 142L103 137H107L108 142ZM120 144L121 141H125L126 144ZM158 144L159 140H163L164 144ZM172 144L173 140H177L178 144ZM192 136L193 131H197L198 136ZM210 144L211 140H215L216 144ZM246 140L247 135H251L252 140Z" fill="var(--il-near)"/>
<path d="M0 200V156H58V162H76V170H92V178H106V188H118V200Z" fill="var(--il-mid)"/>
<path d="M0 156H58M58 162H76M76 170H92M92 178H106M106 188H118" stroke="var(--il-ice)" stroke-width="2"/>
<path d="M0 166H62M0 176H80M0 186H98M0 196H112" stroke="var(--il-far)" stroke-width="1.2"/>
<path d="M226 176Q226 168 236 168H254Q262 168 262 176Q262 182 256 182H232Q226 182 226 176Z" fill="var(--il-near)"/>
<path d="M252 172L254 146H261L259 172Z" fill="var(--il-near)"/>
<path d="M253 147Q257 140 265 142L272 147Q270 151 264 151H254Z" fill="var(--il-near)"/>
<path d="M256 143L255 136L259 142ZM260 142L261 135L263 142Z" fill="var(--il-near)"/>
<path d="M230 180V196M237 180V196M250 180V196M257 180V196" stroke="var(--il-near)" stroke-width="3"/>
<path d="M227 172Q221 172 222 179" stroke="var(--il-near)" stroke-width="3" fill="none"/>
```

### pe-uros-titicaca (water + reed boats + yellow accent)

```svg
<rect width="300" height="200" fill="var(--il-sky)"/>
<circle cx="250" cy="36" r="13" fill="var(--il-sun)"/>
<path d="M0 112L30 100L56 106L90 82L104 92L124 74L150 98L190 92L220 104L300 98V122H0Z" fill="var(--il-far)"/>
<path d="M90 82L98 90L94 92L86 88ZM124 74L134 84L128 86L118 82Z" fill="var(--il-ice)"/>
<rect y="120" width="300" height="80" fill="var(--il-water)"/>
<path d="M150 140H292L298 148H144Z" fill="var(--il-sun)"/>
<path d="M150 140H292" stroke="var(--il-near)" stroke-width="1.4"/>
<path d="M166 140L182 112L198 140ZM206 140L224 106L242 140ZM252 140L266 116L280 140Z" fill="var(--il-sun)" stroke="var(--il-near)" stroke-width="1.4" stroke-linejoin="round"/>
<path d="M182 112V140M174 126L190 126M224 106V140M214 124L234 124M266 116V140M259 128L273 128" stroke="var(--il-near)" stroke-width="1"/>
<path d="M178 140V130H186V140ZM220 140V128H228V140ZM262 140V131H270V140Z" fill="var(--il-near)"/>
<path d="M238 140V96" stroke="var(--il-near)" stroke-width="1.6"/>
<path d="M238 96L252 101L238 106Z" fill="var(--il-near)"/>
<path d="M28 166Q20 146 32 132Q34 148 46 156H134Q148 148 150 130Q166 148 152 168Q92 180 28 166Z" fill="var(--il-sun)" stroke="var(--il-near)" stroke-width="1.6" stroke-linejoin="round"/>
<path d="M48 156Q46 146 56 144H124Q132 146 130 156" fill="var(--il-sun)" stroke="var(--il-near)" stroke-width="1.6"/>
<path d="M44 158V168M60 156V172M78 156V173M96 156V173M114 156V172M132 157V170M70 146V156M90 145V156M110 146V156" stroke="var(--il-near)" stroke-width="1.4"/>
<path d="M150 130Q148 120 156 118L162 122L158 126Q154 126 154 132Z" fill="var(--il-near)"/>
<path d="M156 119L158 114L160 120Z" fill="var(--il-near)"/>
<path d="M32 132Q28 124 22 124L20 128L26 129Q28 132 28 138Z" fill="var(--il-near)"/>
<path d="M40 182H140M70 190H170M190 172H260M210 182H290" stroke="var(--il-ice)" stroke-width="1.5" stroke-linecap="round"/>
```

### pe-colca-canyon (canyon walls + condor)

```svg
<rect width="300" height="200" fill="var(--il-sky)"/>
<circle cx="250" cy="34" r="12" fill="var(--il-sun)"/>
<path d="M100 104L150 70L162 74L176 66L220 104Z" fill="var(--il-far)"/>
<path d="M150 70L162 74L176 66L186 76L170 82L158 78L142 80Z" fill="var(--il-ice)"/>
<path d="M162 62Q156 50 164 42Q172 34 166 24" stroke="var(--il-far)" stroke-width="5" stroke-linecap="round" fill="none"/>
<path d="M0 200V92L36 96L72 118L104 160L124 200Z" fill="var(--il-mid)"/>
<path d="M300 200V86L262 94L222 122L196 164L184 200Z" fill="var(--il-mid)"/>
<path d="M0 108L30 112M0 124L50 128M0 140L66 146M0 156L80 164M0 172L92 180M300 104L260 110M300 120L240 128M300 136L226 146M300 152L212 164M300 168L202 180" stroke="var(--il-far)" stroke-width="1.6"/>
<path d="M124 200L120 186Q150 176 186 186L184 200Z" fill="var(--il-far)"/>
<path d="M128 200Q150 188 176 200Z" fill="var(--il-water)"/>
<path d="M150 74L120 60Q96 54 66 60L58 56L62 63L52 62L58 68L48 69L58 74Q100 80 146 82Z" fill="var(--il-near)"/>
<path d="M150 74L180 60Q204 54 234 60L242 56L238 63L248 62L242 68L252 69L242 74Q200 80 154 82Z" fill="var(--il-near)"/>
<path d="M118 66Q96 62 72 66M182 66Q204 62 228 66" stroke="var(--il-ice)" stroke-width="3" stroke-linecap="round" fill="none"/>
<path d="M142 72Q150 64 158 72L156 88L150 96L144 88Z" fill="var(--il-near)"/>
<path d="M144 72Q150 68 156 72" stroke="var(--il-ice)" stroke-width="3" fill="none"/>
<circle cx="150" cy="66" r="4" fill="var(--il-mid)"/>
```
