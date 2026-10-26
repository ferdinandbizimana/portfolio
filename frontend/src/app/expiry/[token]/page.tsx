import type { Metadata } from "next";
import { notFound } from "next/navigation";

import type { ExpiryDetail } from "@/lib/expiry";
import { API_URL } from "@/lib/server-api";

import { JustifyList } from "./justify-list";

// Opened from the monthly e-mail of the sales pharmacist: never indexed, never cached.
export const metadata: Metadata = {
  title: "Expiry follow-up",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};
export const dynamic = "force-dynamic";

export default async function ExpiryPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const response = await fetch(`${API_URL}/api/public/expiry/${encodeURIComponent(token)}`, {
    cache: "no-store",
  });
  if (response.status === 404) notFound();
  if (!response.ok) return <p role="alert">This page could not be loaded. Please try again.</p>;
  const detail = (await response.json()) as ExpiryDetail;
  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <JustifyList token={token} detail={detail} />
    </main>
  );
}
