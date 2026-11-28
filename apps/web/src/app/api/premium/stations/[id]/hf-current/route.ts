import registry from "@/generated/stations.json";
import { premiumProxy } from "@/lib/premium/server";

const KNOWN = new Set(registry.stations.map((s) => s.id));

/** Latest 5-minute reading and the 5-minute high/low so far, next to the METAR values. */
export async function GET(
  _req: Request,
  ctx: RouteContext<"/api/premium/stations/[id]/hf-current">,
) {
  const { id } = await ctx.params;
  const sid = id.toUpperCase();
  if (!KNOWN.has(sid)) {
    return Response.json(
      { error: "bad request" },
      { status: 400, headers: { "Cache-Control": "private, no-store" } },
    );
  }
  return premiumProxy("hf-current", `/stations/${sid}/hf-current`);
}
