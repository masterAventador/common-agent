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

export type ModelConfiguration = components["schemas"]["ModelConfigurationResponse"];
export type ModelConfigurationInput = components["schemas"]["ModelConfigurationBody"];
export type ModelConfigurationVerification =
  components["schemas"]["ModelConfigurationVerificationResponse"];

const modelConfigurationSchema = z.strictObject({
  id: z.uuid(),
  display_name: z.string().min(1),
  provider: z.literal("bailian"),
  model_identifier: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/),
  enabled: z.boolean(),
  streaming_breaks_tool_calls: z.boolean(),
  thinking_can_be_disabled: z.boolean(),
  created_at: z.iso.datetime({ offset: true }),
  updated_at: z.iso.datetime({ offset: true }),
});

const modelConfigurationsSchema = cursorPageSchema(modelConfigurationSchema);
const verificationSchema = z.strictObject({
  status: z.literal("available"),
  model_identifier: z.string().min(1),
  response_preview: z.string().min(1),
});

export function parseModelConfigurationResponse(data: unknown): ModelConfiguration {
  return modelConfigurationSchema.parse(data);
}

export function parseModelConfigurationsResponse(
  data: unknown,
): CursorPage<ModelConfiguration> {
  return modelConfigurationsSchema.parse(data);
}

export function parseModelConfigurationVerification(
  data: unknown,
): ModelConfigurationVerification {
  return verificationSchema.parse(data);
}

export async function fetchModelConfigurations(
  page: ListPageRequest = {},
  enabledOnly = false,
): Promise<CursorPage<ModelConfiguration>> {
  try {
    const response = await apiClient.get<unknown>("/model-configurations", {
      params: { ...listPageParams(page), enabled_only: enabledOnly || undefined },
    });
    return parseModelConfigurationsResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function fetchModelConfiguration(
  modelConfigurationId: string,
): Promise<ModelConfiguration> {
  try {
    const response = await apiClient.get<unknown>(
      `/model-configurations/${encodeURIComponent(modelConfigurationId)}`,
    );
    const configuration = parseModelConfigurationResponse(response.data);
    if (configuration.id !== modelConfigurationId) {
      throw new Error("模型配置响应与请求不匹配");
    }
    return configuration;
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function createModelConfiguration(
  input: ModelConfigurationInput,
): Promise<ModelConfiguration> {
  try {
    const response = await apiClient.post<unknown>("/model-configurations", input);
    return parseModelConfigurationResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function updateModelConfiguration(
  modelConfigurationId: string,
  input: ModelConfigurationInput,
): Promise<ModelConfiguration> {
  try {
    const response = await apiClient.put<unknown>(
      `/model-configurations/${encodeURIComponent(modelConfigurationId)}`,
      input,
    );
    return parseModelConfigurationResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function deleteModelConfiguration(
  modelConfigurationId: string,
): Promise<void> {
  try {
    await apiClient.delete(
      `/model-configurations/${encodeURIComponent(modelConfigurationId)}`,
    );
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function verifyModelConfiguration(
  modelConfigurationId: string,
): Promise<ModelConfigurationVerification> {
  try {
    const response = await apiClient.post<unknown>(
      `/model-configurations/${encodeURIComponent(modelConfigurationId)}/verify`,
    );
    return parseModelConfigurationVerification(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}
