import { describe, expect, it } from "vitest";

import { errorMessage } from "./api-errors";

describe("errorMessage", () => {
  it("uses a string detail", () => {
    expect(errorMessage({ detail: "The e-mail or password is not correct." })).toBe(
      "The e-mail or password is not correct.",
    );
  });

  it("uses the first validation error with its field", () => {
    expect(
      errorMessage({
        detail: [{ loc: ["body", "email"], msg: "String should have at least 3 characters" }],
      }),
    ).toBe("email: String should have at least 3 characters");
  });

  it("falls back for anything else", () => {
    expect(errorMessage(null)).toBe("Something went wrong. Please try again.");
    expect(errorMessage({ detail: "" }, "Fallback")).toBe("Fallback");
  });
});
