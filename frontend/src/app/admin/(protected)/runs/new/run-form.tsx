"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Field, StatusMessage } from "@/components/admin/fields";
import { postJson } from "@/lib/api-errors";
import type { AnalysisInfo, Run } from "@/lib/runs";
import type { DataFile } from "@/lib/upload";

type Choice = { fileId: string; sheet: string };

/** The best sheet for a dataset: one recognised as it, newest file first. */
export function suggest(files: DataFile[], dataset: string): Choice {
  for (const file of files) {
    const sheet = file.sheets.find((s) => s.matches.some((m) => m.dataset === dataset));
    if (sheet) return { fileId: String(file.id), sheet: sheet.name };
  }
  return { fileId: "", sheet: "" };
}

export function RunForm({ analysis, files }: { analysis: AnalysisInfo; files: DataFile[] }) {
  const router = useRouter();
  const properties = analysis.parameters_schema.properties ?? {};
  const [label, setLabel] = useState("");
  const [params, setParams] = useState<Record<string, string>>({});
  const [choices, setChoices] = useState<Record<string, Choice>>(() =>
    Object.fromEntries(analysis.inputs.map((i) => [i.key, suggest(files, i.dataset)])),
  );
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    const inputs = Object.fromEntries(
      Object.entries(choices)
        .filter(([, c]) => c.fileId && c.sheet)
        .map(([key, c]) => [key, { data_file_id: Number(c.fileId), sheet: c.sheet }]),
    );
    const result = await postJson<Run>("/api/admin/runs", {
      analysis: analysis.key,
      label,
      parameters: params,
      inputs,
    });
    if (result.ok) {
      router.push(`/admin/runs/${result.data.id}`);
      return;
    }
    setPending(false);
    setMessage({ kind: "error", text: result.message });
  }

  if (files.length === 0) {
    return (
      <p>
        No data files are ready yet. <Link href="/admin/data">Upload the files first</Link>.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-6">
      <Field label="Name of this run" hint="For example: End of June 2026.">
        <input
          className="input"
          maxLength={200}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
      </Field>

      {Object.entries(properties).map(([name, prop]) => (
        <Field key={name} label={prop.title ?? name} hint={prop.description}>
          {prop.enum ? (
            <select
              className="input"
              required={analysis.parameters_schema.required?.includes(name)}
              value={params[name] ?? ""}
              onChange={(e) => setParams({ ...params, [name]: e.target.value })}
            >
              <option value="">Choose…</option>
              {prop.enum.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          ) : (
            <input
              className="input"
              type={prop.format === "date" ? "date" : prop.type === "number" ? "number" : "text"}
              required={analysis.parameters_schema.required?.includes(name)}
              value={params[name] ?? ""}
              onChange={(e) => setParams({ ...params, [name]: e.target.value })}
            />
          )}
        </Field>
      ))}

      {analysis.inputs.map((input) => {
        const choice = choices[input.key] ?? { fileId: "", sheet: "" };
        const file = files.find((f) => String(f.id) === choice.fileId);
        return (
          <fieldset
            key={input.key}
            className="flex flex-col gap-3 rounded-lg border border-line p-4"
          >
            <legend className="px-1 text-sm font-semibold">{input.label}</legend>
            <p className="text-xs text-muted">Expected: {input.dataset_title}</p>
            <Field label="File">
              <select
                className="input"
                required={input.required}
                value={choice.fileId}
                onChange={(e) => {
                  const next = files.find((f) => String(f.id) === e.target.value);
                  const sheet =
                    next?.sheets.find((s) => s.matches.some((m) => m.dataset === input.dataset)) ??
                    next?.sheets[0];
                  setChoices({
                    ...choices,
                    [input.key]: { fileId: e.target.value, sheet: sheet?.name ?? "" },
                  });
                }}
              >
                <option value="">Choose a file…</option>
                {files.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.filename} (#{f.id})
                  </option>
                ))}
              </select>
            </Field>
            {file && (
              <Field label="Sheet">
                <select
                  className="input"
                  required={input.required}
                  value={choice.sheet}
                  onChange={(e) =>
                    setChoices({ ...choices, [input.key]: { ...choice, sheet: e.target.value } })
                  }
                >
                  {file.sheets.map((s) => (
                    <option key={s.name} value={s.name}>
                      {s.name}
                      {s.matches.some((m) => m.dataset === input.dataset) ? " (recognised)" : ""}
                    </option>
                  ))}
                </select>
              </Field>
            )}
          </fieldset>
        );
      })}

      <StatusMessage message={message} />
      <button type="submit" className="btn-primary self-start" disabled={pending}>
        {pending ? "Starting…" : "Run analysis"}
      </button>
    </form>
  );
}
