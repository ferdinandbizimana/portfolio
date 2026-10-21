"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { StatusMessage } from "@/components/admin/fields";
import { sendJson } from "@/lib/api-errors";
import { formatDateTime } from "@/lib/audit";
import { formatBytes, uploadFile, type DataFile } from "@/lib/upload";

type Progress = { name: string; fraction: number; text: string };

export function DataFiles({ files }: { files: DataFile[] }) {
  const router = useRouter();
  const [progress, setProgress] = useState<Progress[]>([]);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  // While files are being read in the background, refresh every 2 seconds.
  const busy = files.some((f) => f.status === "received" || f.status === "parsing");
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => router.refresh(), 2000);
    return () => clearInterval(timer);
  }, [busy, router]);

  async function upload(list: FileList | null) {
    if (!list?.length) return;
    setMessage(null);
    for (const file of Array.from(list)) {
      const update = (fraction: number, text: string) =>
        setProgress((p) => [
          ...p.filter((x) => x.name !== file.name),
          { name: file.name, fraction, text },
        ]);
      try {
        await uploadFile(file, update);
        setMessage({ kind: "ok", text: `${file.name} uploaded. It is being read now.` });
      } catch (error) {
        setMessage({
          kind: "error",
          text: `${file.name}: ${error instanceof Error ? error.message : "upload failed"}`,
        });
      }
      setProgress((p) => p.filter((x) => x.name !== file.name));
      router.refresh();
    }
  }

  async function remove(file: DataFile) {
    const warning = file.used_by_runs
      ? ` It was used by ${file.used_by_runs} run(s); their results stay, but they cannot be re-run.`
      : "";
    if (!window.confirm(`Delete ${file.filename}?${warning}`)) return;
    const result = await sendJson("DELETE", `/api/admin/data-files/${file.id}`);
    if (!result.ok) setMessage({ kind: "error", text: result.message });
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-6">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void upload(e.dataTransfer.files);
        }}
        className={`flex flex-col items-center gap-3 rounded-lg border-2 border-dashed p-8 text-center ${
          dragging ? "border-accent bg-panel" : "border-line"
        }`}
      >
        <p>Drop Excel or CSV files here, or</p>
        <button type="button" className="btn-primary" onClick={() => input.current?.click()}>
          Choose files
        </button>
        <input
          ref={input}
          type="file"
          multiple
          accept=".xlsx,.xlsm,.xls,.csv,.txt"
          className="sr-only"
          aria-label="Choose files to upload"
          onChange={(e) => {
            void upload(e.target.files);
            e.target.value = "";
          }}
        />
        {progress.map((p) => (
          <div key={p.name} className="w-full max-w-md text-left text-sm">
            <div className="flex justify-between">
              <span className="truncate">{p.name}</span>
              <span>{Math.round(p.fraction * 100)}%</span>
            </div>
            <progress
              className="w-full"
              value={p.fraction}
              max={1}
              aria-label={`${p.name} ${p.text}`}
            />
          </div>
        ))}
      </div>
      <StatusMessage message={message} />
      {files.length === 0 ? (
        <p className="text-muted">No files yet.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {files.map((file) => (
            <li key={file.id} className="rounded-lg border border-line p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-medium">{file.filename}</p>
                  <p className="text-xs text-muted">
                    {formatBytes(file.size_bytes)} ·{" "}
                    {file.source === "folder"
                      ? `from the shared folder (${file.source_path ?? file.filename})`
                      : "uploaded"}{" "}
                    {formatDateTime(file.created_at)} · SHA-256 {file.sha256.slice(0, 12)}…
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      file.status === "ready"
                        ? "bg-success-soft text-success"
                        : file.status === "failed"
                          ? "bg-danger-soft text-danger"
                          : "bg-panel text-muted"
                    }`}
                  >
                    {file.status === "ready"
                      ? "Ready"
                      : file.status === "failed"
                        ? "Failed"
                        : "Reading…"}
                  </span>
                  <button type="button" className="btn-secondary" onClick={() => remove(file)}>
                    Delete
                  </button>
                </div>
              </div>
              <p className="mt-2 text-sm text-muted">{file.message}</p>
              {file.sheets.length > 0 && (
                <ul className="mt-2 flex flex-col gap-1 text-sm">
                  {file.sheets.map((sheet) => (
                    <li key={sheet.name}>
                      <span className="font-medium">{sheet.name}</span>: {sheet.row_count} rows,{" "}
                      {sheet.columns.length} columns
                      {sheet.matches.length > 0 ? (
                        <span className="ml-2 rounded-full bg-success-soft px-2 py-0.5 text-xs text-success">
                          {sheet.matches[0]!.title}
                        </span>
                      ) : (
                        <span className="ml-2 text-xs text-muted">not recognised</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
