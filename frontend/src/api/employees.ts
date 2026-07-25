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

export type Employee = components["schemas"]["EmployeeResponse"];
export type EmployeeConfigurationInput = components["schemas"]["EmployeeConfigurationBody"];

const employeeSchema = z.strictObject({
  id: z.uuid(),
  name: z.string().min(1),
  description: z.string(),
  system_prompt: z.string().min(1),
  default_model_configuration_id: z.uuid(),
  default_model_identifier: z
    .string()
    .regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/),
  knowledge_base_id: z.string().min(1).nullable(),
  allowed_workflow_ids: z
    .array(z.uuid())
    .max(100)
    .refine((items) => new Set(items).size === items.length),
  deep_thinking_enabled: z.boolean(),
  created_at: z.iso.datetime({ offset: true }),
  updated_at: z.iso.datetime({ offset: true }),
});

const employeesSchema = cursorPageSchema(employeeSchema);

export function parseEmployeeResponse(data: unknown): Employee {
  return employeeSchema.parse(data);
}

export function parseEmployeesResponse(data: unknown): CursorPage<Employee> {
  return employeesSchema.parse(data);
}

export async function fetchEmployees(
  page: ListPageRequest = {},
): Promise<CursorPage<Employee>> {
  try {
    const response = await apiClient.get<unknown>("/employees", {
      params: listPageParams(page),
    });
    return parseEmployeesResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function fetchEmployee(employeeId: string): Promise<Employee> {
  try {
    const response = await apiClient.get<unknown>(
      `/employees/${encodeURIComponent(employeeId)}`,
    );
    return parseEmployeeResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function createEmployee(input: EmployeeConfigurationInput): Promise<Employee> {
  try {
    const response = await apiClient.post<unknown>("/employees", input);
    return parseEmployeeResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function updateEmployee(
  employeeId: string,
  input: EmployeeConfigurationInput,
): Promise<Employee> {
  try {
    const response = await apiClient.put<unknown>(
      `/employees/${encodeURIComponent(employeeId)}`,
      input,
    );
    return parseEmployeeResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function deleteEmployee(employeeId: string): Promise<void> {
  try {
    await apiClient.delete(`/employees/${encodeURIComponent(employeeId)}`);
  } catch (error) {
    throw toApiClientError(error);
  }
}
