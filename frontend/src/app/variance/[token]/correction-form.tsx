"use client";

import { useState } from "react";

import { Field, StatusMessage } from "@/components/admin/fields";
import { sendJson } from "@/lib/api-errors";
import {
  COLOUR_CLASS,
  COLOUR_LABEL,
  formatDifference,
  statusLine,
  type PublicVariance,
} from "@/lib/variances";

export function CorrectionForm({ token, initial }: { token: string; initial: PublicVariance }) {
  const [variance, setVariance] = useState(initial);
  const [rootCause, setRootCause] = useState("");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [unit, setUnit] = useState("");
  const [action, setAction] = useState("");
  const [name, setName] = useState(initial.responsible);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    const result = await sendJson<PublicVariance>(
      "POST",
      `/api/public/variances/${encodeURIComponent(token)}/correct`,
      {
        root_cause: rootCause,
        corrected_qty: quantity === "" ? null : Number(quantity),
        reason,
        responsible_unit: unit,
        action_taken: action,
        corrected_by: name,
      },
    );
    setSaving(false);
    if (result.ok) {
      setVariance(result.data);
      setMessage({ kind: "ok", text: "Thank you: the variance is recorded as corrected." });
    } else {
      setMessage({ kind: "error", text: result.message });
    }
  }

  const v = variance;
  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="text-sm text-muted">{v.source_title}</p>
        <h1 className="text-2xl font-semibold">Stock variance in bin {v.storage_bin}</h1>
        <p className={`mt-2 inline-block rounded-md px-2 py-1 text-sm ${COLOUR_CLASS[v.colour]}`}>
          {COLOUR_LABEL[v.colour]}: {statusLine(v, v.overdue_days)}
        </p>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted">Product</dt>
        <dd>
          {v.product} {v.description}
        </dd>
        {v.batch && (
          <>
            <dt className="text-muted">Batch</dt>
            <dd>{v.batch}</dd>
          </>
        )}
        {v.system_qty !== null && (
          <>
            <dt className="text-muted">System quantity</dt>
            <dd>{v.system_qty}</dd>
          </>
        )}
        {v.counted_qty !== null && (
          <>
            <dt className="text-muted">Counted quantity</dt>
            <dd>{v.counted_qty}</dd>
          </>
        )}
        <dt className="text-muted">Difference</dt>
        <dd className="font-semibold">{formatDifference(v.difference_qty)}</dd>
        {v.found_on && (
          <>
            <dt className="text-muted">Found on</dt>
            <dd>{v.found_on}</dd>
          </>
        )}
        {v.responsible && (
          <>
            <dt className="text-muted">Responsible</dt>
            <dd>{v.responsible}</dd>
          </>
        )}
      </dl>

      {v.status === "corrected" ? (
        <section aria-label="Correction" className="card flex flex-col gap-1 text-sm">
          <StatusMessage message={message} />
          {v.root_cause && (
            <p>
              <span className="text-muted">Root cause: </span>
              {v.root_cause}
            </p>
          )}
          <p>
            <span className="text-muted">Reason: </span>
            {v.reason}
          </p>
          {v.corrected_qty !== null && (
            <p>
              <span className="text-muted">Quantity corrected: </span>
              {v.corrected_qty}
            </p>
          )}
          <p>
            <span className="text-muted">Responsible unit: </span>
            {v.responsible_unit}
          </p>
          {v.action_taken && (
            <p>
              <span className="text-muted">Action taken: </span>
              {v.action_taken}
            </p>
          )}
          {v.corrected_by && (
            <p>
              <span className="text-muted">Corrected by: </span>
              {v.corrected_by}
            </p>
          )}
        </section>
      ) : (
        <form onSubmit={submit} className="card flex flex-col gap-4">
          <h2 className="font-semibold">Record the correction</h2>
          <Field label="Root cause">
            <select
              className="input"
              required
              value={rootCause}
              onChange={(e) => setRootCause(e.target.value)}
            >
              <option value="">Choose…</option>
              {v.root_causes.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Reason for the variance" hint="What happened, in your words.">
            <textarea
              className="input"
              required
              minLength={3}
              maxLength={2000}
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
          <Field label="Responsible unit" hint="Where the error was made, for accountability.">
            <select
              className="input"
              required
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
            >
              <option value="">Choose…</option>
              {v.units.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
          </Field>
          <Field
            label="Quantity corrected"
            hint={`Optional. The difference found was ${formatDifference(v.difference_qty)}.`}
          >
            <input
              className="input"
              type="number"
              step="any"
              inputMode="decimal"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
          </Field>
          <Field label="Action taken" hint="For example: stock moved back, posting corrected.">
            <textarea
              className="input"
              maxLength={2000}
              rows={2}
              value={action}
              onChange={(e) => setAction(e.target.value)}
            />
          </Field>
          <Field label="Your name">
            <input
              className="input"
              maxLength={200}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          <StatusMessage message={message} />
          <button type="submit" className="btn-primary self-start" disabled={saving}>
            {saving ? "Saving…" : "Mark as corrected"}
          </button>
        </form>
      )}
    </div>
  );
}
