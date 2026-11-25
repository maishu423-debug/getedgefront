import type { MetadataRoute } from "next";
import { connection } from "next/server";

import { getStations } from "@/lib/api";
import { SITE_URL } from "@/lib/site";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  await connection(); // request time only: the station list comes from the API, never the build
  const res = await getStations();
  const stations = res.ok ? res.data.stations.map((s) => s.id) : [];
  return [
    { url: `${SITE_URL}/`, changeFrequency: "always", priority: 1 },
    ...stations.map((id) => ({
      url: `${SITE_URL}/station/${id}`,
      changeFrequency: "always" as const,
      priority: 0.8,
    })),
    { url: `${SITE_URL}/sources`, changeFrequency: "monthly", priority: 0.4 },
    { url: `${SITE_URL}/pricing`, changeFrequency: "monthly", priority: 0.3 },
  ];
}
