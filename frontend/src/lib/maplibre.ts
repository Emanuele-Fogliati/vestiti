// MapLibre runs its tile decoding in a web worker. The library looks for the worker file next
// to itself, which a bundled app does not have: Vite builds the worker and we point to it.
import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";

maplibregl.setWorkerUrl(workerUrl);

export { maplibregl };
