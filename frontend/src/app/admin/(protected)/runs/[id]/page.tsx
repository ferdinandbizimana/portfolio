import { notFound } from "next/navigation";

import type { Run } from "@/lib/runs";
import { apiGet } from "@/lib/server-api";

import { RunView } from "./run-view";

export const metadata = { title: "Run" };

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const id = Number((await params).id);
  if (!Number.isInteger(id)) notFound();
  const response = await apiGet(`/api/admin/runs/${id}`);
  if (response.status === 404) notFound();
  if (!response.ok) return <p role="alert">The run could not be loaded.</p>;
  return <RunView run={(await response.json()) as Run} />;
}
