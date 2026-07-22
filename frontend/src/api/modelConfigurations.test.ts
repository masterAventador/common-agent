import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import {
  createModelConfiguration,
  deleteModelConfiguration,
  fetchModelConfiguration,
  fetchModelConfigurations,
  parseModelConfigurationResponse,
  parseModelConfigurationsResponse,
  parseModelConfigurationVerification,
  updateModelConfiguration,
  verifyModelConfiguration,
} from "./modelConfigurations";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const model = {
  id: "10000000-0000-4000-8000-000000000018",
  display_name: "Qwen Plus",
  provider: "bailian" as const,
  model_identifier: "qwen-plus",
  enabled: true,
  created_at: "2026-07-22T02:00:00Z",
  updated_at: "2026-07-22T02:00:00Z",
};
const input = {
  display_name: model.display_name,
  model_identifier: model.model_identifier,
  enabled: true,
};
const verification = {
  status: "available" as const,
  model_identifier: "qwen-plus",
  response_preview: "连接成功",
};

describe("model configuration API boundary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("accepts only the tenant model and safe verification contracts", () => {
    expect(parseModelConfigurationResponse(model)).toEqual(model);
    expect(parseModelConfigurationsResponse({ items: [model], next_cursor: null })).toEqual({
      items: [model],
      next_cursor: null,
    });
    expect(parseModelConfigurationVerification(verification)).toEqual(verification);

    expect(() => parseModelConfigurationResponse({ ...model, provider: "openai" })).toThrow();
    expect(() => parseModelConfigurationResponse({ ...model, api_key: "secret" })).toThrow();
    expect(() =>
      parseModelConfigurationResponse({ ...model, model_identifier: "../unsafe" }),
    ).toThrow();
    expect(() =>
      parseModelConfigurationVerification({ ...verification, status: "unknown" }),
    ).toThrow();
  });

  it("uses only formal platform endpoints for filtered list, CRUD, and verification", async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: { items: [model], next_cursor: null } })
      .mockResolvedValueOnce({ data: model });
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce({ data: model })
      .mockResolvedValueOnce({ data: verification });
    vi.mocked(apiClient.put).mockResolvedValue({ data: model });
    vi.mocked(apiClient.delete).mockResolvedValue({ data: undefined });

    await expect(
      fetchModelConfigurations({ search: "Qwen", limit: 20, cursor: "next" }, true),
    ).resolves.toEqual({ items: [model], next_cursor: null });
    await expect(fetchModelConfiguration(model.id)).resolves.toEqual(model);
    await expect(createModelConfiguration(input)).resolves.toEqual(model);
    await expect(updateModelConfiguration("model/with space", input)).resolves.toEqual(model);
    await expect(verifyModelConfiguration("model/with space")).resolves.toEqual(verification);
    await expect(deleteModelConfiguration("model/with space")).resolves.toBeUndefined();

    expect(apiClient.get).toHaveBeenCalledWith("/model-configurations", {
      params: { search: "Qwen", limit: 20, cursor: "next", enabled_only: true },
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      `/model-configurations/${model.id}`,
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(1, "/model-configurations", input);
    expect(apiClient.put).toHaveBeenCalledWith("/model-configurations/model%2Fwith%20space", input);
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      "/model-configurations/model%2Fwith%20space/verify",
    );
    expect(apiClient.delete).toHaveBeenCalledWith(
      "/model-configurations/model%2Fwith%20space",
    );
  });
});
