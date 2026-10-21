import { describe, expect, it } from "vitest";

import { actionLabel, detailText, formatDateTime, isWarning } from "./audit";

describe("audit helpers", () => {
  it("labels known actions in plain English and passes unknown ones through", () => {
    expect(actionLabel("auth.login")).toBe("Signed in");
    expect(actionLabel("upload.created")).toBe("upload.created");
  });

  it("flags failed and blocked sign-ins as warnings", () => {
    expect(isWarning("auth.login_failed")).toBe(true);
    expect(isWarning("auth.login_rate_limited")).toBe(true);
    expect(isWarning("auth.login")).toBe(false);
  });

  it("summarises detail objects", () => {
    expect(detailText({ email: "a@example.com", count: 2 })).toBe(
      "email: a@example.com · count: 2",
    );
    expect(detailText({})).toBe("");
  });

  it("formats times in Kigali time", () => {
    expect(formatDateTime("2026-01-15T07:30:00Z")).toBe("15 Jan 2026, 09:30");
  });
});
