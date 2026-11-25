import { proxyGet } from "@/lib/proxy";

export async function GET(_req: Request, ctx: RouteContext<"/api/stations/[id]/current">) {
  const { id } = await ctx.params;
  if (!/^[A-Za-z][A-Za-z0-9]{3}$/.test(id)) {
    return Response.json({ error: "bad station id" }, { status: 400 });
  }
  return proxyGet(`/stations/${id.toUpperCase()}/current`);
}
