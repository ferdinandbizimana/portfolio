"use client";

import { useId, useMemo, useState } from "react";

import {
  distinctValues,
  filterRows,
  formatValue,
  type Dashboard,
  type Table,
} from "@/lib/dashboard";

import { DataTable } from "./data-table";
import { EChart } from "./echart";

/** Renders a dashboard: KPI tiles, filters and search, charts, tables and checks. */
export function DashboardView({
  dashboard,
  showChecks = true,
}: {
  dashboard: Dashboard;
  showChecks?: boolean;
}) {
  const filterKeys = useMemo(
    () => [...new Set(dashboard.tables.flatMap((t) => t.filters))],
    [dashboard.tables],
  );
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [search, setSearch] = useState("");
  const idPrefix = useId();
  const hasSearch = dashboard.tables.some((t) => t.searchable.length > 0);
  const options = useMemo(() => {
    const result: Record<string, string[]> = {};
    for (const key of filterKeys) {
      const source = dashboard.tables.find((t) => t.filters.includes(key));
      result[key] = source ? distinctValues(source.rows, key) : [];
    }
    return result;
  }, [dashboard.tables, filterKeys]);

  const filtered = useMemo(() => {
    const byId: Record<string, ReturnType<typeof filterRows>> = {};
    for (const table of dashboard.tables) byId[table.id] = filterRows(table, filters, search);
    return byId;
  }, [dashboard.tables, filters, search]);

  const tableById = (id: string): Table | undefined => dashboard.tables.find((t) => t.id === id);
  const active = Object.values(filters).some(Boolean) || search.trim() !== "";

  return (
    <div className="flex flex-col gap-8">
      {dashboard.kpis.length > 0 && (
        <section aria-label="Key figures" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {dashboard.kpis.map((kpi) => (
            <div key={kpi.label} className="rounded-lg border border-line p-4">
              <p className="text-xs uppercase tracking-wide text-muted">{kpi.label}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {formatValue(kpi.value, kpi.format)}
                {kpi.unit && (
                  <span className="ml-1 text-sm font-normal text-muted">{kpi.unit}</span>
                )}
              </p>
              {kpi.note && <p className="mt-1 text-xs text-muted">{kpi.note}</p>}
            </div>
          ))}
        </section>
      )}

      {(filterKeys.length > 0 || hasSearch) && (
        <section
          aria-label="Filters"
          className="flex flex-wrap items-end gap-3 rounded-lg bg-panel p-3"
        >
          {hasSearch && (
            <div className="flex min-w-48 flex-1 flex-col gap-1 text-xs font-medium">
              <label htmlFor={`${idPrefix}-search`}>Search</label>
              <input
                id={`${idPrefix}-search`}
                type="search"
                className="input"
                value={search}
                placeholder="Name or code"
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          )}
          {filterKeys.map((key) => (
            <div key={key} className="flex min-w-40 flex-col gap-1 text-xs font-medium">
              <label htmlFor={`${idPrefix}-filter-${key}`}>{key}</label>
              <select
                id={`${idPrefix}-filter-${key}`}
                className="input"
                value={filters[key] ?? ""}
                onChange={(e) => setFilters((f) => ({ ...f, [key]: e.target.value }))}
              >
                <option value="">All</option>
                {options[key]?.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </div>
          ))}
          {active && (
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setFilters({});
                setSearch("");
              }}
            >
              Reset
            </button>
          )}
        </section>
      )}

      {dashboard.charts.length > 0 && (
        <section aria-label="Charts" className="grid gap-4 lg:grid-cols-2">
          {dashboard.charts.map((chart) => {
            const table = tableById(chart.table);
            return table ? (
              <EChart key={chart.id} chart={chart} rows={filtered[table.id] ?? []} />
            ) : null;
          })}
        </section>
      )}

      {dashboard.tables.map((table) => (
        <section key={table.id} aria-labelledby={`table-${table.id}`}>
          <h2 id={`table-${table.id}`} className="mb-2 text-lg font-semibold">
            {table.title}
          </h2>
          {table.note && <p className="mb-2 text-sm text-muted">{table.note}</p>}
          <DataTable table={table} rows={filtered[table.id] ?? []} />
        </section>
      ))}

      {showChecks && dashboard.checks.length > 0 && (
        <section aria-labelledby="checks-heading">
          <h2 id="checks-heading" className="mb-2 text-lg font-semibold">
            Checks ({dashboard.checks.filter((c) => c.passed).length} of {dashboard.checks.length}{" "}
            passed)
          </h2>
          <ul className="flex flex-col gap-1 text-sm">
            {dashboard.checks.map((check) => (
              <li key={check.key} className="flex flex-wrap items-baseline gap-2">
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    check.passed ? "bg-success-soft text-success" : "bg-danger-soft text-danger"
                  }`}
                >
                  {check.passed ? "Passed" : "Failed"}
                </span>
                <span>{check.label}</span>
                {!check.passed && (
                  <span className="text-muted">
                    expected {formatValue(check.expected, "number")}, got{" "}
                    {formatValue(check.actual, "number")}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {dashboard.notes.length > 0 && (
        <section className="text-sm text-muted">
          {dashboard.notes.map((note) => (
            <p key={note}>{note}</p>
          ))}
        </section>
      )}
    </div>
  );
}
