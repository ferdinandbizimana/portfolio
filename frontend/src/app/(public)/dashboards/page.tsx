import type { Metadata } from "next";
import Link from "next/link";

import { formatDateTime } from "@/lib/audit";
import { fetchPublicDashboards } from "@/lib/public-api";

export const metadata: Metadata = { title: "Dashboards" };

export default async function DashboardsPage() {
  const dashboards = await fetchPublicDashboards();

  return (
    <div>
      <h1 className="mb-2 text-3xl font-semibold">Dashboards</h1>
      <p className="mb-8 text-muted">
        Interactive summaries of supply chain analyses. Use the filters and search on each dashboard
        to explore the figures.
      </p>
      {dashboards.length === 0 ? (
        <p className="text-muted">No dashboards are published yet.</p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {dashboards.map((d) => (
            <li key={d.slug}>
              <Link
                href={`/dashboards/${d.slug}`}
                className="flex h-full flex-col gap-2 rounded-lg border border-line p-4 text-ink hover:bg-panel"
              >
                <h2 className="font-semibold">{d.title}</h2>
                {d.description && <p className="text-sm text-muted">{d.description}</p>}
                {d.published_at && (
                  <p className="mt-auto text-xs text-muted">
                    Published {formatDateTime(d.published_at)}
                  </p>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
