import { notFound } from "next/navigation";

import type { Run } from "@/lib/runs";
import { apiGet } from "@/lib/server-api";

import { PublishForm } from "./publish-form";

export const metadata = { title: "Publish dashboard" };

export default async function PublishPage({ params }: { params: Promise<{ id: string }> }) {
  const id = Number((await params).id);
  if (!Number.isInteger(id)) notFound();
  const response = await apiGet(`/api/admin/runs/${id}`);
  if (response.status === 404) notFound();
  if (!response.ok) return <p role="alert">The run could not be loaded.</p>;
  const run = (await response.json()) as Run;
  if (run.status !== "succeeded" || !run.dashboard) {
    return <p role="alert">Only a finished run with a dashboard can be published.</p>;
  }
  return <PublishForm run={run} />;
}
