import { expect, type Locator, type Page } from "@playwright/test";

export async function selectEmployeeDefaultModel(
  page: Page,
  dialog: Locator,
  modelText?: string,
): Promise<void> {
  await dialog.getByRole("combobox", { name: "默认模型" }).click();
  const options = page.locator(
    ".ant-select-dropdown:visible .ant-select-item-option:not(.ant-select-item-option-disabled)",
  );
  const option = modelText ? options.filter({ hasText: modelText }).first() : options.first();
  await expect(option).toBeVisible();
  await option.click();
}

export async function selectWorkflowAiTarget(page: Page, targetText: string): Promise<void> {
  await page.getByRole("combobox", { name: "AI 对话执行目标" }).click();
  const option = page
    .locator(
    ".ant-select-dropdown:visible .ant-select-item-option:not(.ant-select-item-option-disabled)",
    )
    .filter({ hasText: targetText })
    .first();
  await expect(option).toBeVisible();
  await option.click();
}
