"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { formatDateTime } from "@/lib/audit";
import { isActive, STATUS_LABEL, statusClass, type RunSummary } from "@/lib/runs";

export function RunList({ runs }: { runs: RunSummary[] }) {
  const router = useRouter();
  const [picked, setPicked] = useState<number[]>([]);

  const busy = runs.some((r) => isActive(r.status));
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => router.refresh(), 2000);
    return () => clearInterval(timer);
  }, [busy, router]);

  if (runs.length === 0) return <p className="text-muted">No runs yet.</p>;

  const first = runs.find((r) => r.id === picked[0]);
  const second = runs.find((r) => r.id === picked[1]);
  const comparable =
    first && second && first.analysis_key === second.analysis_key && second.status === "succeeded";

  function toggle(id: number) {
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id].slice(-2)));
  }

  return (
    <div className="flex flex-col gap-3">
      {picked.length === 2 && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg bg-panel p-3 text-sm">
          {comparable ? (
            <Link
              className="btn-primary"
              // Older run first, so the change reads from earlier to later.
              href={`/admin/runs/compare?a=${Math.min(...picked)}&b=${Math.max(...picked)}`}
            >
              Compare the two runs
            </Link>
          ) : (
            <span>Choose two finished runs of the same analysis to compare.</span>
          )}
        </div>
      )}
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-left text-sm">
          <thead className="bg-panel text-xs uppercase tracking-wide text-muted">
            <tr>
              <th scope="col" className="px-3 py-2">
                <span className="sr-only">Compare</span>
              </th>
              <th scope="col" className="px-3 py-2">
                Run
              </th>
              <th scope="col" className="px-3 py-2">
                Analysis
              </th>
              <th scope="col" className="px-3 py-2">
                Status
              </th>
              <th scope="col" className="px-3 py-2">
                Checks
              </th>
              <th scope="col" className="px-3 py-2">
                Started
              </th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="border-t border-line">
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    aria-label={`Select run ${run.id} to compare`}
                    disabled={run.status !== "succeeded"}
                    checked={picked.includes(run.id)}
                    onChange={() => toggle(run.id)}
                  />
                </td>
                <td className="px-3 py-2">
                  <Link href={`/admin/runs/${run.id}`}>{run.label || `Run #${run.id}`}</Link>
                </td>
                <td className="px-3 py-2">{run.analysis_title}</td>
                <td className="px-3 py-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs ${statusClass(run.status)}`}>
                    {STATUS_LABEL[run.status]}
                    {isActive(run.status) ? ` ${run.progress}%` : ""}
                  </span>
                </td>
                <td className="px-3 py-2">
                  {run.checks_total ? `${run.checks_passed} / ${run.checks_total}` : "–"}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-muted">
                  {formatDateTime(run.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
