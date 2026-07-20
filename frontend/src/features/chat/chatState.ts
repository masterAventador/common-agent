import type { ConversationMessage } from "../../api/conversations";
import type { WorkflowRun } from "../../api/workflowRuns";

const messageStatusOrder: Record<ConversationMessage["status"], number> = {
  pending: 0,
  streaming: 1,
  completed: 2,
  failed: 2,
  stopped: 2,
};

export function replaceMessage(
  messages: ConversationMessage[] | undefined,
  nextMessage: ConversationMessage,
): ConversationMessage[] {
  const current = messages ?? [];
  const existingIndex = current.findIndex((message) => message.id === nextMessage.id);
  const existing = current[existingIndex];
  if (existing) {
    const existingUpdatedAt = Date.parse(existing.updated_at);
    const nextUpdatedAt = Date.parse(nextMessage.updated_at);
    if (
      nextUpdatedAt < existingUpdatedAt ||
      (nextUpdatedAt === existingUpdatedAt &&
        messageStatusOrder[nextMessage.status] < messageStatusOrder[existing.status])
    ) {
      return current;
    }
  }
  const next =
    existingIndex === -1
      ? [...current, nextMessage]
      : current.map((message, index) => (index === existingIndex ? nextMessage : message));
  return [...next].sort((left, right) => left.sequence_number - right.sequence_number);
}

export function mergeAcceptedTurn(
  messages: ConversationMessage[] | undefined,
  userMessage: ConversationMessage,
  assistantMessage: ConversationMessage,
): ConversationMessage[] {
  return replaceMessage(replaceMessage(messages, userMessage), assistantMessage);
}

export function groupWorkflowRunsByMessage(runs: WorkflowRun[]): Map<string, WorkflowRun[]> {
  const grouped = new Map<string, WorkflowRun[]>();
  for (const run of runs) {
    const messageId = run.origin?.assistant_message_id;
    if (!messageId) continue;
    grouped.set(messageId, [...(grouped.get(messageId) ?? []), run]);
  }
  return grouped;
}
