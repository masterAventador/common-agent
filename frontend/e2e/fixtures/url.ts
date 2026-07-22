import type { Page } from "@playwright/test";

import { expect } from "./auth";

export async function expectRouteSearchParam(
  page: Page,
  pathname: string,
  parameter: string,
  value: string,
): Promise<void> {
  await expect(page).toHaveURL((url) => {
    return url.pathname === pathname && url.searchParams.get(parameter) === value;
  });
}
