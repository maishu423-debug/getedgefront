import registry from "@/generated/stations.json";
import { premiumProxy } from "@/lib/premium/server";

const KNOWN = new Set(registry.stations.map((s) => s.id));

/** 5-minute readings for the last 6 or 24 hours (Premium only; v2 Phase 10 B1). */
export async function GET(req: Request, ctx: RouteContext<"/api/premium/stations/[id]/hf">) {
  const { id } = await ctx.params;
  const sid = id.toUpperCase();
  const hours = new URL(req.url).searchParams.get("hours") ?? "6";
  if (!KNOWN.has(sid) || (hours !== "6" && hours !== "24")) {
    return Response.json(
      { error: "bad request" },
      { status: 400, headers: { "Cache-Control": "private, no-store" } },
    );
  }
  return premiumProxy("hf", `/stations/${sid}/hf?hours=${hours}`);
}
