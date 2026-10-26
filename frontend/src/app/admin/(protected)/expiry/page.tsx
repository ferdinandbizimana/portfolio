import type { ExpiryOverview } from "@/lib/expiry";
import { apiGet } from "@/lib/server-api";

import { ExpiryBoard } from "./expiry-board";

export const metadata = { title: "Expiry follow-up" };

export default async function ExpiryPage() {
  const response = await apiGet("/api/admin/expiry");
  if (!response.ok) return <p role="alert">The expiry follow-up could not be loaded.</p>;
  const overview = (await response.json()) as ExpiryOverview;
  return (
    <div className="max-w-6xl">
      <h1 className="mb-2 text-2xl font-semibold">Expiry follow-up</h1>
      <p className="mb-6 text-muted">
        Each expiry monitoring run can be followed up: the sales pharmacist receives the expired
        stock and what expires within 3 and 3 to 6 months, value per plant, with the batches in
        Excel and a secure link to justify every expired item. The latest run is e-mailed
        automatically on the last day of each month.
      </p>
      <ExpiryBoard initial={overview} />
    </div>
  );
}
