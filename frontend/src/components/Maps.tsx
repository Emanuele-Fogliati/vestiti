import { lazy, Suspense } from "react";
import type { RouteStop } from "./RouteMap";
import "../theme/maps.css";

// The map library is big: it loads only on pages that show a map, after the page itself.
const GlobeImpl = lazy(() => import("./Globe"));
const RouteMapImpl = lazy(() => import("./RouteMap"));

export function HomeGlobe() {
  return <Suspense fallback={<section className="globe globe-loading" aria-hidden="true" />}><GlobeImpl /></Suspense>;
}

export function TripMap({ stops }: { stops: RouteStop[] }) {
  return <Suspense fallback={<div className="rmap rmap-loading" aria-hidden="true" />}><RouteMapImpl stops={stops} /></Suspense>;
}
