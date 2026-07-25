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

/**
 * 摊平游标分页并按主键去重。
 *
 * 服务端在翻页期间仍在写入时，同一条记录可能被相邻两页同时带回；不去重会让列表出现
 * 重复条目。默认按 `id` 去重，主键字段不叫 `id` 的（如审计事件用 `event_id`）通过
 * `identify` 指定。
 */
export function flattenCursorPages<Item extends { id: string }>(
  data: InfiniteData<CursorPage<Item>, unknown> | undefined,
): Item[];
export function flattenCursorPages<Item>(
  data: InfiniteData<CursorPage<Item>, unknown> | undefined,
  identify: (item: Item) => string,
): Item[];
export function flattenCursorPages<Item>(
  data: InfiniteData<CursorPage<Item>, unknown> | undefined,
  identify: (item: Item) => string = (item) => (item as { id: string }).id,
): Item[] {
  const seen = new Set<string>();
  const items: Item[] = [];
  for (const page of data?.pages ?? []) {
    for (const item of page.items) {
      const key = identify(item);
      if (seen.has(key)) continue;
      seen.add(key);
      items.push(item);
    }
  }
  return items;
}
