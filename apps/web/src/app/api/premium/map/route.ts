import { premiumProxy } from "@/lib/premium/server";

/** Every station: latest 5-minute reading, high/low so far and the METAR values (Premium). */
export async function GET() {
  return premiumProxy("map", "/map");
}
