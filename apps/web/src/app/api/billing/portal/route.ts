import { siteUrl } from "@/lib/auth/server";
import { getViewer } from "@/lib/auth/viewer";
import { fromOurSite, json } from "@/lib/billing/http";
import { sqlStore } from "@/lib/billing/store";
import { billingConfig, getStripe } from "@/lib/billing/stripe";
import { logJson } from "@/lib/deploy";

/** Opens the Stripe Customer Portal for the signed-in user's own customer (v2 Phase 8). */
export async function POST(req: Request) {
  if (!fromOurSite(req)) return json({ code: "bad_origin" }, 403);
  let config;
  try {
    config = billingConfig();
  } catch {
    config = null;
  }
  if (!config) return json({ code: "billing_unavailable" }, 503);
  const viewer = await getViewer();
  if (!viewer.user) return json({ code: "signed_out" }, 401);
  const customer = await sqlStore().customerOf(viewer.user.id);
  if (!customer) return json({ code: "no_customer" }, 404);
  try {
    const portal = await getStripe().billingPortal.sessions.create({
      customer: customer.stripeCustomerId,
      return_url: `${siteUrl()}/account`,
      ...(config.portalConfigurationId ? { configuration: config.portalConfigurationId } : {}),
    });
    return json({ url: portal.url });
  } catch (err) {
    logJson("error", "portal session failed", {
      error: err instanceof Error ? err.message : "unknown",
    });
    return json({ code: "stripe_error" }, 502);
  }
}
