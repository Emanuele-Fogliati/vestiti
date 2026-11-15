import { lazy, Suspense } from "react";
import type { RouteStop } from "./RouteMap";
import type { GlobeFocus } from "./Globe";
import "../theme/maps.css";

// The map library is big: it loads only on pages that show a map, after the page itself.
const GlobeImpl = lazy(() => import("./Globe"));
const RouteMapImpl = lazy(() => import("./RouteMap"));

export function HomeGlobe(props: { bare?: boolean; intro?: boolean; onReady?: () => void; mode?: "trip" | "trek"; focus?: GlobeFocus[] }) {
  return <Suspense fallback={<section className="globe globe-loading" aria-hidden="true" />}><GlobeImpl {...props} /></Suspense>;
}

export function TripMap({ stops, focusIndex }: { stops: RouteStop[]; focusIndex?: number | null }) {
  return <Suspense fallback={<div className="rmap rmap-loading" aria-hidden="true" />}><RouteMapImpl stops={stops} focusIndex={focusIndex} /></Suspense>;
}
