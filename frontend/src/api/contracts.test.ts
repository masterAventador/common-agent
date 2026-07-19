import { describe, expect, it } from "vitest";

import type { ApiError } from "./contracts";

describe("generated API contracts", () => {
  it("exposes the stable backend error envelope", () => {
    const error = {
      code: "resource_not_found",
      message: "请求的资源不存在",
      request_id: "request-1",
      retryable: false,
    } satisfies ApiError;

    expect(error.retryable).toBe(false);
  });
});
