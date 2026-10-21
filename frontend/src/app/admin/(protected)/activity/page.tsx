import Link from "next/link";

import { actionLabel, detailText, formatDateTime, isWarning, type AuditPage } from "@/lib/audit";
import { apiGet } from "@/lib/server-api";

export const metadata = { title: "Activity log" };

const PAGE_SIZE = 50;

export default async function ActivityPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const page = Math.max(1, Number.parseInt((await searchParams).page ?? "1", 10) || 1);
  const response = await apiGet(
    `/api/admin/audit?limit=${PAGE_SIZE}&offset=${(page - 1) * PAGE_SIZE}`,
  );
  if (!response.ok) {
    return <p role="alert">The activity log could not be loaded. Please refresh the page.</p>;
  }
  const data = (await response.json()) as AuditPage;
  const lastPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE));

  return (
    <div className="max-w-5xl">
      <h1 className="mb-2 text-2xl font-semibold">Activity log</h1>
      <p className="mb-6 text-muted">
        {data.total} {data.total === 1 ? "event" : "events"}, newest first. Times are Kigali time.
      </p>
      {data.items.length === 0 ? (
        <p className="text-muted">No activity yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-left text-sm">
            <thead className="bg-panel text-xs uppercase tracking-wide text-muted">
              <tr>
                <th scope="col" className="px-3 py-2">
                  When
                </th>
                <th scope="col" className="px-3 py-2">
                  Action
                </th>
                <th scope="col" className="px-3 py-2">
                  From
                </th>
                <th scope="col" className="px-3 py-2">
                  Details
                </th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((event) => (
                <tr key={event.id} className="border-t border-line">
                  <td className="whitespace-nowrap px-3 py-2">
                    {formatDateTime(event.occurred_at)}
                  </td>
                  <td
                    className={`whitespace-nowrap px-3 py-2 ${isWarning(event.action) ? "font-medium text-danger" : ""}`}
                  >
                    {actionLabel(event.action)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-muted">
                    {event.ip_address ?? "–"}
                  </td>
                  <td className="px-3 py-2 text-muted">{detailText(event.detail)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {lastPage > 1 && (
        <nav aria-label="Pages" className="mt-4 flex items-center gap-3 text-sm">
          {page > 1 && <Link href={`/admin/activity?page=${page - 1}`}>← Newer</Link>}
          <span className="text-muted">
            Page {page} of {lastPage}
          </span>
          {page < lastPage && <Link href={`/admin/activity?page=${page + 1}`}>Older →</Link>}
        </nav>
      )}
    </div>
  );
}
