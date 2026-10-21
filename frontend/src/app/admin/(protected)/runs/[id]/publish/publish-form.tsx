"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Field } from "@/components/admin/fields";
import { DashboardView } from "@/components/dashboard/dashboard-view";
import { postJson } from "@/lib/api-errors";
import type { Dashboard } from "@/lib/dashboard";
import type { Run } from "@/lib/runs";

type DetailLevel = "summary" | "detail";

export function PublishForm({ run }: { run: Run }) {
  const router = useRouter();
  const [title, setTitle] = useState(run.label || run.analysis_title);
  const [description, setDescription] = useState("");
  const [detailLevel, setDetailLevel] = useState<DetailLevel>("summary");
  const [includeChecks, setIncludeChecks] = useState(false);
  const [preview, setPreview] = useState<Dashboard | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Show exactly what visitors would see for the chosen options.
  useEffect(() => {
    let cancelled = false;
    const query = new URLSearchParams({
      detail_level: detailLevel,
      include_checks: String(includeChecks),
    });
    fetch(`/api/admin/runs/${run.id}/publication-preview?${query}`, {
      credentials: "same-origin",
    })
      .then((response) => (response.ok ? (response.json() as Promise<Dashboard>) : null))
      .catch(() => null)
      .then((data) => {
        if (cancelled) return;
        setPreview(data);
        setPreviewError(data ? "" : "The preview could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [run.id, detailLevel, includeChecks]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const result = await postJson(`/api/admin/runs/${run.id}/publications`, {
      title,
      description,
      detail_level: detailLevel,
      include_checks: includeChecks,
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    router.push("/admin/publications");
    router.refresh();
  }

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div>
        <p className="text-sm text-muted">
          <Link href="/admin/runs">Runs</Link> /{" "}
          <Link href={`/admin/runs/${run.id}`}>#{run.id}</Link> / Publish
        </p>
        <h1 className="text-2xl font-semibold">Publish a dashboard</h1>
        <p className="text-sm text-muted">
          Publishing saves a frozen copy of this dashboard. It starts private: choose who can see it
          on the Published page. Later runs never change it.
        </p>
      </div>

      <form onSubmit={submit} className="flex max-w-2xl flex-col gap-4">
        <Field label="Title">
          <input
            className="input"
            required
            maxLength={200}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field label="Description" hint="Shown above the dashboard. Optional.">
          <textarea
            className="input"
            rows={3}
            maxLength={2000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <fieldset className="flex flex-col gap-2 text-sm">
          <legend className="mb-1 font-medium">Level of detail</legend>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="detail_level"
              checked={detailLevel === "summary"}
              onChange={() => setDetailLevel("summary")}
            />
            Summary only (totals and summary tables, no line-level detail)
          </label>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="detail_level"
              checked={detailLevel === "detail"}
              onChange={() => setDetailLevel("detail")}
            />
            Full detail (every table shown in the dashboard)
          </label>
        </fieldset>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={includeChecks}
            onChange={(e) => setIncludeChecks(e.target.checked)}
          />
          Show the self-checks
        </label>
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        <div>
          <button type="submit" className="btn-primary" disabled={busy || !title.trim()}>
            {busy ? "Saving…" : "Create (private)"}
          </button>
        </div>
      </form>

      <section aria-labelledby="preview-heading" className="rounded-lg border border-line p-4">
        <h2 id="preview-heading" className="mb-4 text-lg font-semibold">
          Preview: what visitors will see
        </h2>
        {previewError && <p role="alert">{previewError}</p>}
        {preview ? <DashboardView dashboard={preview} /> : !previewError && <p>Loading…</p>}
      </section>
    </div>
  );
}
