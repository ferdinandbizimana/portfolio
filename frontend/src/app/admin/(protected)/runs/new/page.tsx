import { notFound } from "next/navigation";

import type { AnalysisInfo } from "@/lib/runs";
import { apiGet } from "@/lib/server-api";
import type { DataFile } from "@/lib/upload";

import { RunForm } from "./run-form";

export const metadata = { title: "New run" };

export default async function NewRunPage({
  searchParams,
}: {
  searchParams: Promise<{ analysis?: string }>;
}) {
  const key = (await searchParams).analysis;
  const [analysesResponse, filesResponse] = await Promise.all([
    apiGet("/api/admin/analyses"),
    apiGet("/api/admin/data-files"),
  ]);
  if (!analysesResponse.ok || !filesResponse.ok) {
    return <p role="alert">The page could not be loaded.</p>;
  }
  const analysis = ((await analysesResponse.json()) as AnalysisInfo[]).find((a) => a.key === key);
  if (!analysis) notFound();
  const files = ((await filesResponse.json()) as DataFile[]).filter((f) => f.status === "ready");

  return (
    <div className="max-w-3xl">
      <h1 className="mb-2 text-2xl font-semibold">{analysis.title}</h1>
      <p className="mb-6 text-muted">{analysis.description}</p>
      <RunForm analysis={analysis} files={files} />
    </div>
  );
}
