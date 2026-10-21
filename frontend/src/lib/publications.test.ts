import { describe, expect, it } from "vitest";

import { publicPath, sharePath, VISIBILITY_LABEL } from "./publications";

describe("publication links", () => {
  it("builds the shared and public paths", () => {
    expect(sharePath({ secret_token: "abc_123" })).toBe("/d/abc_123");
    expect(publicPath({ slug: "stock-june" })).toBe("/dashboards/stock-june");
  });

  it("labels every visibility", () => {
    expect(Object.keys(VISIBILITY_LABEL)).toEqual(["private", "secret", "public"]);
  });
});
