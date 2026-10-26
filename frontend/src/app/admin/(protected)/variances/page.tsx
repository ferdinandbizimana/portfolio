import { apiGet } from "@/lib/server-api";
import type { DataFile } from "@/lib/upload";
import type { VarianceOverview } from "@/lib/variances";

import { VarianceBoard } from "./variance-board";

export const metadata = { title: "Stock variances" };

export default async function VariancesPage() {
  const [response, filesResponse] = await Promise.all([
    apiGet("/api/admin/variances"),
    apiGet("/api/admin/data-files"),
  ]);
  if (!response.ok || !filesResponse.ok) {
    return <p role="alert">The stock variances could not be loaded.</p>;
  }
  const overview = (await response.json()) as VarianceOverview;
  const files = (await filesResponse.json()) as DataFile[];

  return (
    <div className="max-w-6xl">
      <h1 className="mb-2 text-2xl font-semibold">Stock variances</h1>
      <p className="mb-6 text-muted">
        Variances from spot checks, the picking register and physical inventory documents go to the
        person responsible for the bin, by e-mail with a secure link to record the correction. A
        variance still open after {overview.overdue_days} days turns red; a list of open variances
        goes to each person every working morning.
      </p>
      <VarianceBoard overview={overview} files={files} />
    </div>
  );
}
