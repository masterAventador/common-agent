import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import {
  createConversation,
  createConversationTurn,
  deleteConversation,
  fetchConversation,
  fetchConversationMessages,
  fetchConversations,
  parseConversationEvent,
  parseMessagesResponse,
  retryConversationMessage,
  sendConversationMessage,
  stopConversationGeneration,
  subscribeToConversationEvents,
} from "./conversations";

vi.mock("./client", () => ({
  apiBaseUrl: "http://127.0.0.1:18200/api/v1",
  getTenantId: () => "10000000-0000-4000-8000-000000000001",
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const conversation = {
  id: "a0fcaad2-a53d-40c8-9f64-23298bfacf49",
  source: "employee" as const,
  employee_id: "6f3d43e0-6f6d-5a67-9f25-756a0b9ed2ab",
  model_configuration_id: null,
  title: "知识问答",
  created_at: "2026-07-20T02:00:00Z",
  updated_at: "2026-07-20T02:00:00Z",
};
const historyItem = { ...conversation, employee_name: "知识助理" };

const userMessage = {
  id: "52a34887-e32a-4709-aa32-6835502a8bc8",
  conversation_id: conversation.id,
  sequence_number: 1,
  role: "user" as const,
  content: "验收问题",
  status: "completed" as const,
  citations: [],
  error_code: null,
  model_configuration_id: null,
  model_identifier: null,
  created_at: "2026-07-20T02:00:01Z",
  updated_at: "2026-07-20T02:00:01Z",
};

const assistantMessage = {
  ...userMessage,
  id: "baeed6a2-d8cb-49ac-8999-393cf2153161",
  sequence_number: 2,
  role: "assistant" as const,
  model_configuration_id: "0d4f38a5-bfd1-496f-b99d-fd768a2f3c30",
  model_identifier: "qwen-turbo",
  content: "验收回答",
  citations: [
    {
      position: 1,
      knowledge_base_id: "kb-1",
      chunk_id: "chunk-1",
      document_id: "doc-1",
      document_name: "手册.txt",
      content: "可靠引用",
      score: 0.91,
    },
  ],
};

const turn = {
  turn_id: "3a64b792-d4a9-4296-a7fd-79013bb42c2b",
  user_message: userMessage,
  assistant_message: { ...assistantMessage, content: "", status: "pending" as const },
  retry: false,
};

const event = {
  schema_version: "1" as const,
  sequence: 4,
  conversation_id: conversation.id,
  turn_id: turn.turn_id,
  message_id: assistantMessage.id,
  type: "assistant.completed" as const,
  delta: null,
  retry: false,
  message: assistantMessage,
  occurred_at: "2026-07-20T02:00:02Z",
};

class FakeEventSource {
  static latest: FakeEventSource | undefined;
  readonly listeners = new Map<string, Array<(event: MessageEvent<string>) => void>>();
  readonly close = vi.fn();
  onerror: ((event: Event) => void) | null = null;

  constructor(
    readonly url: string,
    readonly eventSourceInit?: EventSourceInit,
  ) {
    FakeEventSource.latest = this;
  }

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  emit(type: string, payload: unknown) {
    for (const listener of this.listeners.get(type) ?? []) {
      listener(new MessageEvent(type, { data: JSON.stringify(payload) }));
    }
  }
}

describe("conversation API and SSE boundary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    FakeEventSource.latest = undefined;
    vi.stubGlobal("EventSource", FakeEventSource);
  });

  it("accepts generated message and event snapshots and rejects drift", () => {
    expect(parseMessagesResponse([userMessage, assistantMessage])).toEqual([
      userMessage,
      assistantMessage,
    ]);
    expect(parseConversationEvent(event)).toEqual(event);

    expect(() => parseMessagesResponse([{ ...userMessage, private_prompt: "secret" }])).toThrow();
    expect(() => parseConversationEvent({ ...event, schema_version: "2" })).toThrow();
    expect(() =>
      parseConversationEvent({
        ...event,
        message: { ...assistantMessage, status: "unknown" },
      }),
    ).toThrow();
  });

  it("uses only formal conversation list, history, send, stop, and retry endpoints", async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: { items: [historyItem], next_cursor: null } })
      .mockResolvedValueOnce({ data: historyItem })
      .mockResolvedValueOnce({ data: [userMessage, assistantMessage] });
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce({ data: conversation })
      .mockResolvedValueOnce({ data: { conversation, turn } })
      .mockResolvedValueOnce({ data: turn })
      .mockResolvedValueOnce({ data: { turn_id: turn.turn_id, assistant_message_id: assistantMessage.id } })
      .mockResolvedValueOnce({ data: { ...turn, retry: true } });
    vi.mocked(apiClient.delete).mockResolvedValue({ data: undefined });

    await expect(fetchConversations(conversation.employee_id)).resolves.toEqual({
      items: [historyItem],
      next_cursor: null,
    });
    await expect(fetchConversation(conversation.id)).resolves.toEqual(historyItem);
    await expect(
      createConversation({
        conversation_id: conversation.id,
        employee_id: conversation.employee_id,
        title: conversation.title,
      }),
    ).resolves.toEqual(conversation);
    await expect(fetchConversationMessages(conversation.id)).resolves.toEqual([
      userMessage,
      assistantMessage,
    ]);
    await expect(
      createConversationTurn({
        conversation_id: conversation.id,
        message_id: userMessage.id,
        employee_id: conversation.employee_id,
        model_configuration_id: assistantMessage.model_configuration_id,
        content: userMessage.content,
      }),
    ).resolves.toEqual({ conversation, turn });
    await expect(
      sendConversationMessage(conversation.id, {
        message_id: userMessage.id,
        model_configuration_id: assistantMessage.model_configuration_id,
        content: userMessage.content,
      }),
    ).resolves.toEqual(turn);
    await expect(stopConversationGeneration(conversation.id)).resolves.toEqual({
      turn_id: turn.turn_id,
      assistant_message_id: assistantMessage.id,
    });
    await expect(retryConversationMessage(assistantMessage.id)).resolves.toEqual({
      ...turn,
      retry: true,
    });
    await expect(deleteConversation(conversation.id)).resolves.toBeUndefined();

    expect(apiClient.get).toHaveBeenNthCalledWith(1, "/conversations", {
      params: { employee_id: conversation.employee_id },
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(1, "/conversations", {
      conversation_id: conversation.id,
      employee_id: conversation.employee_id,
      title: conversation.title,
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      `/conversations/${conversation.id}`,
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      3,
      `/conversations/${conversation.id}/messages`,
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      "/conversation-turns",
      {
        conversation_id: conversation.id,
        message_id: userMessage.id,
        employee_id: conversation.employee_id,
        model_configuration_id: assistantMessage.model_configuration_id,
        content: userMessage.content,
      },
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      `/conversations/${conversation.id}/messages`,
      {
        message_id: userMessage.id,
        model_configuration_id: assistantMessage.model_configuration_id,
        content: userMessage.content,
      },
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      4,
      `/conversations/${conversation.id}/stop`,
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      5,
      `/messages/${assistantMessage.id}/retry`,
    );
    expect(apiClient.delete).toHaveBeenCalledWith(`/conversations/${conversation.id}`);
  });

  it("parses named SSE events, reports malformed payloads, and closes explicitly", () => {
    const onEvent = vi.fn();
    const onError = vi.fn();
    const subscription = subscribeToConversationEvents(conversation.id, {
      afterSequence: 3,
      onEvent,
      onError,
    });
    const source = FakeEventSource.latest;
    expect(source?.url).toBe(
      `http://127.0.0.1:18200/api/v1/conversations/${conversation.id}/events?after_sequence=3&tenant_id=10000000-0000-4000-8000-000000000001`,
    );
    expect(source?.eventSourceInit).toEqual({ withCredentials: true });

    source?.emit("assistant.completed", event);
    source?.emit("assistant.delta", { ...event, schema_version: "2" });

    expect(onEvent).toHaveBeenCalledWith(event);
    expect(onError).toHaveBeenCalledTimes(1);
    subscription.close();
    expect(source?.close).toHaveBeenCalledTimes(1);
  });
});
