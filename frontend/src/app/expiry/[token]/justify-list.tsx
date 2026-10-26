"use client";

import { useState } from "react";

import { StatusMessage } from "@/components/admin/fields";
import { sendJson } from "@/lib/api-errors";
import { needsReason, rwf, type ExpiryDetail, type ExpiryItem } from "@/lib/expiry";

type Message = { kind: "ok" | "error"; text: string } | null;

function ItemForm({
  path,
  item,
  rootCauses,
  name,
  onSaved,
}: {
  path: string;
  item: ExpiryItem;
  rootCauses: string[];
  name: string;
  onSaved: (item: ExpiryItem) => void;
}) {
  const [cause, setCause] = useState(item.root_cause);
  const [reason, setReason] = useState(item.reason);
  const [message, setMessage] = useState<Message>(null);
  const [saving, setSaving] = useState(false);
  const label = `${item.description || item.material}`;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    const result = await sendJson<ExpiryItem>("POST", `${path}/items/${item.id}`, {
      root_cause: cause,
      reason,
      justified_by: name,
    });
    setSaving(false);
    if (result.ok) {
      onSaved(result.data);
      setMessage({ kind: "ok", text: "Saved." });
    } else setMessage({ kind: "error", text: result.message });
  }

  return (
    <form
      onSubmit={save}
      aria-label={`Justification for ${label}`}
      className="card flex flex-col gap-2"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold">
          {label} <span className="text-sm font-normal text-muted">[{item.material}]</span>
        </h3>
        <span className="font-semibold">{rwf(item.value)}</span>
      </div>
      <p className="text-sm text-muted">
        {item.owner} · plants {item.plants}
      </p>
      <label className="flex flex-col gap-1 text-sm">
        Root cause
        <select className="input" required value={cause} onChange={(e) => setCause(e.target.value)}>
          <option value="">Choose…</option>
          {rootCauses.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {needsReason(rootCauses, cause) ? "Reason (required)" : "Reason and action taken"}
        <textarea
          className="input"
          rows={2}
          maxLength={4000}
          required={needsReason(rootCauses, cause)}
          minLength={needsReason(rootCauses, cause) ? 3 : undefined}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        {item.justified_at && (
          <span className="text-sm text-muted">
            Justified{item.justified_by ? ` by ${item.justified_by}` : ""}
          </span>
        )}
        <StatusMessage message={message} />
      </div>
    </form>
  );
}

export function JustifyList({ token, detail }: { token: string; detail: ExpiryDetail }) {
  const [items, setItems] = useState(detail.items);
  const [name, setName] = useState("");
  const path = `/api/public/expiry/${encodeURIComponent(token)}`;
  const totals = detail.outlook.reduce(
    (t, p) => ({
      expired: t.expired + p.expired,
      m3: t.m3 + p.within_3_months,
      m6: t.m6 + p.three_to_6_months,
    }),
    { expired: 0, m3: 0, m6: 0 },
  );
  const done = items.filter((i) => i.root_cause).length;
  const date = new Date(detail.review.closing_date).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="text-sm text-muted">Rwanda Medical Supply · expiry follow-up</p>
        <h1 className="text-2xl font-semibold">Stock expiry position at {date}</h1>
      </div>

      <section aria-labelledby="outlook-heading" className="flex flex-col gap-2">
        <h2 id="outlook-heading" className="text-lg font-semibold">
          Value per plant
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-muted">
                <th className="py-1 pr-3">Plant</th>
                <th className="py-1 pr-3 text-right">Expired</th>
                <th className="py-1 pr-3 text-right">Within 3 months</th>
                <th className="py-1 text-right">3 to 6 months</th>
              </tr>
            </thead>
            <tbody>
              {detail.outlook.map((p) => (
                <tr key={p.plant} className="border-b border-line">
                  <td className="py-1 pr-3">
                    {p.plant} {p.plant_name}
                  </td>
                  <td className="py-1 pr-3 text-right">{rwf(p.expired)}</td>
                  <td className="py-1 pr-3 text-right">{rwf(p.within_3_months)}</td>
                  <td className="py-1 text-right">{rwf(p.three_to_6_months)}</td>
                </tr>
              ))}
              <tr className="font-semibold">
                <td className="py-1 pr-3">Total</td>
                <td className="py-1 pr-3 text-right">{rwf(totals.expired)}</td>
                <td className="py-1 pr-3 text-right">{rwf(totals.m3)}</td>
                <td className="py-1 text-right">{rwf(totals.m6)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="items-heading" className="flex flex-col gap-3">
        <h2 id="items-heading" className="text-lg font-semibold">
          Expired items to justify ({done} of {items.length} done)
        </h2>
        <p className="text-sm text-muted">
          For each expired item choose the root cause. When it is &quot;Other&quot;, write the
          reason. Each item is saved on its own.
        </p>
        <label className="flex max-w-sm flex-col gap-1 text-sm">
          Your name
          <input
            className="input"
            maxLength={200}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        {items.length === 0 && <p>No expired stock: nothing to justify.</p>}
        {items.map((item) => (
          <ItemForm
            key={item.id}
            path={path}
            item={item}
            rootCauses={detail.root_causes}
            name={name}
            onSaved={(saved) => setItems((all) => all.map((i) => (i.id === saved.id ? saved : i)))}
          />
        ))}
      </section>
    </div>
  );
}
