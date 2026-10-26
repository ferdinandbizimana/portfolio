"use client";

import { useMemo, useState } from "react";

import { Field, StatusMessage } from "@/components/admin/fields";
import { sendJson } from "@/lib/api-errors";
import type { DataFile } from "@/lib/upload";
import {
  COLOUR_CLASS,
  COLOUR_LABEL,
  formatDifference,
  importProblem,
  type Colour,
  type VarianceCase,
  type VarianceOverview,
  type VarianceStaff,
} from "@/lib/variances";

type Message = { kind: "ok" | "error"; text: string } | null;

const VARIANCE_DATASETS = ["spot_check", "picking_register", "ewm_physical_inventory"];

function filesFor(files: DataFile[], datasets: string[]) {
  return files.filter(
    (f) =>
      f.status === "ready" &&
      f.sheets.some((s) => s.matches.some((m) => datasets.includes(m.dataset))),
  );
}

async function postImport(path: string, fileId: string): Promise<{ ok: boolean; body: unknown }> {
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data_file_id: Number(fileId) }),
  });
  return { ok: response.ok, body: await response.json().catch(() => null) };
}

function ImportPanel({ files, reload }: { files: DataFile[]; reload: () => Promise<void> }) {
  const binFiles = filesFor(files, ["bin_owners"]);
  const varianceFiles = filesFor(files, VARIANCE_DATASETS);
  const [binFile, setBinFile] = useState("");
  const [varianceFile, setVarianceFile] = useState("");
  const [message, setMessage] = useState<Message>(null);
  const [busy, setBusy] = useState(false);

  async function importBins() {
    setBusy(true);
    const { ok, body } = await postImport("/api/admin/variances/bin-list", binFile);
    setBusy(false);
    if (!ok) return setMessage({ kind: "error", text: importProblem(body) });
    const r = body as { staff: string[]; bins: number; unit_bins: number; without_email: string[] };
    setMessage({
      kind: "ok",
      text:
        `Bin list imported: ${r.bins} bins for ${r.staff.length} people` +
        (r.unit_bins ? `; ${r.unit_bins} bins of warehouse units left out` : "") +
        (r.without_email.length ? `; no e-mail for ${r.without_email.join(", ")}` : "") +
        ".",
    });
    await reload();
  }

  async function importVariances() {
    setBusy(true);
    const { ok, body } = await postImport("/api/admin/variances/import", varianceFile);
    setBusy(false);
    if (!ok) return setMessage({ kind: "error", text: importProblem(body) });
    const r = body as {
      source_title: string;
      created: number;
      duplicates: number;
      unassigned: number;
      no_variance: number;
      warnings: string[];
    };
    setMessage({
      kind: "ok",
      text:
        `${r.source_title}: ${r.created} new variances` +
        (r.duplicates ? `, ${r.duplicates} already imported` : "") +
        (r.unassigned ? `, ${r.unassigned} in bins without a responsible person` : "") +
        (r.no_variance ? `, ${r.no_variance} lines without a difference` : "") +
        "." +
        (r.warnings.length
          ? ` ${r.warnings.length} values could not be read and were left empty.`
          : ""),
    });
    await reload();
  }

  return (
    <section aria-label="Import" className="card mb-6 grid gap-4 md:grid-cols-2">
      <div className="flex flex-col gap-2">
        <Field label="Bin list" hint="Storage bins with their responsible person and e-mails.">
          <select className="input" value={binFile} onChange={(e) => setBinFile(e.target.value)}>
            <option value="">Choose an uploaded file…</option>
            {binFiles.map((f) => (
              <option key={f.id} value={f.id}>
                {f.filename} (#{f.id})
              </option>
            ))}
          </select>
        </Field>
        <button
          type="button"
          className="btn-secondary self-start"
          disabled={!binFile || busy}
          onClick={importBins}
        >
          Import bin list
        </button>
      </div>
      <div className="flex flex-col gap-2">
        <Field
          label="Variance file"
          hint="Spot check, picking register or physical inventory document."
        >
          <select
            className="input"
            value={varianceFile}
            onChange={(e) => setVarianceFile(e.target.value)}
          >
            <option value="">Choose an uploaded file…</option>
            {varianceFiles.map((f) => (
              <option key={f.id} value={f.id}>
                {f.filename} (#{f.id})
              </option>
            ))}
          </select>
        </Field>
        <button
          type="button"
          className="btn-primary self-start"
          disabled={!varianceFile || busy}
          onClick={importVariances}
        >
          Create variances and send e-mails
        </button>
      </div>
      <div className="md:col-span-2">
        <StatusMessage message={message} />
        {binFiles.length + varianceFiles.length === 0 && (
          <p className="text-sm text-muted">Upload the files on the Data files page first.</p>
        )}
      </div>
    </section>
  );
}

function StaffRow({ person, reload }: { person: VarianceStaff; reload: () => Promise<void> }) {
  const [email, setEmail] = useState(person.email);
  const [message, setMessage] = useState<Message>(null);

  async function save(change: { email?: string; active?: boolean }) {
    const result = await sendJson("PATCH", `/api/admin/variances/staff/${person.id}`, change);
    setMessage(
      result.ok ? { kind: "ok", text: "Saved." } : { kind: "error", text: result.message },
    );
    if (result.ok) await reload();
  }

  return (
    <tr className="border-t border-line">
      <td className="py-2 pr-3">{person.name}</td>
      <td className="py-2 pr-3 tabular-nums">{person.bins}</td>
      <td className="py-2 pr-3">
        <div className="flex gap-2">
          <input
            className="input min-w-48"
            type="email"
            aria-label={`E-mail of ${person.name}`}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          {email !== person.email && (
            <button type="button" className="btn-secondary" onClick={() => save({ email })}>
              Save
            </button>
          )}
        </div>
        {message?.kind === "error" && <StatusMessage message={message} />}
      </td>
      <td className="py-2">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={person.active}
            onChange={(e) => save({ active: e.target.checked })}
          />
          Receives e-mails
        </label>
      </td>
    </tr>
  );
}

function CaseRow({
  item,
  staff,
  units,
  reload,
}: {
  item: VarianceCase;
  staff: VarianceStaff[];
  units: string[];
  reload: () => Promise<void>;
}) {
  const [closing, setClosing] = useState(false);
  const [reason, setReason] = useState("");
  const [unit, setUnit] = useState("");
  const [message, setMessage] = useState<Message>(null);

  async function act(promise: Promise<{ ok: boolean; message?: string }>) {
    const result = await promise;
    if (result.ok) {
      setClosing(false);
      setMessage(null);
      await reload();
    } else {
      setMessage({ kind: "error", text: result.message ?? "Not saved." });
    }
  }

  async function copyLink() {
    const response = await fetch(`/api/admin/variances/cases/${item.id}/link`, {
      credentials: "same-origin",
    });
    const { link } = (await response.json()) as { link: string };
    await navigator.clipboard?.writeText(link).catch(() => undefined);
    setMessage({ kind: "ok", text: `Link copied: ${link}` });
  }

  return (
    <tr className="border-t border-line align-top">
      <td className="py-2 pr-2">
        <span className={`rounded-md px-2 py-0.5 text-xs ${COLOUR_CLASS[item.colour]}`}>
          {COLOUR_LABEL[item.colour]}
        </span>
      </td>
      <td className="py-2 pr-2 font-mono text-sm">{item.storage_bin}</td>
      <td className="py-2 pr-2 text-sm">
        {item.product} {item.description}
        {item.batch && <span className="text-muted"> · batch {item.batch}</span>}
        <div className="text-xs text-muted">
          {item.source_title}
          {item.found_on ? ` · ${item.found_on}` : ""}
          {item.reference ? ` · ${item.reference}` : ""}
        </div>
      </td>
      <td className="py-2 pr-2 text-right tabular-nums">{formatDifference(item.difference_qty)}</td>
      <td className="py-2 pr-2">
        <select
          className="input text-sm"
          aria-label={`Responsible for bin ${item.storage_bin}`}
          value={item.staff_id ?? ""}
          onChange={(e) =>
            act(
              sendJson("PATCH", `/api/admin/variances/cases/${item.id}`, {
                staff_id: e.target.value ? Number(e.target.value) : null,
              }),
            )
          }
        >
          <option value="">Not assigned</option>
          {staff.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </td>
      <td className="py-2 pr-2 text-sm tabular-nums">{item.days_open} d</td>
      <td className="py-2 text-sm">
        {item.status === "corrected" ? (
          <div>
            <p>{item.reason}</p>
            <p className="text-xs text-muted">
              {item.responsible_unit}
              {item.corrected_by ? ` · ${item.corrected_by}` : ""}
            </p>
            <button
              type="button"
              className="text-xs underline"
              onClick={() => act(sendJson("POST", `/api/admin/variances/cases/${item.id}/reopen`))}
            >
              Reopen
            </button>
          </div>
        ) : closing ? (
          <form
            className="flex flex-col gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              act(
                sendJson("POST", `/api/admin/variances/cases/${item.id}/correct`, {
                  reason,
                  responsible_unit: unit,
                }),
              );
            }}
          >
            <input
              className="input"
              required
              minLength={3}
              aria-label="Reason"
              placeholder="Reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <select
              className="input"
              required
              aria-label="Responsible unit"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
            >
              <option value="">Responsible unit…</option>
              {units.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
            <div className="flex gap-2">
              <button type="submit" className="btn-primary">
                Save
              </button>
              <button type="button" className="btn-secondary" onClick={() => setClosing(false)}>
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-secondary" onClick={() => setClosing(true)}>
              Mark corrected
            </button>
            <button type="button" className="btn-secondary" onClick={copyLink}>
              Copy link
            </button>
          </div>
        )}
        <StatusMessage message={message} />
      </td>
    </tr>
  );
}

export function VarianceBoard({
  overview: initial,
  files,
}: {
  overview: VarianceOverview;
  files: DataFile[];
}) {
  // After each change the board reloads its data from the API, so what it shows
  // never depends on a page refresh finishing.
  const [overview, setOverview] = useState(initial);
  async function reload() {
    const response = await fetch("/api/admin/variances", { credentials: "same-origin" });
    if (response.ok) setOverview((await response.json()) as VarianceOverview);
  }
  const [colour, setColour] = useState<"" | Colour>("");
  const [person, setPerson] = useState("");
  const [source, setSource] = useState("");

  const cases = useMemo(
    () =>
      overview.cases.filter(
        (c) =>
          (!colour || c.colour === colour) &&
          (!person || String(c.staff_id ?? 0) === person) &&
          (!source || c.source === source),
      ),
    [overview.cases, colour, person, source],
  );

  return (
    <div>
      <section aria-label="By person" className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {overview.summary.length === 0 && (
          <p className="text-muted">No variances yet. Import the bin list, then a variance file.</p>
        )}
        {overview.summary.map((s) => (
          <div key={s.staff_id ?? "none"} className="card">
            <p className="font-semibold">{s.name}</p>
            <p className="mt-1 flex flex-wrap gap-2 text-sm">
              <span className={`rounded-md px-2 py-0.5 ${COLOUR_CLASS.red}`}>
                {s.overdue} overdue
              </span>
              <span className={`rounded-md px-2 py-0.5 ${COLOUR_CLASS.amber}`}>
                {s.open - s.overdue} open
              </span>
              <span className={`rounded-md px-2 py-0.5 ${COLOUR_CLASS.green}`}>
                {s.corrected} corrected
              </span>
            </p>
          </div>
        ))}
      </section>

      <ImportPanel files={files} reload={reload} />

      <section aria-label="Variances" className="mb-8">
        <div className="mb-3 flex flex-wrap items-end gap-3">
          <h2 className="mr-auto text-lg font-semibold">Variances</h2>
          <Field label="Status">
            <select
              className="input"
              value={colour}
              onChange={(e) => setColour(e.target.value as "" | Colour)}
            >
              <option value="">All</option>
              <option value="red">Overdue</option>
              <option value="amber">Open</option>
              <option value="green">Corrected</option>
            </select>
          </Field>
          <Field label="Responsible">
            <select className="input" value={person} onChange={(e) => setPerson(e.target.value)}>
              <option value="">Everyone</option>
              {overview.staff.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
              <option value="0">Not assigned</option>
            </select>
          </Field>
          <Field label="Source">
            <select className="input" value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">All sources</option>
              {Object.entries(overview.sources).map(([key, title]) => (
                <option key={key} value={key}>
                  {title}
                </option>
              ))}
            </select>
          </Field>
          <a className="btn-secondary" href="/api/admin/variances/export.xlsx">
            Download Excel
          </a>
        </div>
        <p className="mb-2 text-sm text-muted">
          {cases.length} of {overview.total} variances
          {overview.total > overview.cases.length
            ? ` (the newest ${overview.cases.length} shown)`
            : ""}
        </p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[56rem] text-left">
            <thead className="text-xs text-muted">
              <tr>
                <th className="pb-2">Status</th>
                <th className="pb-2">Bin</th>
                <th className="pb-2">Product</th>
                <th className="pb-2 text-right">Difference</th>
                <th className="pb-2">Responsible</th>
                <th className="pb-2">Open</th>
                <th className="pb-2">Correction</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <CaseRow
                  key={c.id}
                  item={c}
                  staff={overview.staff}
                  units={overview.units}
                  reload={reload}
                />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-label="Responsible people">
        <h2 className="mb-2 text-lg font-semibold">Responsible people</h2>
        <p className="mb-3 text-sm text-muted">
          From the bin list ({overview.bins} bins). Correct an e-mail here if needed.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="text-xs text-muted">
              <tr>
                <th className="pb-2">Name</th>
                <th className="pb-2">Bins</th>
                <th className="pb-2">E-mail</th>
                <th className="pb-2">E-mails</th>
              </tr>
            </thead>
            <tbody>
              {overview.staff.map((s) => (
                <StaffRow key={s.id} person={s} reload={reload} />
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
