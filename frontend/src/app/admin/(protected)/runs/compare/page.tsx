import Link from "next/link";

import { formatValue, type CellValue, type ValueFormat } from "@/lib/dashboard";
import type { RunSummary } from "@/lib/runs";
import { apiGet } from "@/lib/server-api";

export const metadata = { title: "Compare runs" };

interface Comparison {
  a: RunSummary;
  b: RunSummary;
  metrics: {
    label: string;
    format: ValueFormat;
    a: CellValue;
    b: CellValue;
    difference: number | null;
    change: number | null;
  }[];
}

export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{ a?: string; b?: string }>;
}) {
  const { a, b } = await searchParams;
  const response = await apiGet(
    `/api/admin/runs/compare?a=${encodeURIComponent(a ?? "")}&b=${encodeURIComponent(b ?? "")}`,
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    return (
      <p role="alert">
        {typeof body?.detail === "string" ? body.detail : "The runs could not be compared."}{" "}
        <Link href="/admin/runs">Back to runs</Link>
      </p>
    );
  }
  const data = (await response.json()) as Comparison;
  const name = (run: RunSummary) => run.label || `Run #${run.id}`;

  return (
    <div className="max-w-4xl">
      <p className="text-sm text-muted">
        <Link href="/admin/runs">Runs</Link> / compare
      </p>
      <h1 className="mb-6 text-2xl font-semibold">
        {name(data.a)} → {name(data.b)}
      </h1>
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-sm">
          <thead className="bg-panel text-xs uppercase tracking-wide text-muted">
            <tr>
              <th scope="col" className="px-3 py-2 text-left">
                Figure
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                {name(data.a)}
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                {name(data.b)}
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Difference
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Change
              </th>
            </tr>
          </thead>
          <tbody>
            {data.metrics.map((m) => (
              <tr key={m.label} className="border-t border-line">
                <th scope="row" className="px-3 py-2 text-left font-normal">
                  {m.label}
                </th>
                <td className="px-3 py-2 text-right tabular-nums">{formatValue(m.a, m.format)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatValue(m.b, m.format)}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {m.difference === null
                    ? "–"
                    : `${m.difference > 0 ? "+" : ""}${formatValue(m.difference, m.format === "percent" ? "percent" : "number")}`}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {m.change === null
                    ? "–"
                    : `${m.change > 0 ? "Increase" : m.change < 0 ? "Reduction" : "No change"} ${formatValue(Math.abs(m.change), "percent")}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
