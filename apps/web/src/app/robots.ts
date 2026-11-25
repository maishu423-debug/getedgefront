import type { MetadataRoute } from "next";
import { connection } from "next/server";

import { indexingEnabled } from "@/lib/deploy";
import { SITE_URL } from "@/lib/site";

/** Until the owner's "go live" (INDEXING_ENABLED=true) every crawler is turned away. */
export default async function robots(): Promise<MetadataRoute.Robots> {
  await connection(); // read the switch per request, never at build time
  if (!indexingEnabled()) return { rules: [{ userAgent: "*", disallow: "/" }] };
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/api/"] }],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
