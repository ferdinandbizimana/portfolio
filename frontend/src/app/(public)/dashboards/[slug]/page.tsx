import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { PublishedDashboard } from "@/components/dashboard/published-dashboard";
import { fetchPublicDashboard } from "@/lib/public-api";

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const data = await fetchPublicDashboard((await params).slug);
  if (!data) return { title: "Not found" };
  return { title: data.title, description: data.description || data.dashboard.subtitle };
}

export default async function DashboardPage({ params }: Props) {
  const data = await fetchPublicDashboard((await params).slug);
  if (!data) notFound();
  return (
    <div className="flex flex-col gap-4">
      <Link href="/dashboards" className="text-sm">
        ← All dashboards
      </Link>
      <PublishedDashboard data={data} />
    </div>
  );
}
