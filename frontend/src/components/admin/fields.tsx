"use client";

import { useId, useState, type ReactNode } from "react";

import { Markdown } from "@/components/markdown";
import { sendJson } from "@/lib/api-errors";
import type { FileRef } from "@/lib/portfolio";

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm font-medium">
      {label}
      {children}
      {hint && <span className="text-xs font-normal text-muted">{hint}</span>}
    </label>
  );
}

/** A Markdown textarea with a Preview tab. */
export function MarkdownField({
  label,
  value,
  onChange,
  rows = 6,
  maxLength,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  maxLength?: number;
}) {
  const id = useId();
  const [preview, setPreview] = useState(false);
  return (
    <div className="flex flex-col gap-1 text-sm">
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="font-medium">
          {label}
        </label>
        <button
          type="button"
          className="text-xs text-accent"
          onClick={() => setPreview((p) => !p)}
          aria-pressed={preview}
        >
          {preview ? "Edit" : "Preview"}
        </button>
      </div>
      {preview ? (
        <div className="min-h-24 rounded-md border border-line p-3">
          {value.trim() ? <Markdown>{value}</Markdown> : <p className="text-muted">Nothing yet.</p>}
        </div>
      ) : (
        <textarea
          id={id}
          className="input font-mono text-sm"
          rows={rows}
          value={value}
          maxLength={maxLength}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      <span className="text-xs text-muted">
        Markdown: **bold**, *italic*, ## heading, - list, [link](https://…), | tables |.
      </span>
    </div>
  );
}

/** Upload or remove one file (image or PDF). */
export function FilePicker({
  label,
  accept,
  value,
  onChange,
}: {
  label: string;
  accept: string;
  value: FileRef | null;
  onChange: (file: FileRef | null) => void;
}) {
  const id = useId();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    const result = await sendJson<FileRef>("POST", "/api/admin/files", form);
    setBusy(false);
    if (result.ok) onChange(result.data);
    else setError(result.message);
  }

  return (
    <div className="flex flex-col gap-1 text-sm">
      <span className="font-medium">{label}</span>
      {value ? (
        <div className="flex flex-wrap items-center gap-3">
          {value.content_type.startsWith("image/") ? (
            // eslint-disable-next-line @next/next/no-img-element -- small admin preview
            <img src={value.url} alt="" className="h-16 w-16 rounded object-cover" />
          ) : (
            <a href={value.url}>{value.filename}</a>
          )}
          <button type="button" className="btn-secondary" onClick={() => onChange(null)}>
            Remove
          </button>
        </div>
      ) : (
        <span className="text-muted">None</span>
      )}
      <label htmlFor={id} className="btn-secondary mt-1 cursor-pointer self-start">
        {busy ? "Uploading…" : value ? "Replace…" : "Upload…"}
      </label>
      <input
        id={id}
        type="file"
        accept={accept}
        className="sr-only"
        disabled={busy}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void upload(file);
          e.target.value = "";
        }}
      />
      {error && (
        <span role="alert" className="text-danger">
          {error}
        </span>
      )}
    </div>
  );
}

export function StatusMessage({
  message,
}: {
  message: { kind: "ok" | "error"; text: string } | null;
}) {
  if (!message) return null;
  return (
    <p
      role={message.kind === "error" ? "alert" : "status"}
      className={`rounded-md px-3 py-2 text-sm ${
        message.kind === "error" ? "bg-danger-soft text-danger" : "bg-success-soft text-success"
      }`}
    >
      {message.text}
    </p>
  );
}
