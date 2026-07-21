import { z } from "zod";

import type { components } from "./generated/schema";
import { apiBaseUrl, apiClient, getTenantId } from "./client";
import { toApiClientError } from "./errors";
import {
  cursorPageSchema,
  listPageParams,
  type CursorPage,
  type ListPageRequest,
} from "./pagination";

export type Conversation = components["schemas"]["ConversationResponse"];
export type ConversationMessage = components["schemas"]["MessageResponse"];
export type ConversationEvent = components["schemas"]["ConversationEventResponse"];
export type CreateConversationInput = components["schemas"]["CreateConversationBody"];
export type CreateConversationTurnInput =
  components["schemas"]["CreateConversationTurnBody"];
export type SendMessageInput = components["schemas"]["SendMessageBody"];
export type TurnAccepted = components["schemas"]["TurnAcceptedResponse"];
export type ConversationTurnAccepted =
  components["schemas"]["ConversationTurnAcceptedResponse"];
export type StopAccepted = components["schemas"]["StopAcceptedResponse"];

const timestampSchema = z.iso.datetime({ offset: true });
const citationSchema = z.strictObject({
  position: z.int().positive(),
  knowledge_base_id: z.string().min(1),
  chunk_id: z.string().min(1),
  document_id: z.string().min(1),
  document_name: z.string().min(1),
  content: z.string().min(1),
  score: z.number().min(0).max(1),
});
const messageSchema = z.strictObject({
  id: z.uuid(),
  conversation_id: z.uuid(),
  sequence_number: z.int().positive(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  status: z.enum(["pending", "streaming", "completed", "failed", "stopped"]),
  citations: z.array(citationSchema),
  error_code: z.string().min(1).nullable(),
  model_configuration_id: z.uuid().nullable(),
  model_identifier: z.string().min(1).nullable(),
  created_at: timestampSchema,
  updated_at: timestampSchema,
});
const conversationSchema = z.strictObject({
  id: z.uuid(),
  source: z.enum(["generic", "employee"]),
  employee_id: z.uuid().nullable(),
  model_configuration_id: z.uuid().nullable(),
  title: z.string().min(1),
  created_at: timestampSchema,
  updated_at: timestampSchema,
});
const turnAcceptedSchema = z.strictObject({
  turn_id: z.uuid(),
  user_message: messageSchema,
  assistant_message: messageSchema,
  retry: z.boolean(),
});
const conversationTurnAcceptedSchema = z.strictObject({
  conversation: conversationSchema,
  turn: turnAcceptedSchema,
});
const stopAcceptedSchema = z.strictObject({
  turn_id: z.uuid(),
  assistant_message_id: z.uuid(),
});
const conversationEventSchema = z.strictObject({
  schema_version: z.literal("1"),
  sequence: z.int().positive(),
  conversation_id: z.uuid(),
  turn_id: z.uuid(),
  message_id: z.uuid(),
  type: z.enum([
    "assistant.started",
    "assistant.delta",
    "assistant.completed",
    "assistant.failed",
    "assistant.stopped",
  ]),
  delta: z.string().nullable(),
  retry: z.boolean(),
  message: messageSchema,
  occurred_at: timestampSchema,
});

const conversationsSchema = cursorPageSchema(conversationSchema);
const messagesSchema = z.array(messageSchema);
const conversationEventTypes = [
  "assistant.started",
  "assistant.delta",
  "assistant.completed",
  "assistant.failed",
  "assistant.stopped",
] as const;

export function parseConversationsResponse(data: unknown): CursorPage<Conversation> {
  return conversationsSchema.parse(data);
}

export function parseMessagesResponse(data: unknown): ConversationMessage[] {
  return messagesSchema.parse(data);
}

export function parseConversationEvent(data: unknown): ConversationEvent {
  return conversationEventSchema.parse(data);
}

export async function fetchConversations(
  employeeId?: string,
  page: ListPageRequest = {},
  source?: "generic" | "employee",
): Promise<CursorPage<Conversation>> {
  try {
    const response = await apiClient.get<unknown>("/conversations", {
      params: {
        ...listPageParams(page),
        ...(employeeId ? { employee_id: employeeId } : {}),
        ...(source ? { source } : {}),
      },
    });
    return parseConversationsResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function createConversationTurn(
  input: CreateConversationTurnInput,
): Promise<ConversationTurnAccepted> {
  try {
    const response = await apiClient.post<unknown>("/conversation-turns", input);
    return conversationTurnAcceptedSchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function createConversation(
  input: CreateConversationInput,
): Promise<Conversation> {
  try {
    const response = await apiClient.post<unknown>("/conversations", input);
    return conversationSchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function deleteConversation(conversationId: string): Promise<void> {
  try {
    await apiClient.delete(`/conversations/${encodeURIComponent(conversationId)}`);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function fetchConversationMessages(
  conversationId: string,
): Promise<ConversationMessage[]> {
  try {
    const response = await apiClient.get<unknown>(
      `/conversations/${encodeURIComponent(conversationId)}/messages`,
    );
    return parseMessagesResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function sendConversationMessage(
  conversationId: string,
  input: SendMessageInput,
): Promise<TurnAccepted> {
  try {
    const response = await apiClient.post<unknown>(
      `/conversations/${encodeURIComponent(conversationId)}/messages`,
      input,
    );
    return turnAcceptedSchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function stopConversationGeneration(
  conversationId: string,
): Promise<StopAccepted> {
  try {
    const response = await apiClient.post<unknown>(
      `/conversations/${encodeURIComponent(conversationId)}/stop`,
    );
    return stopAcceptedSchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function retryConversationMessage(messageId: string): Promise<TurnAccepted> {
  try {
    const response = await apiClient.post<unknown>(
      `/messages/${encodeURIComponent(messageId)}/retry`,
    );
    return turnAcceptedSchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export type ConversationEventOptions = {
  afterSequence?: number;
  onEvent: (event: ConversationEvent) => void;
  onError: (error: Error) => void;
};

export function subscribeToConversationEvents(
  conversationId: string,
  options: ConversationEventOptions,
): { close: () => void } {
  const afterSequence = options.afterSequence ?? 0;
  const source = new EventSource(
    `${apiBaseUrl.replace(/\/$/, "")}/conversations/${encodeURIComponent(
      conversationId,
    )}/events?${new URLSearchParams({
      after_sequence: String(afterSequence),
      tenant_id: getTenantId(),
    })}`,
    { withCredentials: true },
  );

  const handleEvent = (rawEvent: Event) => {
    try {
      const messageEvent = rawEvent as MessageEvent<string>;
      options.onEvent(parseConversationEvent(JSON.parse(messageEvent.data)));
    } catch {
      options.onError(new Error("事件数据格式不合法"));
    }
  };
  for (const eventType of conversationEventTypes) {
    source.addEventListener(eventType, handleEvent);
  }
  source.onerror = () => options.onError(new Error("事件流连接中断"));
  return { close: () => source.close() };
}
