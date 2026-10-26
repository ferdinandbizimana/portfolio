import { describe, expect, it } from "vitest";

import { needsReason, rwf } from "./expiry";

describe("expiry follow-up", () => {
  it("formats money without decimals", () => {
    expect(rwf(1234567.6)).toBe("RWF 1,234,568");
  });
  it("asks for the reason only for the last root cause (Other)", () => {
    const causes = ["Demand", "Other (give the reason)"];
    expect(needsReason(causes, "Other (give the reason)")).toBe(true);
    expect(needsReason(causes, "Demand")).toBe(false);
    expect(needsReason(causes, "")).toBe(false);
  });
});
