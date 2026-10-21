import { describe, expect, it } from "vitest";

import { formatMonth, formatPeriod, parseItems, slugify } from "./portfolio";

describe("portfolio helpers", () => {
  it("formats months and periods", () => {
    expect(formatMonth("2023-07")).toBe("Jul 2023");
    expect(formatPeriod("2021-03", "2023-06")).toBe("Mar 2021 – Jun 2023");
    expect(formatPeriod("2023-07", null)).toBe("Jul 2023 – Present");
  });

  it("keeps an unexpected month as it is", () => {
    expect(formatMonth("soon")).toBe("soon");
  });

  it("splits skills by line or comma and drops blanks and duplicates", () => {
    expect(parseItems("SAP MM\n EWM ,FI\n\nEWM")).toEqual(["SAP MM", "EWM", "FI"]);
  });

  it("makes URL slugs from titles", () => {
    expect(slugify("Year-end Stock Count 2026!")).toBe("year-end-stock-count-2026");
    expect(slugify("  Réconciliation   des stocks ")).toBe("reconciliation-des-stocks");
    expect(slugify("---")).toBe("");
  });
});
