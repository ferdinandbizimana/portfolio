"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { sendJson } from "@/lib/api-errors";
import { formatDateTime } from "@/lib/audit";
import { STATUS_LABEL, type RunStatus } from "@/lib/runs";
import { describeParameter, describeWhen, type Schedule } from "@/lib/schedules";

export function ScheduleList({
  schedules,
  rules,
}: {
  schedules: Schedule[];
  rules: Record<string, string>;
}) {
  if (schedules.length === 0) {
    return <p className="text-muted">No schedules yet.</p>;
  }
  return (
    <ul className="flex flex-col gap-4">
      {schedules.map((s) => (
        <ScheduleItem key={s.id} schedule={s} rules={rules} />
      ))}
    </ul>
  );
}

function ScheduleItem({ schedule, rules }: { schedule: Schedule; rules: Record<string, string> }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function runNow() {
    setBusy(true);
    setError("");
    const result = await sendJson<Schedule>("POST", `/api/admin/schedules/${schedule.id}/run-now`);
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    if (result.data.last_run_id) router.push(`/admin/runs/${result.data.last_run_id}`);
  }

  async function remove() {
    if (!window.confirm(`Delete the schedule "${schedule.name}"? Its past runs are kept.`)) return;
    const result = await sendJson("DELETE", `/api/admin/schedules/${schedule.id}`);
    if (!result.ok) setError(result.message);
    router.refresh();
  }

  return (
    <li className="flex flex-col gap-2 rounded-lg border border-line p-4 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">
            {schedule.name}
            {!schedule.enabled && (
              <span className="ml-2 rounded-full bg-panel px-2 py-0.5 text-xs font-normal text-muted">
                Off
              </span>
            )}
          </h2>
          <p className="text-muted">
            {schedule.analysis_title} · {describeWhen(schedule)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-primary" onClick={runNow} disabled={busy}>
            {busy ? "Starting…" : "Run now"}
          </button>
          <Link href={`/admin/schedules/${schedule.id}`} className="btn-secondary">
            Edit
          </Link>
          <button type="button" className="btn-secondary text-danger" onClick={remove}>
            Delete
          </button>
        </div>
      </div>
      <ul className="text-muted">
        {Object.entries(schedule.inputs).map(([key, rule]) => (
          <li key={key}>
            Files named like <code>{rule.pattern}</code>
            {rule.sheet ? `, sheet ${rule.sheet}` : ""}
          </li>
        ))}
        {Object.entries(schedule.parameters).map(([name, value]) => (
          <li key={name}>
            {name}: {describeParameter(value, rules)}
          </li>
        ))}
      </ul>
      {schedule.last_message && <p>{schedule.last_message}</p>}
      <p className="text-xs text-muted">
        {schedule.run_count} run(s)
        {schedule.last_run_id && (
          <>
            {" "}
            · last:{" "}
            <Link href={`/admin/runs/${schedule.last_run_id}`}>
              run #{schedule.last_run_id}
              {schedule.last_run_status &&
                ` (${STATUS_LABEL[schedule.last_run_status as RunStatus] ?? schedule.last_run_status})`}
            </Link>
          </>
        )}
        {schedule.last_checked_at && ` · checked ${formatDateTime(schedule.last_checked_at)}`}
      </p>
      {error && (
        <p role="alert" className="text-danger">
          {error}
        </p>
      )}
    </li>
  );
}
