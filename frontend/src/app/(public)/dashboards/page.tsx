import type { Metadata } from "next";
import Link from "next/link";

import { PageShell } from "@/components/portfolio/page-shell";
import { formatDateTime } from "@/lib/audit";
import { fetchPublicDashboards } from "@/lib/public-api";

export const metadata: Metadata = { title: "Dashboards" };

export default async function DashboardsPage() {
  const dashboards = await fetchPublicDashboards();

  return (
    <PageShell
      eyebrow="Live work"
      title="Dashboards"
      intro="Interactive summaries of supply chain analyses, built from SAP exports. Use the filters and search on each dashboard to explore the figures."
    >
      {dashboards.length === 0 ? (
        <p className="text-muted">No dashboards are published yet.</p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {dashboards.map((d) => (
            <li key={d.slug}>
              <Link
                href={`/dashboards/${d.slug}`}
                className="tile flex h-full flex-col gap-2 text-ink no-underline hover:border-accent"
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
    </PageShell>
  );
}
