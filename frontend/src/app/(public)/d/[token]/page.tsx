import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PublishedDashboard } from "@/components/dashboard/published-dashboard";
import { fetchSharedDashboard } from "@/lib/public-api";

// Shared by secret link: never indexed by search engines.
export const metadata: Metadata = {
  title: "Shared dashboard",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default async function SharedDashboardPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const data = await fetchSharedDashboard((await params).token);
  if (!data) notFound();
  return <PublishedDashboard data={data} />;
}
