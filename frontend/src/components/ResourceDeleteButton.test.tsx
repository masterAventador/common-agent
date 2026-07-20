import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { ResourceDeleteButton } from "./ResourceDeleteButton";

it("shows a keyboard-safe irreversible confirmation before invoking deletion", async () => {
  const onConfirm = vi.fn().mockResolvedValue(undefined);
  const user = userEvent.setup();
  render(
    <ResourceDeleteButton
      resourceKind="知识库"
      resourceName="产品资料"
      impact="文档与索引都会被永久删除。"
      onConfirm={onConfirm}
    />,
  );

  await user.click(screen.getByRole("button", { name: "删除知识库 产品资料" }));

  expect(screen.getByRole("dialog", { name: "删除知识库“产品资料”？" })).toBeInTheDocument();
  expect(screen.getByText("文档与索引都会被永久删除。")).toBeInTheDocument();
  expect(screen.getByText("此操作不可恢复。")).toBeInTheDocument();
  const cancel = screen.getByRole("button", { name: /取\s*消/ });
  await waitFor(() => expect(cancel).toHaveFocus());

  await user.click(cancel);
  expect(onConfirm).not.toHaveBeenCalled();
});
