# Stop illustrations

Every stop card shows a picture of the place. The app looks for one in this order:

1. **Hand-drawn landmark** (`backend/app/art/`). These are flat SVG scenes on a 300x200 canvas, drawn with the
   `--il-*` colour tokens only, so they follow the theme. A stop gets one when the stop name contains one of the
   landmark's aliases, or else when the stop lies within the landmark's `radius_km`. If two stops in a trip would get the
   same landmark, the second one switches to a different landmark named in its notes (for example, a second Cusco stop
   whose notes mention the Rainbow Mountain).
2. **Model-made picture** (table `place_art`). FLUX.1-schnell, run through ComfyUI, draws the place once in the
   same flat poster style. The image is stored, then mapped onto the theme's palette each time it is served.
3. **Generic terrain scene** (`frontend/src/components/Illustration.tsx`). This is always the fallback, and it is
   also what the card shows while 1 or 2 is loading.

## Adding a hand-drawn landmark

1. Draw the scene in `backend/app/art/landmarks/<id>.svg`. Use only `fill`/`stroke="var(--il-…)"`, with no
   `<script>` and no links. Look at the other scenes for the style: a sky, a small sun, a few flat layers and one
   recognisable subject.
2. Add `<id>` to `backend/app/art/catalog.json` with its label, coordinates, radius and aliases. Write the aliases
   in lower case and without accents.
3. Run `pytest tests/test_art.py`, which checks the tokens and the matching.

## Image model on your PC (RTX GPU)

1. Install ComfyUI. On Windows, use the portable NVIDIA build from
   https://github.com/comfyanonymous/ComfyUI/releases. An RTX 50xx needs the build that bundles PyTorch for
   CUDA 12.8 or newer.
2. Put `flux1-schnell-fp8.safetensors` (from https://huggingface.co/Comfy-Org/flux1-schnell, licence
   Apache-2.0) in `ComfyUI/models/checkpoints/`.
3. Start ComfyUI with `run_nvidia_gpu.bat`. It listens on `127.0.0.1:8188`.
4. Add `ART_IMAGE_ENABLED=true` to `.env` and run `docker compose up -d`. The app reaches ComfyUI at
   `http://host.docker.internal:8188`.

Once a trip is open, a stop that has no landmark asks the server for a picture. The server works out what to draw
(the local LLM picks the place's best-known sight) and sends it to ComfyUI on a background thread. The card switches
from the generic scene to the picture when it's ready, in a few seconds once the model is loaded. Every later trip that
visits the same place (same name, country and coordinates within about 10 km) reuses that picture.

If you don't like a picture, run `docker compose exec app python -m app.cli art-forget --name "Reykjavik"`. The
picture is drawn again the next time a trip with that stop is opened.

## Production (no GPU)

Keep `ART_IMAGE_ENABLED=false`. Production then serves only pictures that are already in the database:

```bash
# on the PC with the GPU
docker compose exec app python -m app.cli art-pregen --file app/art/popular.txt
docker compose exec app python -m app.cli art-export --dir /tmp/art && docker compose cp app:/tmp/art ./art-export
# on the server
python -m app.cli art-import --dir art-export
```

`app/art/popular.txt` lists the destinations to draw in advance. A place that is not in it gets the generic scene in
production until you pre-draw it. If you want new places drawn on demand in production, you can point
`ART_IMAGE_URL` at a hosted ComfyUI or Flux endpoint; each picture is drawn once and cached, so it costs a fraction of
a cent.
