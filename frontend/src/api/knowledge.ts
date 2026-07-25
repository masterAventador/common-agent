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

export type KnowledgeBase = components["schemas"]["KnowledgeBaseResponse"];
export type KnowledgeDocument = components["schemas"]["KnowledgeDocumentResponse"];
export type CreateKnowledgeBaseInput = components["schemas"]["CreateKnowledgeBaseBody"];

const knowledgeBaseSchema = z.strictObject({
  id: z.string().min(1),
  name: z.string().min(1),
  description: z.string(),
  document_count: z.number().int().nonnegative(),
  parsing_count: z.number().int().nonnegative(),
});

const knowledgeDocumentSchema = z.strictObject({
  id: z.string().min(1),
  knowledge_base_id: z.string().min(1),
  name: z.string().min(1),
  size_bytes: z.number().int().nonnegative(),
  parsing_status: z.enum(["uploaded", "parsing", "completed", "failed"]),
  error_code: z.string().min(1).nullable(),
});

const knowledgeBasesSchema = cursorPageSchema(knowledgeBaseSchema);
const knowledgeDocumentsSchema = z.array(knowledgeDocumentSchema);

export function parseKnowledgeBasesResponse(data: unknown): CursorPage<KnowledgeBase> {
  return knowledgeBasesSchema.parse(data);
}

export function parseKnowledgeDocumentsResponse(data: unknown): KnowledgeDocument[] {
  return knowledgeDocumentsSchema.parse(data);
}

function parseKnowledgeBaseResponse(data: unknown): KnowledgeBase {
  return knowledgeBaseSchema.parse(data);
}

function parseKnowledgeDocumentResponse(data: unknown): KnowledgeDocument {
  return knowledgeDocumentSchema.parse(data);
}

export async function fetchKnowledgeBases(
  page: ListPageRequest = {},
): Promise<CursorPage<KnowledgeBase>> {
  try {
    const response = await apiClient.get<unknown>("/knowledge-bases", {
      params: listPageParams(page),
    });
    return parseKnowledgeBasesResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function createKnowledgeBase(
  input: CreateKnowledgeBaseInput,
): Promise<KnowledgeBase> {
  try {
    const response = await apiClient.post<unknown>("/knowledge-bases", input);
    return parseKnowledgeBaseResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function updateKnowledgeBase(
  knowledgeBaseId: string,
  input: CreateKnowledgeBaseInput,
): Promise<KnowledgeBase> {
  try {
    const response = await apiClient.patch<unknown>(
      `/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}`,
      input,
    );
    return parseKnowledgeBaseResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function deleteKnowledgeBase(knowledgeBaseId: string): Promise<void> {
  try {
    await apiClient.delete(`/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}`);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function fetchKnowledgeDocuments(
  knowledgeBaseId: string,
): Promise<KnowledgeDocument[]> {
  try {
    const response = await apiClient.get<unknown>(
      `/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/documents`,
    );
    return parseKnowledgeDocumentsResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function uploadKnowledgeDocument(
  knowledgeBaseId: string,
  file: File,
): Promise<KnowledgeDocument> {
  const body = new FormData();
  body.append("file", file);
  try {
    const response = await apiClient.post<unknown>(
      `/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/documents`,
      body,
      { timeout: 60_000 },
    );
    return parseKnowledgeDocumentResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}

export async function retryKnowledgeDocument(
  knowledgeBaseId: string,
  documentId: string,
): Promise<KnowledgeDocument> {
  try {
    const response = await apiClient.post<unknown>(
      `/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/documents/${encodeURIComponent(documentId)}/retry`,
      undefined,
      { timeout: 60_000 },
    );
    return parseKnowledgeDocumentResponse(response.data);
  } catch (error) {
    throw toApiClientError(error);
  }
}
