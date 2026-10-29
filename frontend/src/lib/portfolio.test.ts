import { describe, expect, it } from "vitest";

import {
  durationText,
  formatMonth,
  formatPeriod,
  initials,
  monthOf,
  parseItems,
  slugify,
  withProfileDefaults,
  yearsOfExperience,
  type Portfolio,
} from "./portfolio";

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

describe("personal brand helpers", () => {
  it("counts whole years from the first role", () => {
    const roles = [
      { start_month: "2019-01", end_month: "2022-06" },
      { start_month: "2022-07", end_month: null },
    ];
    expect(yearsOfExperience(roles, "2026-10")).toBe(7); // Jan 2019 to Oct 2026: 7 yrs 10 mos
    expect(yearsOfExperience(roles, "2019-06")).toBe(0);
    expect(yearsOfExperience([], "2026-10")).toBe(0);
  });

  it("writes the length of a role with both months included", () => {
    expect(durationText("2022-07", "2024-10", "2026-10")).toBe("2 yrs 4 mos");
    expect(durationText("2026-01", null, "2026-11")).toBe("11 mos");
    expect(durationText("2025-11", "2026-10", "2026-10")).toBe("1 yr");
    expect(durationText("2026-10", null, "2026-10")).toBe("1 mo");
  });

  it("makes a monogram and a month", () => {
    expect(initials("Ferdinand Bizimana")).toBe("FB");
    expect(monthOf(new Date(2026, 9, 29))).toBe("2026-10");
  });
});

it("fills the profile fields a cached older response lacks", () => {
  const old = {
    profile: { full_name: "F B" },
    experience: [],
    skills: [],
    projects: [],
  } as unknown as Portfolio;
  const profile = withProfileDefaults(old).profile;
  expect(profile.highlights).toEqual([]);
  expect(profile.languages).toEqual([]);
  expect(profile.availability).toBe("");
});
