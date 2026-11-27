import { getViewer } from "@/lib/auth/viewer";
import { json } from "@/lib/billing/http";

/**
 * The signed-in user's plan as the server sees it (v2 Phase 8). The checkout success page polls
 * this until the webhook-mirrored subscription arrives; it never grants anything itself.
 */
export async function GET() {
  const v = await getViewer();
  if (!v.user) return json({ signedIn: false, tier: "anonymous" });
  return json({
    signedIn: true,
    emailVerified: v.user.emailVerified,
    tier: v.tier,
    state: v.billing.state,
    trialEnd: v.billing.trialEnd,
    currentPeriodEnd: v.billing.currentPeriodEnd,
    premiumUntil: v.billing.premiumUntil,
    trialEligible: v.billing.trialEligible,
  });
}
