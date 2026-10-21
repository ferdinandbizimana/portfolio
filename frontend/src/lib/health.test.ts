import { describe, expect, it } from "vitest";

import { parseHealth } from "./health";

describe("parseHealth", () => {
  it("accepts a healthy response", () => {
    expect(parseHealth({ status: "ok", checks: { database: "ok", redis: "ok" } })).toEqual({
      status: "ok",
      checks: { database: "ok", redis: "ok" },
    });
  });

  it("keeps the name of a failing dependency", () => {
    expect(parseHealth({ status: "degraded", checks: { database: "error" } })).toEqual({
      status: "degraded",
      checks: { database: "error" },
    });
  });

  it.each([null, "ok", { status: "fine", checks: {} }, { status: "ok", checks: { db: 1 } }])(
    "treats %j as unreachable",
    (body) => {
      expect(parseHealth(body).status).toBe("unreachable");
    },
  );
});
