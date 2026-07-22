import { Buffer } from "node:buffer";

import { expect, platformApiUrl, platformWriteHeaders, test } from "./fixtures/auth";

const MEBIBYTE = 1024 * 1024;
const DOCUMENT_LIMIT_BYTES = 20 * MEBIBYTE;
const EDGE_BODY_LIMIT_BYTES = 24 * MEBIBYTE;
const missingKnowledgeBasePath =
  platformApiUrl("/knowledge-bases/missing-production-request-limit/documents");

test("enforces document and edge body limits through the production TLS entry", async ({
  page,
}) => {
  const headers = await platformWriteHeaders(page);
  const acceptedByEdge = await page.request.post(missingKnowledgeBasePath, {
    headers,
    multipart: {
      file: {
        name: "two-mebibytes.txt",
        mimeType: "text/plain",
        buffer: Buffer.alloc(2 * MEBIBYTE, 0x61),
      },
    },
  });
  expect(acceptedByEdge.status()).toBe(404);
  expect((await acceptedByEdge.json()) as { code: string }).toMatchObject({
    code: "knowledge_base_not_found",
  });

  const rejectedByApplication = await page.request.post(missingKnowledgeBasePath, {
    headers,
    multipart: {
      file: {
        name: "over-document-limit.txt",
        mimeType: "text/plain",
        buffer: Buffer.alloc(DOCUMENT_LIMIT_BYTES + 1, 0x61),
      },
    },
  });
  expect(rejectedByApplication.status()).toBe(413);
  expect((await rejectedByApplication.json()) as { code: string }).toMatchObject({
    code: "document_too_large",
  });

  const rejectedByEdge = await page.request.post(missingKnowledgeBasePath, {
    headers,
    multipart: {
      file: {
        name: "over-edge-limit.txt",
        mimeType: "text/plain",
        buffer: Buffer.alloc(EDGE_BODY_LIMIT_BYTES, 0x61),
      },
    },
  });
  expect(rejectedByEdge.status()).toBe(413);
  expect(rejectedByEdge.headers()["content-type"]).toContain("text/html");
});
