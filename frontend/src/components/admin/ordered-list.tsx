"use client";

import type { ReactNode } from "react";

/** A list of items with Move up / Move down / Edit / Delete buttons. */
export function OrderedList<T extends { id: number }>({
  items,
  render,
  onEdit,
  onDelete,
  onMove,
  disabled,
}: {
  items: T[];
  render: (item: T) => ReactNode;
  onEdit: (item: T) => void;
  onDelete: (item: T) => void;
  onMove: (ids: number[]) => void;
  disabled: boolean;
}) {
  function move(index: number, delta: number) {
    const ids = items.map((i) => i.id);
    const target = index + delta;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target]!, ids[index]!];
    onMove(ids);
  }

  return (
    <ul className="flex flex-col gap-2">
      {items.map((item, index) => (
        <li
          key={item.id}
          className="flex flex-col gap-2 rounded-lg border border-line p-3 sm:flex-row sm:items-center"
        >
          <div className="flex-1">{render(item)}</div>
          <div className="flex flex-wrap gap-1">
            <button
              type="button"
              className="btn-secondary"
              aria-label="Move up"
              disabled={disabled || index === 0}
              onClick={() => move(index, -1)}
            >
              ↑
            </button>
            <button
              type="button"
              className="btn-secondary"
              aria-label="Move down"
              disabled={disabled || index === items.length - 1}
              onClick={() => move(index, 1)}
            >
              ↓
            </button>
            <button type="button" className="btn-secondary" onClick={() => onEdit(item)}>
              Edit
            </button>
            <button
              type="button"
              className="btn-secondary text-danger"
              disabled={disabled}
              onClick={() => onDelete(item)}
            >
              Delete
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
