import { describe, expect, it } from "vitest";

import { compactNumber, distinctValues, filterRows, formatValue, type Table } from "./dashboard";

const TABLE: Table = {
  id: "lines",
  title: "Lines",
  columns: [
    { key: "Plant", label: "Plant", format: "text" },
    { key: "Material", label: "Material", format: "text" },
    { key: "Value", label: "Value", format: "money" },
  ],
  rows: [
    { Plant: "P10", Material: "Gloves", Value: 100 },
    { Plant: "P2", Material: "Syringe", Value: -5 },
    { Plant: "P10", Material: "Test kit", Value: 20 },
  ],
  level: "detail",
  filters: ["Plant"],
  searchable: ["Material"],
  note: "",
};

describe("dashboard helpers", () => {
  it("formats values like the reports", () => {
    expect(formatValue(1234567.4, "money")).toBe("1,234,567");
    expect(formatValue(-1500, "money")).toBe("(1,500)");
    expect(formatValue(0.0891, "percent")).toBe("8.9%");
    expect(formatValue(2.345, "number")).toBe("2.35");
    expect(formatValue("2026-06-30", "date")).toBe("30.06.2026");
    expect(formatValue(null, "money")).toBe("");
  });

  it("abbreviates numbers for chart axes", () => {
    expect(compactNumber(53_495_584_236)).toBe("53.5bn");
    expect(compactNumber(-2_500_000)).toBe("-2.5M");
    expect(compactNumber(350_000)).toBe("350K");
    expect(compactNumber(12)).toBe("12");
  });

  it("filters by drop-down values and search text", () => {
    expect(filterRows(TABLE, { Plant: "P10" }, "").map((r) => r.Material)).toEqual([
      "Gloves",
      "Test kit",
    ]);
    expect(filterRows(TABLE, {}, "syr").map((r) => r.Material)).toEqual(["Syringe"]);
    // Search only looks in the searchable columns.
    expect(filterRows(TABLE, {}, "P2")).toEqual([]);
    // A filter on a column the table does not have is ignored.
    expect(filterRows(TABLE, { Program: "TB" }, "")).toHaveLength(3);
  });

  it("lists filter values in natural order", () => {
    expect(distinctValues(TABLE.rows, "Plant")).toEqual(["P2", "P10"]);
  });
});
