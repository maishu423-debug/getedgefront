"use client";

import dynamic from "next/dynamic";

import { usePremiumTier } from "@/lib/premium/client";

import { MapSkeleton } from "./MapSkeleton";
import { MapTeaser } from "./MapTeaser";

/**
 * /map (v2 Phase 10 B5). The page HTML is the same for everyone and holds no data. Free and
 * signed-out visitors get the teaser; MapLibre, the street map and /api/premium/map are only
 * loaded (this dynamic import) once the server-computed session says Premium.
 */
const LiveMap = dynamic(() => import("./LiveMap").then((m) => m.LiveMap), {
  ssr: false,
  loading: () => <MapSkeleton />,
});

export function MapPage() {
  const { pending, premium } = usePremiumTier();
  if (pending) return <MapSkeleton />;
  return premium ? <LiveMap /> : <MapTeaser />;
}
