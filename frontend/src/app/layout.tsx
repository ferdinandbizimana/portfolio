import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { siteUrl } from "@/lib/site";

import "./globals.css";

const NAME = "Ferdinand Bizimana";
const DESCRIPTION =
  "Supply chain and inventory analyst working with SAP S/4HANA (MM, EWM, SD, FI): case studies, live dashboards and CV.";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl()),
  title: { template: `%s · ${NAME}`, default: NAME },
  description: DESCRIPTION,
  openGraph: { type: "website", siteName: NAME, title: NAME, description: DESCRIPTION },
  twitter: { card: "summary_large_image" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0d1418" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
