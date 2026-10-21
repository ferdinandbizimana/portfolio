"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { StatusMessage } from "@/components/admin/fields";
import { postJson } from "@/lib/api-errors";
import { formatDateTime } from "@/lib/audit";
import type { FolderStatus } from "@/lib/schedules";

export function FolderPanel({ folder }: { folder: FolderStatus }) {
  const router = useRouter();
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function scan() {
    setBusy(true);
    const result = await postJson<{ detail: string }>("/api/admin/folder/scan");
    setBusy(false);
    setMessage(
      result.ok
        ? { kind: "ok", text: "The folder is being checked. New files appear below." }
        : { kind: "error", text: result.message },
    );
    // Give the worker a moment, then show what it found.
    setTimeout(() => router.refresh(), 1500);
  }

  return (
    <section
      aria-labelledby="folder-heading"
      className="mb-6 flex flex-col gap-2 rounded-lg bg-panel p-4 text-sm"
    >
      <h2 id="folder-heading" className="font-semibold">
        Shared folder
      </h2>
      {folder.enabled ? (
        <>
          <p>
            New exports saved in the shared folder are picked up automatically (checked every{" "}
            {folder.interval_seconds} seconds; a file is taken once it has not changed for{" "}
            {folder.settle_seconds} seconds). Use <Link href="/admin/schedules">Schedules</Link> to
            run analyses on them automatically.
          </p>
          <p className="text-muted">
            Last check:{" "}
            {folder.last_check ? formatDateTime(folder.last_check) : "not yet (scheduler starting)"}
          </p>
          <div>
            <button type="button" className="btn-secondary" onClick={scan} disabled={busy}>
              Check the folder now
            </button>
          </div>
          <StatusMessage message={message} />
        </>
      ) : (
        <p className="text-muted">
          Not set up. To pick up SAP exports from a shared folder, set INBOX_HOST_DIR (see the
          operations guide).
        </p>
      )}
    </section>
  );
}
