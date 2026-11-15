import { lazy, Suspense } from "react";
import type { RouteMapOpts, RouteStop } from "./RouteMap";
import type { GlobeFocus } from "./Globe";
import type { TrailCard } from "../lib/types";
import "../theme/maps.css";

// The map library is big: it loads only on pages that show a map, after the page itself.
const GlobeImpl = lazy(() => import("./Globe"));
const RouteMapImpl = lazy(() => import("./RouteMap"));
const TrekMapImpl = lazy(() => import("./TrekMap"));

export function HomeGlobe(props: { bare?: boolean; intro?: boolean; onReady?: () => void; mode?: "trip" | "trek"; focus?: GlobeFocus[] }) {
  return <Suspense fallback={<section className="globe globe-loading" aria-hidden="true" />}><GlobeImpl {...props} /></Suspense>;
}

export function TripMap(props: { stops: RouteStop[]; focusIndex?: number | null } & RouteMapOpts) {
  return <Suspense fallback={<div className="rmap rmap-loading" aria-hidden="true" />}><RouteMapImpl {...props} /></Suspense>;
}

export function TreksMap(props: { trails: TrailCard[]; selected: string | null; onPick: (id: string) => void;
  inset?: { top: number; right: number; bottom: number; left: number }; fitKey: string }) {
  return <Suspense fallback={<div className="rmap rmap-loading" aria-hidden="true" />}><TrekMapImpl {...props} /></Suspense>;
}
