import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";

import { SITE_URL } from "@/lib/site";

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});
const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
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
