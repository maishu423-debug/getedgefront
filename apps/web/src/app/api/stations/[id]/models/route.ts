import { proxyGet } from "@/lib/proxy";

const VARS = new Set(["temp", "dewpt", "wind", "cloud", "rh"]);
const SPANS = new Set(["today", "48h"]);

export async function GET(req: Request, ctx: RouteContext<"/api/stations/[id]/models">) {
  const { id } = await ctx.params;
  const q = new URL(req.url).searchParams;
  const v = q.get("var") ?? "temp";
  const span = q.get("span") ?? "today";
  if (!/^[A-Za-z][A-Za-z0-9]{3}$/.test(id) || !VARS.has(v) || !SPANS.has(span)) {
    return Response.json({ error: "bad request" }, { status: 400 });
  }
  return proxyGet(`/stations/${id.toUpperCase()}/models?var=${v}&span=${span}`);
}
