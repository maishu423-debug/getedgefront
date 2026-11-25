import type { Metadata } from "next";

import { DraftPage } from "@/components/DraftPage";

export const metadata: Metadata = {
  title: "Terms and data licences (draft)",
  robots: { index: false },
};

export default function TermsPage() {
  return <DraftPage title="Terms and data licences" />;
}
