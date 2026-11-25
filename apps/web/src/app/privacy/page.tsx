import type { Metadata } from "next";

import { DraftPage } from "@/components/DraftPage";

export const metadata: Metadata = {
  title: "Privacy (draft)",
  robots: { index: false },
};

export default function PrivacyPage() {
  return <DraftPage title="Privacy" />;
}
