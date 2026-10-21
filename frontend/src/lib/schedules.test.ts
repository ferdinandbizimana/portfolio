import { describe, expect, it } from "vitest";

import { describeParameter, describeWhen, isDateRule } from "./schedules";

describe("describeWhen", () => {
  it("names the days and time", () => {
    const all = [0, 1, 2, 3, 4, 5, 6];
    expect(describeWhen({ trigger: "daily", run_time: "06:00", weekdays: all })).toBe(
      "Every day at 06:00",
    );
    expect(describeWhen({ trigger: "daily", run_time: "06:30", weekdays: [4, 0, 1, 2, 3] })).toBe(
      "Mon–Fri at 06:30",
    );
    expect(describeWhen({ trigger: "daily", run_time: "07:00", weekdays: [3, 0] })).toBe(
      "Mon, Thu at 07:00",
    );
    expect(describeWhen({ trigger: "new_files", run_time: "06:00", weekdays: all })).toBe(
      "When new files arrive",
    );
  });
});

describe("parameters", () => {
  const rules = { previous_month_end: "Last day of the previous month" };
  it("shows rules by their label and fixed values as they are", () => {
    expect(isDateRule({ rule: "x" })).toBe(true);
    expect(isDateRule("2026-06-30")).toBe(false);
    expect(describeParameter({ rule: "previous_month_end" }, rules)).toBe(
      "Last day of the previous month",
    );
    expect(describeParameter("2026-06-30", rules)).toBe("2026-06-30");
  });
});
