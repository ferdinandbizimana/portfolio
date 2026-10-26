import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { API_URL } from "@/lib/server-api";
import type { PublicVariance } from "@/lib/variances";

import { CorrectionForm } from "./correction-form";

// Opened from the e-mail of the responsible person: never indexed, never cached.
export const metadata: Metadata = {
  title: "Stock variance",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};
export const dynamic = "force-dynamic";

export default async function VariancePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const response = await fetch(`${API_URL}/api/public/variances/${encodeURIComponent(token)}`, {
    cache: "no-store",
  });
  if (response.status === 404) notFound();
  if (!response.ok) return <p role="alert">This variance could not be loaded. Please try again.</p>;
  const variance = (await response.json()) as PublicVariance;
  return (
    <main className="mx-auto max-w-xl px-4 py-8">
      <CorrectionForm token={token} initial={variance} />
    </main>
  );
}
