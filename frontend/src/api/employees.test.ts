import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import {
  createEmployee,
  deleteEmployee,
  fetchEmployee,
  fetchEmployees,
  parseEmployeeResponse,
  parseEmployeesResponse,
  updateEmployee,
} from "./employees";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const employee = {
  id: "6f3d43e0-6f6d-5a67-9f25-756a0b9ed2ab",
  name: "知识助理",
  description: "通用知识问答",
  system_prompt: "优先依据知识库回答。",
  default_model_configuration_id: "0d4f38a5-bfd1-496f-b99d-fd768a2f3c30",
  default_model_identifier: "qwen-plus",
  knowledge_base_id: "kb-1",
  allowed_workflow_ids: [],
  created_at: "2026-07-19T08:00:00Z",
  updated_at: "2026-07-19T08:00:00Z",
};

const input = {
  name: "知识助理",
  description: "通用知识问答",
  system_prompt: "优先依据知识库回答。",
  default_model_configuration_id: employee.default_model_configuration_id,
  knowledge_base_id: "kb-1",
  allowed_workflow_ids: [],
};

describe("employee API boundary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("accepts generated employee snapshots and rejects response drift", () => {
    expect(parseEmployeeResponse(employee)).toEqual(employee);
    expect(parseEmployeesResponse({ items: [employee], next_cursor: null })).toEqual({
      items: [employee],
      next_cursor: null,
    });

    expect(() => parseEmployeeResponse({ ...employee, private_prompt: "secret" })).toThrow();
    expect(() => parseEmployeeResponse({ ...employee, id: "not-a-uuid" })).toThrow();
    expect(() => parseEmployeeResponse({ ...employee, created_at: "not-a-date" })).toThrow();
    expect(() =>
      parseEmployeeResponse({
        ...employee,
        allowed_workflow_ids: [employee.id, employee.id],
      }),
    ).toThrow();
  });

  it("uses only platform employee endpoints for list, detail, create, and update", async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: { items: [employee], next_cursor: null } })
      .mockResolvedValueOnce({ data: employee });
    vi.mocked(apiClient.post).mockResolvedValue({ data: employee });
    vi.mocked(apiClient.put).mockResolvedValue({ data: employee });
    vi.mocked(apiClient.delete).mockResolvedValue({ data: undefined });

    await expect(fetchEmployees()).resolves.toEqual({ items: [employee], next_cursor: null });
    await expect(fetchEmployee(employee.id)).resolves.toEqual(employee);
    await expect(createEmployee(input)).resolves.toEqual(employee);
    await expect(updateEmployee(employee.id, input)).resolves.toEqual(employee);
    await expect(deleteEmployee(employee.id)).resolves.toBeUndefined();

    expect(apiClient.get).toHaveBeenNthCalledWith(1, "/employees", { params: {} });
    expect(apiClient.get).toHaveBeenNthCalledWith(2, `/employees/${employee.id}`);
    expect(apiClient.post).toHaveBeenCalledWith("/employees", input);
    expect(apiClient.put).toHaveBeenCalledWith(`/employees/${employee.id}`, input);
    expect(apiClient.delete).toHaveBeenCalledWith(`/employees/${employee.id}`);
  });
});
