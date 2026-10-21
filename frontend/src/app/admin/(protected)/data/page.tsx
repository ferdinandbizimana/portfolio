import { apiGet } from "@/lib/server-api";
import type { DataFile } from "@/lib/upload";

import { DataFiles } from "./data-files";

export const metadata = { title: "Data files" };

export default async function DataPage() {
  const response = await apiGet("/api/admin/data-files");
  if (!response.ok) return <p role="alert">The data files could not be loaded.</p>;
  const files = (await response.json()) as DataFile[];

  return (
    <div className="max-w-5xl">
      <h1 className="mb-2 text-2xl font-semibold">Data files</h1>
      <p className="mb-6 text-muted">
        Upload Excel or CSV exports from SAP. Large files are sent in pieces and an interrupted
        upload continues where it stopped. Files stay private; they are never shown on the public
        site.
      </p>
      <DataFiles files={files} />
    </div>
  );
}
