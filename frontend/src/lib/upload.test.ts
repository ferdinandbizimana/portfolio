import { describe, expect, it } from "vitest";

import { formatBytes, missingChunks } from "./upload";

describe("upload helpers", () => {
  it("lists the chunks still to send", () => {
    expect(
      missingChunks({
        id: "x",
        filename: "f.xlsx",
        size_bytes: 25,
        chunk_size: 10,
        chunk_count: 3,
        received_chunks: [1],
      }),
    ).toEqual([0, 2]);
  });

  it("formats sizes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(214 * 1024 * 1024)).toBe("214.0 MB");
  });
});
