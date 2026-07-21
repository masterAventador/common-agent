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

export type WorkflowRun = components["schemas"]["WorkflowRunResponse"];
export type WorkflowRunEvent = components["schemas"]["WorkflowRunEventResponse"];
export type StartWorkflowRunInput = components["schemas"]["StartWorkflowRunBody"];
export type StopWorkflowRunAccepted =
  components["schemas"]["WorkflowRunStopAcceptedResponse"];

const timestampSchema = z.iso.datetime({ offset: true });
const nodeIdSchema = z.string().trim().min(1).max(128);
const runIdSchema = z.uuid();
const workflowRunStatusSchema = z.enum([
  "pending",
  "running",
  "completed",
  "failed",
  "stopped",
]);
const workflowRunOriginSchema = z.strictObject({
  employee_id: z.uuid(),
  conversation_id: z.uuid(),
  assistant_message_id: z.uuid(),
});
const workflowAiTargetSchema = z.strictObject({
  node_id: nodeIdSchema,
  target_type: z.enum(["employee", "model"]),
  target_id: z.uuid(),
  target_name: z.string().trim().min(1).max(128),
  model_configuration_id: z.uuid(),
  model_identifier: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/),
});
const workflowRunSchema = z
  .strictObject({
    id: runIdSchema,
    workflow_id: z.uuid(),
    trigger: z.enum(["manual", "employee"]),
    status: workflowRunStatusSchema,
    input: z.string().min(1).max(200_000),
    output: z.string().max(200_000),
    current_node_id: nodeIdSchema.nullable(),
    completed_node_ids: z.array(nodeIdSchema).max(100),
    failed_node_id: nodeIdSchema.nullable(),
    error_code: z.string().trim().min(1).max(128).nullable(),
    origin: workflowRunOriginSchema.nullable(),
    ai_targets: z.array(workflowAiTargetSchema).max(100),
    created_at: timestampSchema,
    started_at: timestampSchema.nullable(),
    finished_at: timestampSchema.nullable(),
    updated_at: timestampSchema,
  })
  .superRefine((value, context) => {
    if ((value.trigger === "employee") !== (value.origin !== null)) {
      context.addIssue({
        code: "custom",
        message: "运行触发来源与关联信息不一致",
        path: ["origin"],
      });
    }
  });
const workflowRunsSchema = cursorPageSchema(workflowRunSchema);
const workflowRunEventTypes = [
  "workflow.run.started",
  "workflow.node.started",
  "workflow.node.completed",
  "workflow.node.failed",
  "workflow.run.completed",
  "workflow.run.failed",
  "workflow.run.stopped",
] as const;
const workflowRunEventSchema = z
  .strictObject({
    schema_version: z.literal("1"),
    sequence: z.int().positive(),
    run_id: runIdSchema,
    workflow_id: z.uuid(),
    type: z.enum(workflowRunEventTypes),
    node_id: nodeIdSchema.nullable(),
    run: workflowRunSchema,
    occurred_at: timestampSchema,
  })
  .superRefine((value, context) => {
    if (value.run_id !== value.run.id) {
      context.addIssue({ code: "custom", message: "事件运行 ID 与摘要不一致", path: ["run"] });
    }
    if (value.workflow_id !== value.run.workflow_id) {
      context.addIssue({ code: "custom", message: "事件工作流 ID 与摘要不一致", path: ["run"] });
    }
  });
const stopAcceptedSchema = z.strictObject({ run_id: runIdSchema });

export function parseWorkflowRunResponse(data: unknown): WorkflowRun {
  return workflowRunSchema.parse(data);
}

export function parseWorkflowRunEvent(data: unknown): WorkflowRunEvent {
  return workflowRunEventSchema.parse(data);
}

export async function fetchConversationWorkflowRuns(
  conversationId: string,
  page: ListPageRequest = {},
): Promise<CursorPage<WorkflowRun>> {
  try {
    const response = await apiClient.get<unknown>("/workflow-runs", {
      params: { conversation_id: conversationId, ...listPageParams(page) },
    });
    return workflowRunsSchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function startWorkflowRun(
  workflowId: string,
  input: StartWorkflowRunInput,
): Promise<WorkflowRun> {
  try {
    const response = await apiClient.post<unknown>(
      `/workflows/${encodeURIComponent(workflowId)}/runs`,
      input,
    );
    return parseWorkflowRunResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function fetchWorkflowRun(runId: string): Promise<WorkflowRun> {
  try {
    const response = await apiClient.get<unknown>(
      `/workflow-runs/${encodeURIComponent(runId)}`,
    );
    return parseWorkflowRunResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function stopWorkflowRun(runId: string): Promise<StopWorkflowRunAccepted> {
  try {
    const response = await apiClient.post<unknown>(
      `/workflow-runs/${encodeURIComponent(runId)}/stop`,
    );
    return stopAcceptedSchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export interface WorkflowRunEventOptions {
  afterSequence?: number;
  onEvent: (event: WorkflowRunEvent) => void;
  onError: (error: Error) => void;
}

export function subscribeToWorkflowRunEvents(
  runId: string,
  options: WorkflowRunEventOptions,
): { close: () => void } {
  const afterSequence = options.afterSequence ?? 0;
  const source = new EventSource(
    `${apiBaseUrl.replace(/\/$/, "")}/workflow-runs/${encodeURIComponent(
      runId,
    )}/events?${new URLSearchParams({
      after_sequence: String(afterSequence),
      tenant_id: getTenantId(),
    })}`,
    { withCredentials: true },
  );
  const handleEvent = (rawEvent: Event) => {
    try {
      const messageEvent = rawEvent as MessageEvent<string>;
      options.onEvent(parseWorkflowRunEvent(JSON.parse(messageEvent.data)));
    } catch {
      options.onError(new Error("工作流事件数据格式不合法"));
    }
  };
  for (const eventType of workflowRunEventTypes) {
    source.addEventListener(eventType, handleEvent);
  }
  source.onerror = () => options.onError(new Error("工作流事件流连接中断"));
  return { close: () => source.close() };
}
