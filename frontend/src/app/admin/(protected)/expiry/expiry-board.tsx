"use client";

import Link from "next/link";
import { useState } from "react";

import { StatusMessage } from "@/components/admin/fields";
import { postJson } from "@/lib/api-errors";
import { rwf, type ExpiryOverview, type ExpiryRunRow } from "@/lib/expiry";

type Message = { kind: "ok" | "error"; text: string } | null;

function RunCard({
  row,
  mailReady,
  reload,
}: {
  row: ExpiryRunRow;
  mailReady: boolean;
  reload: () => Promise<void>;
}) {
  const [message, setMessage] = useState<Message>(null);
  const [busy, setBusy] = useState(false);
  const review = row.review;

  async function prepare() {
    setBusy(true);
    const result = await postJson(`/api/admin/expiry/runs/${row.run_id}`);
    setBusy(false);
    if (!result.ok) return setMessage({ kind: "error", text: result.message });
    await reload();
  }

  async function send() {
    if (!review) return;
    setBusy(true);
    const result = await postJson(`/api/admin/expiry/reviews/${review.id}/send`);
    setBusy(false);
    setMessage(
      result.ok
        ? { kind: "ok", text: "The e-mail is being sent." }
        : { kind: "error", text: result.message },
    );
  }

  async function copy() {
    if (!review) return;
    try {
      await navigator.clipboard.writeText(review.link);
      setMessage({ kind: "ok", text: "Link copied." });
    } catch {
      setMessage({ kind: "ok", text: review.link });
    }
  }

  return (
    <li className="card flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold">
          <Link href={`/admin/runs/${row.run_id}`} className="underline">
            {row.label || `Run ${row.run_id}`}
          </Link>
        </h2>
        <span className="text-sm text-muted">
          {row.opening_date} to {row.closing_date}
        </span>
      </div>
      {review ? (
        <>
          <p className="text-sm">
            Expired: {rwf(review.expired_value)} in {review.items} items ·{" "}
            <strong>
              {review.justified} of {review.items} justified
            </strong>
            {review.mailed_month ? ` · e-mailed for ${review.mailed_month}` : " · not e-mailed yet"}
          </p>
          <div className="flex flex-wrap gap-2">
            <a className="btn-secondary" href={review.link} target="_blank" rel="noopener">
              Open the pharmacist&apos;s page
            </a>
            <button type="button" className="btn-secondary" onClick={copy}>
              Copy link
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={send}
              disabled={busy || !mailReady}
              title={mailReady ? undefined : "E-mail is not set up on the server"}
            >
              Send the e-mail now
            </button>
            <a
              className="btn-secondary"
              href={`/api/admin/expiry/reviews/${review.id}/justifications.xlsx`}
            >
              Justifications (Excel)
            </a>
            <a
              className="btn-secondary"
              href={`/api/admin/expiry/reviews/${review.id}/justifications.html`}
            >
              Justifications dashboard (HTML)
            </a>
          </div>
        </>
      ) : (
        <button type="button" className="btn-primary self-start" onClick={prepare} disabled={busy}>
          Prepare the follow-up
        </button>
      )}
      <StatusMessage message={message} />
    </li>
  );
}

export function ExpiryBoard({ initial }: { initial: ExpiryOverview }) {
  const [overview, setOverview] = useState(initial);

  async function reload() {
    const response = await fetch("/api/admin/expiry", { credentials: "same-origin" });
    if (response.ok) setOverview((await response.json()) as ExpiryOverview);
  }

  return (
    <div className="flex flex-col gap-4">
      {!overview.mail_ready && (
        <p role="status" className="text-sm text-muted">
          E-mail is not set up on the server (SMTP and EXPIRY_MAIL_TO): the monthly e-mail is not
          sent, but the pharmacist&apos;s page works with its link.
        </p>
      )}
      {overview.runs.length === 0 ? (
        <p>
          No expiry monitoring run yet. Run the analysis &quot;Expiry monitoring&quot; on the
          opening and closing ZSTOCKREPORT of a period first.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {overview.runs.map((row) => (
            <RunCard key={row.run_id} row={row} mailReady={overview.mail_ready} reload={reload} />
          ))}
        </ul>
      )}
    </div>
  );
}
