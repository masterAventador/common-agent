import { describe, expect, it } from "vitest";

import { RESOURCE_TINTS, resourceTint } from "./resourceTint";

describe("resourceTint", () => {
  it("keeps the same tint for the same resource", () => {
    const key = "6f3d43e0-6f6d-5a67-9f25-756a0b9ed2ab";
    expect(resourceTint(key)).toEqual(resourceTint(key));
    expect(RESOURCE_TINTS).toContainEqual(resourceTint(key));
  });

  it("spreads different resources across the whole palette", () => {
    const used = new Set(
      Array.from({ length: 200 }, (_, index) => resourceTint(`employee-${index}`)),
    );
    expect(used.size).toBe(RESOURCE_TINTS.length);
  });

  it("stays inside the palette for empty and non-ascii keys", () => {
    expect(RESOURCE_TINTS).toContainEqual(resourceTint(""));
    expect(RESOURCE_TINTS).toContainEqual(resourceTint("知识助理"));
  });
});
