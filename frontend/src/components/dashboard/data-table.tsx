"use client";

import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { formatValue, type Row, type Table } from "@/lib/dashboard";

const NUMERIC = new Set(["number", "integer", "money", "percent"]);

export function DataTable({ table, rows }: { table: Table; rows: Row[] }) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const columns = useMemo<ColumnDef<Row>[]>(
    () =>
      table.columns.map((column) => ({
        id: column.key,
        accessorFn: (row) => row[column.key],
        header: column.label,
        cell: (info) => formatValue(info.getValue() as Row[string], column.format),
        sortUndefined: "last",
        meta: { numeric: NUMERIC.has(column.format) },
      })),
    [table.columns],
  );
  // TanStack Table is not compatible with the React Compiler's memoisation; React
  // skips optimising this one component, which is fine for a table.
  // eslint-disable-next-line react-hooks/incompatible-library
  const grid = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 25 } },
  });
  const page = grid.getState().pagination;

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-left text-sm">
          <thead className="bg-panel text-xs text-muted">
            {grid.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => {
                  const numeric = (header.column.columnDef.meta as { numeric?: boolean })?.numeric;
                  const sorted = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      aria-sort={
                        sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : "none"
                      }
                      className={`px-3 py-2 ${numeric ? "text-right" : ""}`}
                    >
                      <button
                        type="button"
                        className="font-semibold uppercase tracking-wide"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {sorted === "asc" ? " ▲" : sorted === "desc" ? " ▼" : ""}
                      </button>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {grid.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-t border-line">
                {row.getVisibleCells().map((cell) => {
                  const numeric = (cell.column.columnDef.meta as { numeric?: boolean })?.numeric;
                  return (
                    <td
                      key={cell.id}
                      className={`px-3 py-1.5 ${numeric ? "whitespace-nowrap text-right tabular-nums" : ""}`}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  );
                })}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={table.columns.length} className="px-3 py-4 text-center text-muted">
                  No lines match the filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {grid.getPageCount() > 1 && (
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
          <button
            type="button"
            className="btn-secondary"
            onClick={() => grid.previousPage()}
            disabled={!grid.getCanPreviousPage()}
          >
            Previous
          </button>
          <span>
            Lines {page.pageIndex * page.pageSize + 1}–
            {Math.min((page.pageIndex + 1) * page.pageSize, rows.length)} of {rows.length}
          </span>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => grid.nextPage()}
            disabled={!grid.getCanNextPage()}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
