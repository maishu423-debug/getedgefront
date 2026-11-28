import type { Metadata } from "next";

import { LegalPage } from "@/components/LegalPage";

export const metadata: Metadata = {
  title: "Refund & Cancellation Policy",
  description: "EdgeFront Premium: free trial, cancelling online at any time, and refunds.",
  alternates: { canonical: "/refund" },
};

export default function RefundPage() {
  return <LegalPage doc="refund" />;
}
