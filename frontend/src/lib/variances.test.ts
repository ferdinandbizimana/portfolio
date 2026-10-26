import { describe, expect, it } from "vitest";

import { formatDifference, importProblem, statusLine } from "./variances";

describe("variances", () => {
  it("shows the sign of a difference", () => {
    expect(formatDifference(-2)).toBe("-2");
    expect(formatDifference(5)).toBe("+5");
    expect(formatDifference(1.5)).toBe("+1.50");
    expect(formatDifference(0)).toBe("0");
  });

  it("describes open, overdue and corrected cases", () => {
    expect(statusLine({ colour: "amber", days_open: 1 }, 2)).toBe(
      "Open for 1 day (overdue after 2)",
    );
    expect(statusLine({ colour: "red", days_open: 3 }, 2)).toBe(
      "Overdue: open for 3 days (more than 2)",
    );
    expect(statusLine({ colour: "green", days_open: 4 }, 2)).toBe("Corrected");
  });

  it("explains an import problem", () => {
    expect(importProblem({ detail: { message: "Not a bin list.", errors: ["row 3"] } })).toBe(
      "Not a bin list. row 3",
    );
    expect(importProblem({ detail: "File not found." })).toBe("File not found.");
    expect(importProblem(null)).toBe("The file could not be imported.");
  });
});
