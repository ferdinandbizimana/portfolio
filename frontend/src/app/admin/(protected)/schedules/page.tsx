import Link from "next/link";

import type { Schedule, ScheduleOptions } from "@/lib/schedules";
import { apiGet } from "@/lib/server-api";

import { ScheduleList } from "./schedule-list";

export const metadata = { title: "Schedules" };

export default async function SchedulesPage() {
  const [response, optionsResponse] = await Promise.all([
    apiGet("/api/admin/schedules"),
    apiGet("/api/admin/schedules/options"),
  ]);
  if (!response.ok || !optionsResponse.ok) {
    return <p role="alert">The schedules could not be loaded.</p>;
  }
  const schedules = (await response.json()) as Schedule[];
  const options = (await optionsResponse.json()) as ScheduleOptions;

  return (
    <div className="max-w-4xl">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Schedules</h1>
        <Link href="/admin/schedules/new" className="btn-primary">
          New schedule
        </Link>
      </div>
      <p className="mb-6 text-muted">
        A schedule runs an analysis automatically on the newest files from the shared folder (or
        uploaded files whose names match). Times are in {options.timezone}.
        {!options.folder_enabled &&
          " The shared folder is not set up yet, so only uploaded files can match."}
      </p>
      <ScheduleList schedules={schedules} rules={options.date_rules} />
    </div>
  );
}
