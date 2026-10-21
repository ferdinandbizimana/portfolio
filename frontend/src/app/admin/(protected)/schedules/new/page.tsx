import Link from "next/link";

import { loadFormData } from "../load";
import { ScheduleForm } from "../schedule-form";

export const metadata = { title: "New schedule" };

export default async function NewSchedulePage() {
  const data = await loadFormData();
  if (!data) return <p role="alert">The analyses could not be loaded.</p>;
  return (
    <div>
      <p className="text-sm text-muted">
        <Link href="/admin/schedules">Schedules</Link> / New
      </p>
      <h1 className="mb-6 text-2xl font-semibold">New schedule</h1>
      <ScheduleForm analyses={data.analyses} options={data.options} />
    </div>
  );
}
