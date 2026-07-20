import { describe, expect, it } from "vitest";

import { flattenCursorPages, listPageParams, nextPageCursor } from "./pagination";

describe("cursor pagination helpers", () => {
  it("normalizes request params and exposes only a real next cursor", () => {
    expect(listPageParams({ search: "  产品  ", limit: 20, cursor: "next" })).toEqual({
      search: "产品",
      limit: 20,
      cursor: "next",
    });
    expect(nextPageCursor({ items: [], next_cursor: null })).toBeUndefined();
  });

  it("flattens pages in order without rendering a shifted duplicate twice", () => {
    expect(
      flattenCursorPages({
        pages: [
          { items: [{ id: "3" }, { id: "2" }], next_cursor: "next" },
          { items: [{ id: "2" }, { id: "1" }], next_cursor: null },
        ],
        pageParams: [undefined, "next"],
      }),
    ).toEqual([{ id: "3" }, { id: "2" }, { id: "1" }]);
  });
});
