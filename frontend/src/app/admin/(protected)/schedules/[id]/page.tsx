import Link from "next/link";
import { notFound } from "next/navigation";

import type { Schedule } from "@/lib/schedules";
import { apiGet } from "@/lib/server-api";

import { loadFormData } from "../load";
import { ScheduleForm } from "../schedule-form";

export const metadata = { title: "Edit schedule" };

export default async function EditSchedulePage({ params }: { params: Promise<{ id: string }> }) {
  const id = Number((await params).id);
  if (!Number.isInteger(id)) notFound();
  const response = await apiGet(`/api/admin/schedules/${id}`);
  if (response.status === 404) notFound();
  const data = await loadFormData();
  if (!response.ok || !data) return <p role="alert">The schedule could not be loaded.</p>;
  const schedule = (await response.json()) as Schedule;
  return (
    <div>
      <p className="text-sm text-muted">
        <Link href="/admin/schedules">Schedules</Link> / {schedule.name}
      </p>
      <h1 className="mb-6 text-2xl font-semibold">Edit schedule</h1>
      <ScheduleForm analyses={data.analyses} options={data.options} schedule={schedule} />
    </div>
  );
}
