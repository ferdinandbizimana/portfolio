"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { DashboardView } from "@/components/dashboard/dashboard-view";
import { sendJson } from "@/lib/api-errors";
import { formatDateTime } from "@/lib/audit";
import { isActive, STATUS_LABEL, statusClass, type Run } from "@/lib/runs";
import { formatBytes } from "@/lib/upload";

export function RunView({ run }: { run: Run }) {
  const router = useRouter();
  const active = isActive(run.status);

  // Follow the run while the worker is busy.
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => router.refresh(), 1500);
    return () => clearInterval(timer);
  }, [active, router]);

  async function cancel() {
    await sendJson("POST", `/api/admin/runs/${run.id}/cancel`);
    router.refresh();
  }

  async function remove() {
    if (!window.confirm("Delete this run and its reports?")) return;
    const result = await sendJson("DELETE", `/api/admin/runs/${run.id}`);
    if (result.ok) {
      router.replace("/admin/runs");
      router.refresh();
    }
  }

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm text-muted">
            <Link href="/admin/runs">Runs</Link> / #{run.id}
          </p>
          <h1 className="text-2xl font-semibold">{run.label || run.analysis_title}</h1>
          <p className="text-sm text-muted">
            {run.analysis_title} v{run.analysis_version} · started {formatDateTime(run.created_at)}
          </p>
        </div>
        <div className="flex gap-2">
          {active ? (
            <button type="button" className="btn-secondary" onClick={cancel}>
              Cancel
            </button>
          ) : (
            <>
              {run.status === "succeeded" && run.dashboard && (
                <Link href={`/admin/runs/${run.id}/publish`} className="btn-primary">
                  Publish…
                </Link>
              )}
              <button type="button" className="btn-secondary text-danger" onClick={remove}>
                Delete run
              </button>
            </>
          )}
        </div>
      </div>

      <section aria-label="Status" className="rounded-lg border border-line p-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className={`rounded-full px-2 py-0.5 text-sm ${statusClass(run.status)}`}>
            {STATUS_LABEL[run.status]}
          </span>
          <span role="status">{run.message}</span>
        </div>
        {active && (
          <progress
            className="mt-3 w-full"
            value={run.progress}
            max={100}
            aria-label={`Progress ${run.progress}%`}
          />
        )}
        {run.errors.length > 0 && (
          <ul className="mt-3 list-disc pl-6 text-sm text-danger">
            {run.errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        )}
      </section>

      {run.reports.length > 0 && (
        <section aria-labelledby="reports-heading">
          <h2 id="reports-heading" className="mb-2 text-lg font-semibold">
            Reports
          </h2>
          <div className="flex flex-wrap gap-2">
            {run.reports
              .filter((report) => report.kind === "html")
              .map((report) => (
                <a
                  key={`${report.key}-view`}
                  className="btn-secondary"
                  href={`/api/admin/runs/${run.id}/reports/${report.key}/view`}
                  target="_blank"
                  rel="noopener"
                >
                  Open interactive dashboard
                </a>
              ))}
          </div>
          <h3 className="mb-2 mt-4 text-base font-semibold">Downloads</h3>
          <ul className="flex flex-col gap-2">
            {run.reports.map((report) => (
              <li
                key={report.key}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line px-3 py-2"
              >
                <span>
                  <span className="font-medium">{report.title}</span>{" "}
                  <span className="text-sm text-muted">
                    {report.filename} · {formatBytes(report.size_bytes)}
                  </span>
                </span>
                <a
                  className="btn-primary inline-flex items-center gap-2"
                  href={`/api/admin/runs/${run.id}/reports/${report.key}`}
                  download={report.filename}
                  aria-label={`Download ${report.title}`}
                >
                  <DownloadIcon />
                  Download
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

      {run.dashboard && <DashboardView dashboard={run.dashboard} />}

      <section aria-labelledby="inputs-heading" className="text-sm">
        <h2 id="inputs-heading" className="mb-2 text-lg font-semibold">
          Inputs and traceability
        </h2>
        <ul className="flex flex-col gap-1 text-muted">
          {Object.entries(run.inputs).map(([key, input]) => (
            <li key={key}>
              {input.filename},{" "}
              {input.sheet === "*" ? "all recognised sheets" : `sheet ${input.sheet}`} · SHA-256{" "}
              {input.sha256.slice(0, 16)}…
            </li>
          ))}
          {Object.entries(run.parameters).map(([key, value]) => (
            <li key={key}>
              {key}: {String(value)}
            </li>
          ))}
          {run.result_hash && <li>Result fingerprint: {run.result_hash.slice(0, 16)}…</li>}
        </ul>
      </section>
    </div>
  );
}

function DownloadIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M10 3v10M5.5 8.5 10 13l4.5-4.5M4 17h12" />
    </svg>
  );
}
