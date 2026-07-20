import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  fetchKnowledgeBases,
  fetchKnowledgeDocuments,
  parseKnowledgeBasesResponse,
  parseKnowledgeDocumentsResponse,
  uploadKnowledgeDocument,
} from "./knowledge";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const knowledgeBase = {
  id: "kb-1",
  name: "产品手册",
  description: "通用产品资料",
  document_count: 1,
  parsing_count: 0,
};

const document = {
  id: "doc-1",
  knowledge_base_id: "kb-1",
  name: "manual.txt",
  size_bytes: 12,
  parsing_status: "completed" as const,
  error_code: null,
};

describe("knowledge API boundary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("accepts the generated knowledge snapshots and rejects schema drift", () => {
    expect(parseKnowledgeBasesResponse({ items: [knowledgeBase], next_cursor: null })).toEqual({
      items: [knowledgeBase],
      next_cursor: null,
    });
    expect(parseKnowledgeDocumentsResponse([document])).toEqual([document]);

    expect(() =>
      parseKnowledgeBasesResponse({
        items: [{ ...knowledgeBase, private_token: "secret" }],
        next_cursor: null,
      }),
    ).toThrow();
    expect(() =>
      parseKnowledgeDocumentsResponse([{ ...document, parsing_status: "unknown" }]),
    ).toThrow();
  });

  it("uses only the platform API for list and create operations", async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: { items: [knowledgeBase], next_cursor: null } })
      .mockResolvedValueOnce({ data: [document] });
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: knowledgeBase });
    vi.mocked(apiClient.delete).mockResolvedValue({ data: undefined });

    await expect(fetchKnowledgeBases()).resolves.toEqual({
      items: [knowledgeBase],
      next_cursor: null,
    });
    await expect(createKnowledgeBase({ name: "产品手册", description: "通用产品资料" })).resolves.toEqual(
      knowledgeBase,
    );
    await expect(fetchKnowledgeDocuments("kb-1")).resolves.toEqual([document]);
    await expect(deleteKnowledgeBase("kb/with space")).resolves.toBeUndefined();

    expect(apiClient.get).toHaveBeenNthCalledWith(1, "/knowledge-bases", { params: {} });
    expect(apiClient.post).toHaveBeenCalledWith("/knowledge-bases", {
      name: "产品手册",
      description: "通用产品资料",
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(2, "/knowledge-bases/kb-1/documents");
    expect(apiClient.delete).toHaveBeenCalledWith("/knowledge-bases/kb%2Fwith%20space");
  });

  it("uploads a multipart file through the platform API", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: document });
    const file = new File(["hello"], "manual.txt", { type: "text/plain" });

    await expect(uploadKnowledgeDocument("kb/with space", file)).resolves.toEqual(document);

    expect(apiClient.post).toHaveBeenCalledWith(
      "/knowledge-bases/kb%2Fwith%20space/documents",
      expect.any(FormData),
      expect.objectContaining({ timeout: 60_000 }),
    );
    const form = vi.mocked(apiClient.post).mock.calls[0]?.[1];
    expect(form).toBeInstanceOf(FormData);
    expect((form as FormData).get("file")).toBe(file);
  });
});
