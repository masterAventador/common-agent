import { z } from "zod";

import type { components } from "./generated/schema";
import { apiClient } from "./client";
import { toApiClientError } from "./errors";

export const auditActionSchema = z.enum([
  "auth.register",
  "auth.login",
  "auth.logout",
  "auth.recovery.reset",
  "auth.member.provisioned",
  "tenant.created",
  "employee.created",
  "employee.configuration_and_bindings.updated",
  "tool.grants.updated",
  "tool.credentials.updated",
  "mcp.source.created",
  "mcp.source.updated",
  "mcp.source.discovered",
  "tool.capability.created",
  "tool.capability.updated",
  "tool.capabilities.imported",
  "tool.called",
  "model.configuration.created",
  "model.configuration.updated",
  "model.configuration.verified",
  "knowledge.base.created",
  "knowledge.document.uploaded",
  "knowledge.document.retry_started",
  "resource.deleted",
  "conversation.reply.started",
  "workflow.configuration.updated",
  "workflow.run.started",
  "workflow.run.stopped",
  "security.permission.denied",
  "security.request.denied",
]);

export const auditResourceTypeSchema = z.enum([
  "user",
  "session",
  "tenant",
  "employee",
  "model_configuration",
  "mcp_source",
  "tool_capability",
  "knowledge_base",
  "knowledge_document",
  "conversation",
  "workflow",
  "workflow_run",
]);

const digestSchema = z.string().regex(/^[0-9a-f]{64}$/);
const auditEventSchema = z.strictObject({
  sequence: z.number().int().positive(),
  event_id: z.uuid(),
  tenant_id: z.uuid().nullable(),
  actor_user_id: z.uuid().nullable(),
  action: auditActionSchema,
  outcome: z.enum(["started", "succeeded", "denied", "failed"]),
  request_id: z.uuid(),
  trace_id: z.string().regex(/^[0-9a-f]{32}$/),
  resource_type: auditResourceTypeSchema.nullable(),
  resource_id: z.string().min(1).max(128).nullable(),
  error_code: z.string().min(1).max(128).nullable(),
  occurred_at: z.iso.datetime({ offset: true }),
  retention_until: z.iso.datetime({ offset: true }),
  previous_hash: digestSchema,
  event_hash: digestSchema,
});
const auditPageSchema = z.strictObject({
  items: z.array(auditEventSchema),
  next_cursor: z.string().min(1).nullable(),
});
const auditIntegritySchema = z.strictObject({
  event_count: z.number().int().nonnegative(),
  first_sequence: z.number().int().positive().nullable(),
  last_sequence: z.number().int().positive().nullable(),
  last_hash: digestSchema,
  verified: z.boolean(),
  broken_sequence: z.number().int().nonnegative().nullable(),
});
const auditPolicySchema = z.strictObject({
  retention_days: z.number().int().min(30).max(3650),
  max_events_per_scope: z.number().int().min(100).max(10_000_000),
  automatic_deletion: z.literal(false),
});

export type AuditAction = components["schemas"]["AuditAction"];
export type AuditResourceType = components["schemas"]["AuditResourceType"];
export type AuditEvent = components["schemas"]["AuditEventResponse"];
export type AuditPage = components["schemas"]["AuditPageResponse"];
export type AuditIntegrity = components["schemas"]["AuditIntegrityResponse"];
export type AuditPolicy = components["schemas"]["AuditPolicyResponse"];
export type AuditScope = "tenant" | "platform";

export interface AuditQuery {
  scope?: AuditScope;
  actor_user_id?: string;
  resource_type?: AuditResourceType;
  resource_id?: string;
  action?: AuditAction;
  occurred_from?: string;
  occurred_to?: string;
  limit?: number;
  cursor?: string;
}

export async function fetchAuditEvents(query: AuditQuery = {}): Promise<AuditPage> {
  try {
    const response = await apiClient.get<unknown>("/audit-events", {
      params: compactQuery(query),
    });
    return auditPageSchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function fetchAuditIntegrity(scope: AuditScope = "tenant"): Promise<AuditIntegrity> {
  try {
    const response = await apiClient.get<unknown>("/audit-events/integrity", {
      params: { scope },
    });
    return auditIntegritySchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function fetchAuditPolicy(): Promise<AuditPolicy> {
  try {
    const response = await apiClient.get<unknown>("/audit-events/policy");
    return auditPolicySchema.parse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

function compactQuery(query: AuditQuery): Record<string, string | number> {
  return Object.fromEntries(
    Object.entries(query).filter((entry): entry is [string, string | number] => {
      const value = entry[1];
      return value !== undefined && value !== "";
    }),
  );
}
