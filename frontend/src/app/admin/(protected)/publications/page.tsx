import type { Publication } from "@/lib/publications";
import { apiGet } from "@/lib/server-api";

import { PublicationList } from "./publication-list";

export const metadata = { title: "Published dashboards" };

export default async function PublicationsPage() {
  const response = await apiGet("/api/admin/publications");
  if (!response.ok) return <p role="alert">The published dashboards could not be loaded.</p>;
  const publications = (await response.json()) as Publication[];

  return (
    <div className="max-w-4xl">
      <h1 className="mb-2 text-2xl font-semibold">Published dashboards</h1>
      <p className="mb-6 text-muted">
        Each entry is a frozen copy of a run&apos;s dashboard. To publish a new one, open a finished
        run and choose Publish. Unpublishing deletes the copy and its links stop working at once.
      </p>
      <PublicationList publications={publications} />
    </div>
  );
}
