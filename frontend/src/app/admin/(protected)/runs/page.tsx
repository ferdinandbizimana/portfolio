import Link from "next/link";

import type { RunSummary } from "@/lib/runs";
import { apiGet } from "@/lib/server-api";

import { RunList } from "./run-list";

export const metadata = { title: "Runs" };

export default async function RunsPage() {
  const response = await apiGet("/api/admin/runs");
  if (!response.ok) return <p role="alert">The runs could not be loaded.</p>;
  const runs = (await response.json()) as RunSummary[];

  return (
    <div className="max-w-5xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="mb-1 text-2xl font-semibold">Runs</h1>
          <p className="text-muted">
            Every analysis run, newest first. Tick two runs of the same analysis to compare them.
          </p>
        </div>
        <Link href="/admin/analyses" className="btn-primary">
          New run
        </Link>
      </div>
      <RunList runs={runs} />
    </div>
  );
}
