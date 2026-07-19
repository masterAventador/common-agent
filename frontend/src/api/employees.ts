import { z } from "zod";

import type { components } from "./generated/schema";
import { apiClient } from "./client";
import { toApiClientError } from "./errors";

export type Employee = components["schemas"]["EmployeeResponse"];
export type EmployeeConfigurationInput = components["schemas"]["EmployeeConfigurationBody"];

const employeeSchema = z.strictObject({
  id: z.uuid(),
  name: z.string().min(1),
  description: z.string(),
  system_prompt: z.string().min(1),
  knowledge_base_id: z.string().min(1).nullable(),
  allowed_workflow_ids: z.array(z.uuid()),
  created_at: z.iso.datetime({ offset: true }),
  updated_at: z.iso.datetime({ offset: true }),
});

const employeesSchema = z.array(employeeSchema);

export function parseEmployeeResponse(data: unknown): Employee {
  return employeeSchema.parse(data);
}

export function parseEmployeesResponse(data: unknown): Employee[] {
  return employeesSchema.parse(data);
}

export async function fetchEmployees(): Promise<Employee[]> {
  try {
    const response = await apiClient.get<unknown>("/employees");
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
