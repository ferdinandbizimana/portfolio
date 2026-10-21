import Link from "next/link";

import type { AnalysisInfo } from "@/lib/runs";
import { apiGet } from "@/lib/server-api";

export const metadata = { title: "Analyses" };

export default async function AnalysesPage() {
  const response = await apiGet("/api/admin/analyses");
  if (!response.ok) return <p role="alert">The analyses could not be loaded.</p>;
  const analyses = (await response.json()) as AnalysisInfo[];

  return (
    <div className="max-w-4xl">
      <h1 className="mb-2 text-2xl font-semibold">Analyses</h1>
      <p className="mb-6 text-muted">
        Choose an analysis, pick the uploaded files it needs, and run it. Every run is kept in{" "}
        <Link href="/admin/runs">Runs</Link>.
      </p>
      <div className="flex flex-col gap-4">
        {analyses.map((analysis) => (
          <section key={analysis.key} className="rounded-lg border border-line p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold">
                  {analysis.title}{" "}
                  <span className="text-xs font-normal text-muted">v{analysis.version}</span>
                </h2>
                <p className="mt-1 text-sm text-muted">{analysis.description}</p>
                <p className="mt-2 text-sm">
                  Needs: {analysis.inputs.map((i) => i.dataset_title).join(", ")}
                </p>
              </div>
              <Link href={`/admin/runs/new?analysis=${analysis.key}`} className="btn-primary">
                Run
              </Link>
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
