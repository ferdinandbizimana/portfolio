import type { PublicDashboard } from "@/lib/publications";

import { DashboardView } from "./dashboard-view";

/** A published, read-only dashboard as visitors see it. */
export function PublishedDashboard({ data }: { data: PublicDashboard }) {
  return (
    <article className="flex flex-col gap-6">
      <header>
        <h1 className="text-3xl font-semibold">{data.title}</h1>
        {data.dashboard.subtitle && <p className="mt-1 text-muted">{data.dashboard.subtitle}</p>}
        {data.description && <p className="mt-3 max-w-3xl">{data.description}</p>}
      </header>
      <DashboardView dashboard={data.dashboard} />
    </article>
  );
}
