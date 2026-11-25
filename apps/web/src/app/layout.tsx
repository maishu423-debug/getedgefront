import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";

import { SITE_URL } from "@/lib/site";

// Self-hosted, subset fonts (Phase 6 B1): the same three families as the design, cut to the
// characters EdgeFront prints and the weights the UI uses (tools/subset_fonts.py, OFL 1.1 —
// see ./fonts/README.md). 70 KB in total instead of 101 KB from Google's Latin files.
const spaceGrotesk = localFont({
  src: "./fonts/space-grotesk-latin-var.woff2",
  variable: "--font-space-grotesk",
  weight: "500 700",
  display: "swap",
});
const inter = localFont({
  src: "./fonts/inter-latin-var.woff2",
  variable: "--font-inter",
  weight: "400 700",
  display: "swap",
});
const jetbrainsMono = localFont({
  src: "./fonts/jetbrains-mono-latin-var.woff2",
  variable: "--font-jetbrains-mono",
  weight: "400 600",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "EdgeFront — observed weather at the stations weather markets settle on",
    template: "%s | EdgeFront",
  },
  description:
    "Hourly METARs, NWS daily climate reports and ASOS daily summaries, and NWS forecasts for the U.S. stations that Kalshi, Polymarket and Robinhood weather markets use, each with its source and time stamp.",
  openGraph: { siteName: "EdgeFront", type: "website", locale: "en_US" },
  twitter: { card: "summary" },
};

export const viewport: Viewport = { themeColor: "#101A1C", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${spaceGrotesk.variable} ${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-page text-ink">{children}</body>
    </html>
  );
}
