import { apiGet } from "@/lib/server-api";
import type { DataFile } from "@/lib/upload";

import type { FolderStatus } from "@/lib/schedules";

import { DataFiles } from "./data-files";
import { FolderPanel } from "./folder-panel";

export const metadata = { title: "Data files" };

export default async function DataPage() {
  const [response, folderResponse] = await Promise.all([
    apiGet("/api/admin/data-files"),
    apiGet("/api/admin/folder"),
  ]);
  if (!response.ok) return <p role="alert">The data files could not be loaded.</p>;
  const files = (await response.json()) as DataFile[];
  const folder = folderResponse.ok ? ((await folderResponse.json()) as FolderStatus) : null;

  return (
    <div className="max-w-5xl">
      <h1 className="mb-2 text-2xl font-semibold">Data files</h1>
      <p className="mb-6 text-muted">
        Upload Excel or CSV exports from SAP. Large files are sent in pieces and an interrupted
        upload continues where it stopped. Files stay private; they are never shown on the public
        site.
      </p>
      {folder && <FolderPanel folder={folder} />}
      <DataFiles files={files} />
    </div>
  );
}
