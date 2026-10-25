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
