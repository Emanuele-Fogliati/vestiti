# Landmark illustration style

Every stop card shows a small illustration of the place itself: Machu Picchu, the Uros reed
islands, the Colca condor. This guide is the one style all of them follow, whoever draws them.
`python -m app.art.lint` (run from `backend/`) checks the hard rules automatically; the rest is
judged by eye at review.

The official look is **"58, la 17 pulita"**, chosen by Manu on 2026-10-25 after six rounds of
style tests. It is **"Fumetto in carta"**: flat shapes in the real colours of the place, a dark
comic outline, and a soft paper-cut shadow under every shape. Picking it ruled out frames,
panoramas, zoom crops, symbol-only versions, grain, gradients and generic theme colours.

## 0. How to make an image: the official procedure (Manu, permanent rule)

Manu wrote and confirmed these six steps on 2026-10-25. They are the procedure for every image,
in this order, none optional (his words, unchanged):

> 1. **Simbolo.** Decido io qual è la vista simbolo del posto, quella che lo fa riconoscere.
> 2. **Foto.** Uso 4 foto con il sole e senza nuvole. La foto 1 è la cartolina, le altre 3 sono
>    da altri punti e da lontano.
> 3. **Forma vera.** Dalla foto 1 prendo le forme del soggetto: profilo, curve, proporzioni.
> 4. **Composizione.** Il soggetto sta grande e al centro, il resto è solo contorno ai lati.
> 5. **Neve.** Solo dove è permanente, attaccata alla roccia.
> 6. **Controllo critico**, dopo averla fatta:
>    - Coprendo il nome, si capisce subito che posto è? Il soggetto è davvero il protagonista?
>    - Il contorno accompagna senza rubare la scena?
>    - Ogni oggetto si capisce cos'è? Se c'è un dubbio, lo tolgo.
>    - È fisicamente sensato, cioè appoggiato a terra e niente che galleggia?
>    - Se qualcosa non va, la rifaccio prima di consegnarla.

In English: (1) **Symbol**: you decide the place's symbol view, the one that makes it
recognisable. (2) **Photos**: 4 photos with sun and no clouds; photo 1 is the postcard, the other
3 from other points of view and from far away. (3) **True shape**: from photo 1 take the
subject's shapes: profile, curves, proportions. (4) **Composition**: the subject large and
centred, the rest only a frame at the sides. (5) **Snow**: only where permanent, attached to the
rock. (6) **Critical check** after drawing: with the name covered, is the place obvious at once,
and is the subject really the protagonist? Does the frame support without stealing the scene? Can
every object be named (if in doubt, remove it)? Is it physically sensible, grounded, nothing
floating? If anything fails, redo it before handing it in.

**Status: FINAL (Manu, 2026-10-26).** Manu approved all 45 calibration images ("tutte
stupende") and fixed this procedure, with the techniques below, as the one used for every
image from now on. The 45 approved scenes in `backend/app/art/landmarks/` are the reference
set: when unsure, look at how they solve the same problem. A blind test of 108 famous places
worldwide (nature, mountains, sea, cities, monuments) checked that Manu recognises each one
without reading its name: he **passed it on 2026-10-26** ("le immagini sono perfette... vanno
tutte bene"), and those 108 joined the library too. Mass production now runs **country by
country, the most-visited places of each country first** (the inventory's trip count), then
the secondary ones, with no further review by Manu: the critical self-check (0.6) is the gate.

Every decision Manu takes is recorded in this guide and dated in section 11.

Manu tuned this procedure on the first set of places (Patagonia, Peru, the showcase). The other
places are drawn **without him reviewing each one**, so every correction he gives becomes a
general rule in this guide. If a scene would make him say "Da rifare", it is not done.

The details of each step:

1. **Symbol: decide it first.** Before searching any photo, decide what makes this place
   recognisable: the view everyone takes, the one on the postcard. Look at several photos (web
   search for the place and "viewpoint", the Wikipedia article, postcards) and pick the framing
   that keeps coming back: Machu Picchu from the Guardhouse above the ruins, terraces in front and
   Huayna Picchu towering behind; Valle de la Luna from the top of the ridge, looking down at the
   saw-tooth salt crests; Fitz Roy from the road into El Chaltén, the skyline of the Patagonia
   logo; Osorno's cone above Lago Llanquihue or the Petrohué river. Then search only for that view.
2. **Photos: exactly 4, sunny, no clouds**, never fewer.
   - **Photo 1 is always the symbol view**, the postcard everybody knows (Torres del Paine = the
     three towers above the lagoon from the Mirador Base). Never swap it for another viewpoint
     just to get a clearer sky: if no cloudless shot of that view exists, take the clearest one
     and crop the clouds out. The drawing follows photo 1.
   - Photos 2-4 show the **same place from other points of view and distances** (not three crops
     of one spot), preferably **from far away**, so you understand the whole place and what is
     around it.
   - **Sun and clear sky, no clouds**, in every photo; mountains preferably in **summer with
     little snow**, so the rock shapes read and you do not invent snow (step 5, 4d).
   - Never a diagram, a map, an old black-and-white photo, a portrait or a crop of a detail.
   - **Any photo from the web is fine** (Google Images, Flickr, Wikimedia, travel sites): pick the
     best one, not the first freely licensed one. Photos are references to look at: they stay in
     the batch folder and are never committed, shipped or traced; the drawing is our own.
   `python tools/art/ref.py <id> "<Wikipedia title>"` saves the article's lead image as
   `refs/<id>-1.jpg`; run it with `--url` (and `--page`) for each other photo. Write in
   `refs/<id>.json` a "took" for each photo (what you used it for) and overall "notes".
3. **True shape: take it from photo 1.** Write down the exact **profile** of every
   mountain and building (section 4c), its **curvature** (a volcano like Osorno has concave
   flanks that sweep out at the foot: it is never a straight-sided triangle), the
   **proportions** (Huayna Picchu is about twice as tall as the ruins are wide; the ruins sit on
   a saddle, below the peak), what is in front, middle and back, and the colours.
4. **Composition: the subject large and centred, the rest a frame that belongs to it**
   ("contorno"). The subject the place is famous for is the main thing in the scene, big and in
   the middle; the framing is yours, so crop and zoom until it is. But the frame is **not a set
   of blocks placed around it** (Manu, 22:14 and 22:32): it is what really stands next to the
   subject, drawn **as it is in reality, connected and in harmony** with it. Seeing the scene,
   you must understand the place.
   - **One photo, one scene.** Draw the whole scene from photo 1, as one landscape. Do not build
     a montage from several photos, above all for a mountain: photos 2-4 only help you read
     shapes and depth.
   - **Everything is connected.** Peaks and spires **grow out of the mass below them** (or out
     of a glacier lying over their foot): the rock continues down into the base, under any snow.
     A white band or a gap must never cut the subject off from what holds it up (Torres del
     Paine and Cerro Torre looked "nel vuoto", just set down on top). Neighbouring mountains
     join the subject's ridge as in reality; slopes run into its base; water meets the shore.
   - **One rock colour, one season.** Neighbouring mountains share the subject's rock colour and
     the same season and snow: never a white massif beside a grey spire.
   - **Near-black mountains are only shadow.** A mountain that is near-black in the photo is in
     shade: draw it in its real rock colour, or leave it out. Never a black block at the side.
   - The **foreground stays small**: a thin strip that helps recognise the place (the road to
     Fitz Roy through the steppe), never generic grass, scree or fields that compete with the
     subject (Fitz Roy had too much green and brown in front).
   - **Water is flat colour. Never waves**, in any style: no wave strokes, squiggles, foam
     scallops, streaks or lines on the water (Manu: "fanno paura"). At most one reflection. A
     waterfall that is the place itself (Iguazú, Gullfoss) is one clean fall shape. If rapids
     seem needed to recognise a place, find another unique element instead.
   Keep the proportions *within* the subject (tower to tower, peak to ruins). Do not trace
   pixels: redraw the shapes you measured, in the official style.
5. **Snow: only where permanent, attached to the rock** (4d), never a loose block, never fresh
   seasonal snow. Then the other content rules (section 3), which win over the photo: remove
   people, cars, clouds and signs.
   **Always ask: which animal lives here?** (Manu, 22:34: "in questi posti gli animali ci sono,
   ricordati"). Where one belongs, add it even if the photos have none: a guanaco at Torres del
   Paine and the Cuernos, a llama at Machu Picchu, sea lions, penguins. Small, unmistakable
   (side view, clear silhouette) and standing on the ground (4b). A bird in flight only where
   it is the place's trait and its silhouette is unmistakable (the condor over Colca or the
   Andes). Leave it out only where no animal makes sense (a city square, a monument).
6. **Critical check, mandatory, after drawing.** Render the scene (`node tools/art/compare.js
   <batch folder>` writes `compare/<id>.png`, the photos next to the scene) and answer honestly:
   - **Cover the name: do I know where I am at first glance?** If the scene could be any
     mountain, lake or city in the world (a cone over a lake could be anywhere), add the
     element only this place has (Osorno: its concave cone with the glacier streaks, the black
     basalt of the Petrohué river at its foot; Fitz Roy: the road through the steppe).
   - **Is the subject really the protagonist?** Large, centred, the first thing the eye sees,
     its profile and curvature as in photo 1.
   - **Is the rest only a frame?** It supports the subject and takes nothing away from it.
   - **Can every object be named?** If in doubt, remove it. Manu's examples from Osorno: purple
     and white lupin spikes that read as little people, a jetty standing in the middle of the
     water, white lines on the water that mean nothing.
   - **Is the typical animal there**, if one belongs to the place (step 5)?
   - **Is everything physically sensible?** Grounded, nothing floating, water falls into
     something (4b).
   If any answer is no, redo the scene before handing it in. Do not hand in and wait for Manu
   to find it.

**Techniques approved with the 45 calibration images (Manu, 2026-10-26).**
- **Waterfalls:** flat white curtain(s), a pale-blue shaded side or lower part, one lumpy spray
  cloud at the foot. No streaks, no foam on the pool. A place with several falls (Iguazú) gets
  separate curtains with rock gaps between them.
- **Activity figure:** allowed only when the place is unrecognisable without it, tiny and
  single: the person climbing out of the hatch holding the lid at Cu Chi, the paraglider at
  Lima.
- **Guano or pale rock:** colour the whole rock pale. Never a white cap on top: it reads as
  snow.
- **Palms and trees:** a palm is a curved trunk with crescent fronds, never a lollipop. A mass
  of trees is one continuous canopy, not a row of separate balls.
- **No sunny photo exists** (a place under dense forest, a place photographed only at dusk):
  complete the scene from the place's known layout and daylight colours, and say so in the refs
  notes.
- **No collage:** a city or site with several famous landmarks gets one view from one photo,
  not a montage of its landmarks (Ho Chi Minh City, Hoi An).
- Photos may be found with the browser (Google Images) as well as by other means (Manu,
  2026-10-26).

**Then hand it in.** Lint and floatcheck (section 8) must print `ok`. A second Claude runs the
same critical check and the checklist (section 8) on the compare sheet and sends the scene back if
anything fails. Finished images go to Manu directly in the drawing thread, each with **the place
name in its title**; there is no separate review tool any more (Manu, 2026-10-25). Each of his
corrections becomes a new rule here.

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
7. **Believable physics: nothing floats.** See section 4b. This is the most common reason a
   scene is rejected.
8. **No rainbows**, unless a rainbow is truly what the place is known for. A waterfall's spray
   is not a reason to add one.

## 4. Recognisable, not generic

The point of the library is that someone who has been there says "that's it". Before drawing,
write down the **2-4 signature features** of the place and draw those, big and with enough detail
to read on their own:

- Lima: the Miraflores cliffs, the red-and-white lighthouse, the towers on top, a paraglider.
- Arequipa: the white sillar cathedral with its two towers, El Misti behind.
- Machu Picchu: Huayna Picchu's sugar-loaf peak, the terraces, the stone houses.
- Uros: the yellow reed boats with the puma head, the reed huts, the lake.

Rules:
- One landmark per scene, seen from its most famous viewpoint. **Cities** may combine their 2-3
  most famous landmarks in one believable street or waterfront view, when one alone would feel
  empty (Ho Chi Minh City: Notre-Dame, the Central Post Office and the Bitexco tower). It must
  still read as one real place, not a collage.
- Real proportions (number of towers, arches, domes, peaks). Never invent: look it up if unsure.
- No text, no letters, no flags with emblems, no logos, no faces.
- Only real places. Never copy a photo or another illustration: draw from what the place is.
- Cities: the one view that stands for the city (Lima = the Miraflores cliffs and lighthouse,
  Cusco = the cathedral and Inca walls), not a generic skyline.
- Nature: the shape only that place has (the canyon profile, the striped mountain).
- The detail level is the 10 Peru references: usually **20-40 elements, 2-4 KB**.

## 4b. Physics: everything stands on something

The paper shadow under every shape makes an object look **lifted** whenever its bottom edge is
visible. So every object must visibly rest on the ground, the water or its support:

- **Ground overlaps the base.** Draw the ground (or water) layer **after** a building, monument,
  tree or rock, so it covers the object's bottom 4-8 px. The base of a building is a straight
  horizontal edge sitting on the ground, never a curved or rounded bottom with ground or road
  visible underneath.
- **Mountains reach the ground.** A mountain or a range continues down to the horizon, the valley
  floor or the waterline: no strip of sky, and no light band (snow, glacier, mist), between the
  mountain and what is in front of it. Peaks rise from a base, they do not hang above a lake.
  The bad example was the first Torres del Paine, whose towers seemed to float over the lake.
- **No gaps between layers.** Each layer touches or overlaps the layer in front of it. A sliver
  of sky colour between two terrain layers reads as a hole.
- **Only things that really fly may float**: the sun, birds in flight, a paraglider, lanterns
  hanging from a visible string. Smoke and steam rise from a visible source.
- **Animals stand, sit, swim or perch** on something visible (a perched bird's branch connects
  to a trunk that reaches the ground), at a believable size for the scene. A bird in flight is allowed only when it is the place's trait (the Colca condor) and
  its silhouette is unmistakable: spread wings, body, head. If an animal is not instantly
  recognisable at card size, leave it out. The bad example was the first Iguazu, with a toucan
  that read as an unknown object in mid-air.
- **Water falls down and flows to a lower level**, it lands in a pool or river, and spray stays
  at the bottom of the fall.
- **Lean, size and perspective are consistent**: one viewpoint per scene, things further away
  are smaller and higher on the canvas, verticals are vertical, and nothing is larger than the
  landmark it stands next to unless it really is.
- **No ambiguous shapes.** If a shape needs explaining, remove it.

**Automatic check:** `node tools/art/floatcheck.js <folder>` renders each scene with a key-coloured
sky and flags any solid shape (at least 20 × 30 px) with sky underneath it. It needs Node and
Playwright. It catches floating mountains and buildings, not everything above, so look at the
render too.

## 4c. Mountains: recognisable by their own profile (Manu, permanent rule)

A famous mountain must be recognisable **from its silhouette alone**, like a skyline. If two
mountain scenes could swap names, both are wrong. Before drawing:

1. Take the real profile from the reference photo (section 0) and write down what only that mountain has:
   the number of summits, their relative heights, the spacing, the shape of each top (needle,
   horn, dome, cone, saw-tooth, flat table), the steepness of each side, the colour bands.
2. Draw that profile with enough points to carry it (a famous peak is usually 15-40 path points,
   not a 4-point triangle), and keep the real proportions between the summits.
3. Add the 1-2 features that finish the identification: the rock colour change, the snow
   pattern, the glacier at the foot, the lake the view is always taken from.
4. Background ranges stay simple and low, so they never compete with the hero profile.

Examples of what makes each one unique:
- **Torres del Paine**: three separate granite towers of similar height, close together, rising
  from a broad grey massif; the classic view is from the base lake.
- **Cerro Torre**: one very thin needle, much taller than its neighbours, slightly leaning, with an
  ice mushroom on top; Torre Egger and Standhardt are lower needles beside it.
- **Cuernos del Paine**: a light granite base with **dark sedimentary caps** (the "horns"),
  a wide jagged crest over Lago Pehoé; the two-colour bands are the signature.
- **Fitz Roy**: the skyline of the Patagonia logo: a massive steep tower with a pointed top,
  a long stepped shoulder, and a row of granite needles on both sides (Poincenot on the left),
  often pink at sunrise.
- **Osorno**: an almost perfect symmetric cone, pointed, with **concave flanks** that sweep out at the foot and a white snow cap; the symbol view is the cone above the Petrohué rapids.
- **Huayna Picchu**: a sugar-loaf peak behind the ruins. **Misti**: a wide cone behind Arequipa.

Reviewers check this explicitly: cover the label and ask "which mountain is it?". If the answer
is "a mountain", it fails.

## 4d. Snow and ice: part of the mountain, never a separate block (Manu)

Manu's finding: drawn snow and ice came out as **loose white blocks that look like flying
glaciers**. So:
- Start from snow-poor summer photos (section 0) and draw the rock first.
- Draw only permanent snow and ice. A snow cap is clipped to the mountain's own outline (the same
  path, or a `clipPath` of it), with a jagged lower edge that follows the gullies. It never has an
  outline of its own that sits beside or above the rock.
- A glacier is a tongue that flows **down a valley between two slopes** and ends on the ground or
  in water. It is wider at the bottom, it touches the rock on both sides and it is never a
  rectangle or a floating slab.
- No white patches in the middle of a slope that do not connect to anything. If in doubt, leave
  the snow out: bare rock is always believable.

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
  `{"slug", "label", "lat", "lon", "radius_km", "aliases", "names", "palette"}`.
  - `label`: what the scene shows, in English ("Lima's Costa Verde cliffs").
  - `radius_km`: how far a stop can be and still get this scene (a city 15-30, a single site 5-15,
    a big park or canyon 30-60).
  - `aliases`: lowercase ascii names agencies write for this place (local and Italian spellings).
    Only other names of the **same** place. Each alias belongs to one place. An alias matches
    anywhere in a stop's name, so it must be the place itself ("eiffel tower", "machu picchu").
  - `names`: names that match only as the **whole** stop name. Use them for a city whose scene is
    one of its monuments ("paris", "lima", "rome"), so "Notre-Dame de Paris" or "Lima Cathedral"
    don't get the Eiffel Tower or the Costa Verde. A stop named after a landmark but more than
    250 km from it is another place and gets nothing (Venice Beach, the Acropolis of Lindos).
- A place already in the catalog is never redrawn. `python -m app.art.lint <folder>` flags it.
- The API serves the rendered scene at `/api/art/landmarks/<id>.svg` and the flat drawing at
  `?flat=1`.

## 8. Checklist before handing in

- [ ] Exactly 4 reference photos: the classic view plus 3 other points of view or distances, clear
      sky, mountains preferably in summer (section 0).
- [ ] Snow and ice only where permanent, attached to the rock, never a loose block (4d).
- [ ] Started from the classic reference photo (section 0); `compare/<id>.png` shows the same
      viewpoint, proportions and skyline.
- [ ] **Critical check done** (section 0, step 6): name covered, the place is recognisable at
      first glance; the subject is the protagonist; every object can be named; nothing floats.
- [ ] Mountain curvature as in photo 1 (a concave volcano is never a straight triangle).
- [ ] No small objects that can be misread (flowers that look like people, posts in water).
- [ ] **Composition:** the subject the place is famous for is large and centred; what stands
      around it is drawn as in reality and never outweighs it (section 0, step 4).
- [ ] **One connected landscape:** peaks grow out of their base (no white band or gap under
      them), the frame touches the subject, the foreground is a thin strip, no wave squiggles
      on water, one rock colour and season, no near-black shadow
      mountains, drawn from photo 1 as one scene (section 0, step 4).
- [ ] `cd backend && python -m app.art.lint <your out/ folder>` prints only `ok`.
- [ ] `node tools/art/floatcheck.js <your out/ folder>` prints only `ok`.
- [ ] Rendered preview looked at, full size and at card size: the place is recognisable.
- [ ] 2-4 signature features present, proportions right, nothing invented.
- [ ] Palette = the real colours of the place; `near` near black; light sky.
- [ ] No people except one activity figure; no clouds and no rainbows unless they are the
      place's trait; the typical animal where one belongs (step 5); no half-cut background shapes; one clear scene;
      one sun.
- [ ] **Physics:** every building, monument, mountain, tree and animal rests on the ground, water
      or a support; no sky or light band under a mountain; no curved bottoms; no gaps between
      layers; water falls down into something.
- [ ] **Mountains:** each famous peak is recognisable from its silhouette alone (4c): label
      covered, a reviewer can name it. No two scenes look like the same generic mountain.

## 9. What Manu rejected (learn from it)

Feedback on the first showcase of the official style (2026-10-25):

| Scene | Problem | Rule |
|---|---|---|
| Torres del Paine | the towers seem to fly over the lake | 4b: mountains reach the ground |
| Colosseum | the building seems to float, and it looked rough | 4b: ground overlaps the base |
| Iguazu Falls | an unreadable animal in mid-air (a toucan) | 4b: animals stand on something and are unmistakable |
| Skógafoss, Iguazu | rainbows added for decoration | 3.8: no rainbows |
| Ho Chi Minh City | only one church, the city feels empty | 4: cities may combine 2-3 landmarks |
| Gullfoss | hard to tell it is Gullfoss | 4: signature features, big and clear |
| Cerro Torre, Torres del Paine, Cuernos | the Patagonia peaks looked alike; Cuernos unreadable | 4c: each mountain by its real profile |
| Colosseum (2nd try) | still not liked | 4: signature features, real proportions |
| Machu Picchu | ruins much wider than the mountain; not the view everyone knows | 0: start from the classic photo, keep its proportions |
| Valle de la Luna | generic dunes instead of the saw-tooth crests seen from above | 0: the classic view |
| Fitz Roy | a row of mountain shapes, not the Patagonia-logo skyline | 0 + 4c: profile from the photo |
| Torres del Paine (round 4) | redrawn from Laguna Amarga to get a clear sky: not the view everyone knows | 0: photo 1 is always the iconic view; crop clouds, never change viewpoint |
| Torres del Paine (round 5) | liked, but the dark Peineta wall took a third of the scene and the towers sat small at the back: the photo's framing copied literally | 0.4: recompose, subject large and centred, side walls a narrow frame |
| Osorno (round 3) | approved earlier, then rejected: straight-sided cone (the real one is concave and pointed), lupins that look like little people, a jetty in the water and white lines nobody understands, "could be any mountain in the world" | 0.3 curvature, 0.5 no misreadable objects, 0.6 critical pass: add what only this place has |
| Torres, Cerro Torre, Fitz Roy, Osorno (2026-10-25 22:14) | towers "nel vuoto", set on top of the base; Fitz Roy's green and brown foreground made the peaks secondary; Osorno's wave squiggles "tremende" | 0.4: subject central but one connected landscape; thin foreground; rapids as foam, no wave strokes |
| Osorno, Cerro Torre (22:32) | waves still on the water ("fanno paura"); Cerro Torre's neighbours unconnected blocks, a black mountain (shadow) and a white massif beside grey spires | 0.4: no waves ever; one photo, one scene; neighbours as in reality, same rock colour and season; near-black = shadow |
| Patagonia redraws (round 2) | snow and ice drawn as blocks that look like flying glaciers; too few photos, cloudy and snowy ones | 0: 4 photos, clear sky, summer, from far away; 4d |

## 10. Reference scenes

The 45 scenes Manu approved on 2026-10-26 (`backend/app/art/landmarks/<cc>/`, palettes in
`catalog/<cc>.json`) are the references: Peru, Argentina, Chile, Iceland, Vietnam and seven
world wonders. Read at least three close to what you are drawing (a waterfall: Gullfoss,
Skógafoss, Iguazú; a city: Buenos Aires, Hanoi; a mountain: Fitz Roy, Torres del Paine) before
you start. Gullfoss is the weakest of the set: do not copy it. One in full:

### pe-lima-costa-verde (cliffs, lighthouse, towers, one paraglider, flat sea)

Palette: `{"sky": "#AFCFF0", "far": "#A68E78", "mid": "#9C7E62", "ice": "#EEEAE2", "water": "#3F8FA0", "near": "#2E2A28", "sun": "#F2C14E", "leaf": "#6E9A4E", "acc": "#F2C230", "obj": "#CDBBA0"}`

```svg
<rect width="300" height="200" fill="var(--il-sky)"/>
<circle cx="262" cy="24" r="10" fill="var(--il-sun)"/>
<path d="M0 200V92H300V200Z" fill="var(--il-water)"/>
<path d="M122 93L132 88Q140 82 150 80L160 79L172 74Q190 72 202 77L210 82Q218 86 226 93Z" fill="var(--il-far)"/>
<path d="M172 74Q190 72 202 77L210 82Q218 86 226 93H196Q198 84 172 74Z" fill="var(--il-near)" opacity="0.3"/>
<path d="M2 90V70H10V90ZM12 90V64H19V90ZM22 90V74H31V90ZM34 90V68H41V90ZM46 90V76H56V90ZM60 90V72H68V90ZM72 90V78H81V90ZM84 90V80H92V90Z" fill="var(--il-ice)"/>
<path d="M4 73H8M4 77H8M4 81H8M4 85H8M14 67H17M14 71H17M14 75H17M14 79H17M14 83H17M14 87H17M24 77H29M24 81H29M24 85H29M36 71H39M36 75H39M36 79H39M36 83H39M36 87H39M48 79H54M48 83H54M48 87H54M62 75H66M62 79H66M62 83H66M62 87H66M74 81H79M74 85H79M86 83H90M86 87H90" stroke="var(--il-near)" stroke-width="0.7" fill="none" stroke-linecap="round" stroke-linejoin="round" opacity="0.3"/>
<path d="M0 200V86Q50 86 100 90Q110 92 112 96Q60 98 30 104Z" fill="var(--il-mid)"/>
<path d="M0 88Q50 84 100 88L104 91Q50 88 0 92Z" fill="var(--il-leaf)"/>
<path d="M112 96L0 100V200H160Q90 184 56 152Q36 126 50 108Q78 99 112 96Z" fill="var(--il-obj)"/>
<path d="M40 108Q30 126 46 150Q76 182 128 200" stroke="var(--il-near)" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round" opacity="0.6"/>
<path d="M0 200V96Q14 104 24 130Q40 168 60 186Q76 196 96 200Z" fill="var(--il-mid)"/>
<path d="M0 96Q14 104 24 130Q40 168 60 186Q76 196 96 200H60Q36 170 18 136Q8 112 0 108Z" fill="var(--il-near)" opacity="0.3"/>
<path d="M176 44Q200 30 226 42L224 47Q200 37 178 49Z" fill="var(--il-acc)"/>
<path d="M178 48L200 66M224 46L202 66M190 41L200 66M212 40L202 66" stroke="var(--il-near)" stroke-width="0.5" fill="none" stroke-linecap="round" stroke-linejoin="round" opacity="0.6"/>
<path d="M199 65H203V71H199Z" fill="var(--il-near)"/>
```

## 11. Decision log (registro decisioni)

Every rule Manu decided, in order. Each new decision is added here **and** written into the
section it changes, in the same commit. Times are UTC.

| Date and time | Decision (Manu) | Where |
|---|---|---|
| 2026-10-25 18:26 | Official style "58, la 17 pulita" ("Fumetto in carta"): flat shapes, real colours per place, comic outline, paper shadow | top, 1, 2 |
| 2026-10-25 | No people (one activity figure at most), no clouds unless they are the trait, animals OK, no half-cut shapes, one clear scene | 3 |
| 2026-10-25 19:12 | Physics: everything rests on something, nothing floats; no rainbows; no ambiguous animals | 4b, 3 |
| 2026-10-25 19:33 | A famous mountain must be recognisable from its own profile | 4c |
| 2026-10-25 19:46 | Always start from the classic reference photo, keep its proportions; add the typical animal even if the photo has none | 0.1, 0.3, 0.5 |
| 2026-10-25 20:42 | Exactly 4 photos, sunny, no clouds, mountains in summer with little snow, from other viewpoints and from far away | 0.2 |
| 2026-10-25 20:42 | Snow and ice only where permanent, attached to the rock, never a "flying glacier" | 4d, 0.5 |
| 2026-10-25 20:46 | Redo all the first 45 places with 4 photos each | - |
| 2026-10-25 21:41 | Photo 1 is always the iconic postcard view; crop clouds, never change viewpoint | 0.2 |
| 2026-10-25 21:56 | Recompose: the subject large and centred; don't copy the photo's framing | 0.4 |
| 2026-10-25 21:56 | Any photo from the web is fine as a reference (never shipped) | 0.2 |
| 2026-10-25 21:58 | The first places only tune the method; Manu won't review every image, so each correction becomes a general rule here | 0 |
| 2026-10-25 22:01 | Copy the subject's curvature (a concave volcano is never a triangle); no small objects that can be misread; mandatory critical check: cover the name, do I know where I am? | 0.3, 0.6 |
| 2026-10-25 22:06 | Review tool retired: finished images go to Manu in the drawing thread with the place name in the title | 0 (hand in) |
| 2026-10-25 22:06 | The six steps (Simbolo, Foto, Forma vera, Composizione, Neve, Controllo critico) are the official procedure, in his words | 0 |
| 2026-10-25 22:14 | Subject central but one connected landscape: peaks grow out of their base, no white band or gap under them; frame attached, not pasted; foreground a thin strip that helps recognise the place | 0.4 |
| 2026-10-25 22:32 | Never waves on water, in any style: water is flat colour (a waterfall that is the place is one clean shape) | 0.4 |
| 2026-10-25 22:32 | One photo, one scene: draw from photo 1, no montage, above all for a mountain; neighbours drawn as in reality, connected and in harmony | 0.4 |
| 2026-10-25 22:32 | One rock colour and one season across the scene; near-black mountains are only shadow: real colour or leave out | 0.4 |
| 2026-10-25 22:34 | Remember animals: always ask which animal lives here and add it where it belongs | 0.5, 0.6 |
| 2026-10-25 22:42 | Every decision is recorded in this guide, with this log | 11 |
| 2026-10-26 07:33 | All 45 calibration images approved ("tutte stupende"); they join the library as the reference set | 0, 10 |
| 2026-10-26 07:33 | Approved techniques: waterfalls (flat curtains, pale shade, one spray cloud), single tiny activity figure only when needed, pale rock fully coloured (no white cap), palms with curved trunk and crescent fronds, one canopy, no-sunny-photo places completed from known layout, no collage | 0 |
| 2026-10-26 07:35 | This procedure is FINAL: use it for every image; browser and Google Images allowed for photos | 0 |
| 2026-10-26 07:35 | Before mass production, a blind test of about 100 famous places worldwide; then production country by country, most-visited places first, then secondary | 0 |
| 2026-10-26 09:55 | Blind test passed: all 108 places recognised ("vanno tutte bene"); start mass production of every place, in many parallel threads | 0 |
