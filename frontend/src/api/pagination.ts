import { z } from "zod";
import type { InfiniteData } from "@tanstack/react-query";

export interface CursorPage<Item> {
  items: Item[];
  next_cursor: string | null;
}

export interface ListPageRequest {
  search?: string;
  limit?: number;
  cursor?: string;
}

export function cursorPageSchema<ItemSchema extends z.ZodType>(itemSchema: ItemSchema) {
  return z.strictObject({
    items: z.array(itemSchema),
    next_cursor: z.string().min(1).nullable(),
  });
}

export function listPageParams(request: ListPageRequest): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (request.search?.trim()) params.search = request.search.trim();
  if (request.limit !== undefined) params.limit = request.limit;
  if (request.cursor) params.cursor = request.cursor;
  return params;
}

export function nextPageCursor<Item>(page: CursorPage<Item>): string | undefined {
  return page.next_cursor ?? undefined;
}

export function flattenCursorPages<Item extends { id: string }>(
  data: InfiniteData<CursorPage<Item>, unknown> | undefined,
): Item[] {
  const seen = new Set<string>();
  const items: Item[] = [];
  for (const page of data?.pages ?? []) {
    for (const item of page.items) {
      if (seen.has(item.id)) continue;
      seen.add(item.id);
      items.push(item);
    }
  }
  return items;
}
