import type { KnowledgeDocument } from "../../api/knowledge";

export const MAX_DOCUMENT_SIZE_BYTES = 20 * 1024 * 1024;
export const MAX_UPLOAD_QUEUE_FILES = 20;
export const UPLOAD_CONCURRENCY = 2;

export type KnowledgeUploadStatus =
  | "waiting"
  | "uploading"
  | "uploaded"
  | "parsing"
  | "completed"
  | "failed";

export interface KnowledgeUploadItem {
  id: string;
  fingerprint: string;
  file: File;
  status: KnowledgeUploadStatus;
  documentId?: string;
  error?: string;
  retrying?: boolean;
  retryFailureSamples?: number;
}

export interface KnowledgeUploadSelection {
  accepted: KnowledgeUploadItem[];
  rejected: string[];
}

const supportedTypes: Record<string, ReadonlySet<string>> = {
  ".txt": new Set(["", "text/plain"]),
  ".md": new Set(["", "text/markdown", "text/plain"]),
  ".markdown": new Set(["", "text/markdown", "text/plain"]),
  ".pdf": new Set(["", "application/pdf"]),
  ".docx": new Set([
    "",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ]),
};

export function selectKnowledgeUploadFiles(
  current: KnowledgeUploadItem[],
  documents: KnowledgeDocument[],
  files: Iterable<File>,
): KnowledgeUploadSelection {
  const accepted: KnowledgeUploadItem[] = [];
  const rejected: string[] = [];
  const fingerprints = new Set(current.map((item) => item.fingerprint));
  const existingDocuments = new Set(
    documents.map((document) => `${document.name.toLowerCase()}:${document.size_bytes}`),
  );

  for (const file of files) {
    if (current.length + accepted.length >= MAX_UPLOAD_QUEUE_FILES) {
      rejected.push(`${file.name}：一次最多加入 ${MAX_UPLOAD_QUEUE_FILES} 份文档`);
      continue;
    }
    const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    const acceptedTypes = supportedTypes[extension];
    if (!acceptedTypes?.has(file.type.toLowerCase())) {
      rejected.push(`${file.name}：不支持的文件类型`);
      continue;
    }
    if (file.size === 0) {
      rejected.push(`${file.name}：文档内容不能为空`);
      continue;
    }
    if (file.size > MAX_DOCUMENT_SIZE_BYTES) {
      rejected.push(`${file.name}：文件大小超过 20 MiB`);
      continue;
    }
    const fingerprint = fileFingerprint(file);
    const existingKey = `${file.name.toLowerCase()}:${file.size}`;
    if (fingerprints.has(fingerprint) || existingDocuments.has(existingKey)) {
      rejected.push(`${file.name}：文档已存在或已在队列中`);
      continue;
    }
    fingerprints.add(fingerprint);
    accepted.push({
      id: fingerprint,
      fingerprint,
      file,
      status: "waiting",
    });
  }
  return { accepted, rejected };
}

export function statusFromDocument(
  document: KnowledgeDocument,
): Exclude<KnowledgeUploadStatus, "waiting" | "uploading"> {
  return document.parsing_status;
}

function fileFingerprint(file: File): string {
  return `${file.name.toLowerCase()}:${file.size}`;
}
