import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PropsWithChildren } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastHost } from "../../components/ToastHost";
import { ConversationHistory } from "./ConversationHistory";

const conversationApi = vi.hoisted(() => ({
  deleteConversation: vi.fn(),
  fetchConversations: vi.fn(),
}));

vi.mock("../../api/conversations", () => conversationApi);

const generic = {
  id: "c9798edb-d7b5-42d1-b2de-0afd6a83a459",
  source: "generic" as const,
  employee_id: null,
  employee_name: null,
  model_configuration_id: "0d4f38a5-bfd1-496f-b99d-fd768a2f3c30",
  title: "通用历史",
  created_at: "2026-07-20T02:00:00Z",
  updated_at: "2026-07-20T03:00:00Z",
};
const employeeConversation = {
  ...generic,
  id: "a0fcaad2-a53d-40c8-9f64-23298bfacf49",
  source: "employee" as const,
  employee_id: "6f3d43e0-6f6d-5a67-9f25-756a0b9ed2ab",
  employee_name: "知识助理",
  model_configuration_id: null,
  title: "员工历史",
  updated_at: "2026-07-20T04:00:00Z",
};

function Providers({ children }: PropsWithChildren) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      {children}
      <ToastHost />
    </QueryClientProvider>
  );
}

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="当前位置">{`${location.pathname}${location.search}`}</output>;
}

function renderHistory() {
  return render(
    <MemoryRouter initialEntries={["/employees"]}>
      <ConversationHistory />
      <LocationProbe />
    </MemoryRouter>,
    { wrapper: Providers },
  );
}

describe("ConversationHistory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    conversationApi.fetchConversations.mockImplementation(
      (_employeeId: string | undefined, { cursor }: { cursor?: string }) =>
        Promise.resolve(
          cursor
            ? { items: [generic], next_cursor: null }
            : { items: [employeeConversation], next_cursor: "next-history" },
        ),
    );
    conversationApi.deleteConversation.mockResolvedValue(undefined);
  });

  it("shows attribution, loads more, and opens the selected history from the global sidebar", async () => {
    const user = userEvent.setup();
    renderHistory();

    expect(await screen.findByText("员工历史")).toBeInTheDocument();
    expect(screen.getByText("知识助理")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "加载更多历史会话" }));
    expect(await screen.findByText("通用历史")).toBeInTheDocument();
    expect(screen.getByText("通用 AI")).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "打开会话 员工历史" }));
    expect(screen.getByRole("status", { name: "当前位置" })).toHaveTextContent(
      `/chat?conversation_id=${employeeConversation.id}&employee_id=${employeeConversation.employee_id}`,
    );
  });

  it("deletes through the formal confirmation and refreshes all conversation snapshots", async () => {
    conversationApi.fetchConversations
      .mockResolvedValueOnce({ items: [generic], next_cursor: null })
      .mockResolvedValue({ items: [], next_cursor: null });
    const user = userEvent.setup();
    renderHistory();

    await user.click(await screen.findByRole("button", { name: "删除会话 通用历史" }));
    await user.click(screen.getByRole("button", { name: "确认删除会话 通用历史" }));
    await waitFor(() => expect(conversationApi.deleteConversation).toHaveBeenCalledWith(generic.id));
    const removalToast = await screen.findByText("会话“通用历史”已删除");
    expect(removalToast.closest(".toast-item")).toHaveAttribute("role", "status");
    expect(await screen.findByText("暂无历史会话")).toBeInTheDocument();
  });
});
