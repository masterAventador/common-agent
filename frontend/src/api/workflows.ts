import { z } from "zod";

import type { components } from "./generated/schema";
import { apiClient } from "./client";
import { toApiClientError } from "./errors";
import {
  cursorPageSchema,
  listPageParams,
  type CursorPage,
  type ListPageRequest,
} from "./pagination";

export type Workflow = components["schemas"]["WorkflowResponse"];
export type WorkflowConfigurationInput = components["schemas"]["WorkflowConfigurationBody"];
export type WorkflowNodeInput = components["schemas"]["WorkflowNodeBody"];
export type WorkflowNodeType = WorkflowNodeInput["type"];
export type WorkflowValidationIssue = components["schemas"]["WorkflowValidationIssueResponse"];
export type WorkflowValidationResult = components["schemas"]["WorkflowValidationResponse"];

const positionSchema = z.strictObject({
  x: z.number().finite(),
  y: z.number().finite(),
});

const nodeIdSchema = z.string().trim().min(1).max(128);
const startNodeSchema = z.strictObject({
  id: nodeIdSchema,
  type: z.literal("start"),
  position: positionSchema,
  config: z.strictObject({}),
});
const aiChatNodeSchema = z.strictObject({
  id: nodeIdSchema,
  type: z.literal("ai_chat"),
  position: positionSchema,
  config: z.strictObject({
    prompt: z.string().trim().min(1).max(12_000),
    target: z.discriminatedUnion("type", [
      z.strictObject({ type: z.literal("employee"), employee_id: z.uuid() }),
      z.strictObject({ type: z.literal("model"), model_configuration_id: z.uuid() }),
    ]),
  }),
});
const knowledgeRetrievalNodeSchema = z.strictObject({
  id: nodeIdSchema,
  type: z.literal("knowledge_retrieval"),
  position: positionSchema,
  config: z.strictObject({
    knowledge_base_id: z.string().trim().min(1).max(128),
  }),
});
const endNodeSchema = z.strictObject({
  id: nodeIdSchema,
  type: z.literal("end"),
  position: positionSchema,
  config: z.strictObject({}),
});
const workflowNodeSchema = z.discriminatedUnion("type", [
  startNodeSchema,
  aiChatNodeSchema,
  knowledgeRetrievalNodeSchema,
  endNodeSchema,
]);
const workflowEdgeSchema = z.strictObject({
  id: z.string().trim().min(1).max(128),
  source: nodeIdSchema,
  target: nodeIdSchema,
});
const workflowSchema = z.strictObject({
  id: z.uuid(),
  name: z.string().trim().min(1).max(128),
  description: z.string().trim().max(1_000),
  nodes: z.array(workflowNodeSchema),
  edges: z.array(workflowEdgeSchema),
  created_at: z.iso.datetime({ offset: true }),
  updated_at: z.iso.datetime({ offset: true }),
});

const validationCodeSchema = z.enum([
  "node_limit_exceeded",
  "edge_limit_exceeded",
  "duplicate_node_id",
  "duplicate_edge_id",
  "missing_start",
  "multiple_starts",
  "missing_end",
  "edge_source_missing",
  "edge_target_missing",
  "self_loop",
  "duplicate_connection",
  "start_has_incoming_edge",
  "end_has_outgoing_edge",
  "multiple_outgoing_edges",
  "isolated_node",
  "unreachable_from_start",
  "cannot_reach_end",
  "cycle_detected",
  "knowledge_base_not_found",
  "ai_target_required",
  "employee_not_found",
  "model_configuration_not_found",
  "model_configuration_disabled",
]);
const workflowValidationSchema = z.strictObject({
  valid: z.boolean(),
  issues: z.array(
    z.strictObject({
      code: validationCodeSchema,
      message: z.string().min(1),
      node_id: nodeIdSchema.nullable(),
      edge_id: z.string().trim().min(1).max(128).nullable(),
    }),
  ),
});

const workflowsSchema = cursorPageSchema(workflowSchema);

export function parseWorkflowResponse(data: unknown): Workflow {
  return workflowSchema.parse(data);
}

export function parseWorkflowsResponse(data: unknown): CursorPage<Workflow> {
  return workflowsSchema.parse(data);
}

export function parseWorkflowValidationResponse(data: unknown): WorkflowValidationResult {
  return workflowValidationSchema.parse(data);
}

export async function fetchWorkflows(
  page: ListPageRequest = {},
): Promise<CursorPage<Workflow>> {
  try {
    const response = await apiClient.get<unknown>("/workflows", {
      params: listPageParams(page),
    });
    return parseWorkflowsResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function validateWorkflow(
  configuration: WorkflowConfigurationInput,
): Promise<WorkflowValidationResult> {
  try {
    const response = await apiClient.post<unknown>("/workflows/validate", configuration);
    return parseWorkflowValidationResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function createWorkflow(
  configuration: WorkflowConfigurationInput,
): Promise<Workflow> {
  try {
    const response = await apiClient.post<unknown>("/workflows", configuration);
    return parseWorkflowResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function deleteWorkflow(workflowId: string): Promise<void> {
  try {
    await apiClient.delete(`/workflows/${encodeURIComponent(workflowId)}`);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function updateWorkflow(
  workflowId: string,
  configuration: WorkflowConfigurationInput,
): Promise<Workflow> {
  try {
    const response = await apiClient.put<unknown>(
      `/workflows/${encodeURIComponent(workflowId)}`,
      configuration,
    );
    return parseWorkflowResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}
