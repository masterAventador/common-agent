import { Alert, Button, Flex, Progress, Tag, Typography } from "antd";
import { FileUp, Play, RotateCcw, Trash2, UploadCloud } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  retryKnowledgeDocument,
  uploadKnowledgeDocument,
  type KnowledgeDocument,
} from "../../api/knowledge";
import { getErrorMessage } from "../../api/errors";
import {
  selectKnowledgeUploadFiles,
  statusFromDocument,
  UPLOAD_CONCURRENCY,
  type KnowledgeUploadItem,
  type KnowledgeUploadStatus,
} from "./knowledgeUploadModel";

const { Text } = Typography;
const ACCEPTED_DOCUMENTS =
  ".txt,.md,.markdown,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const RETRY_STALE_FAILURE_SAMPLES = 1;

const statusPresentation: Record<KnowledgeUploadStatus, { color: string; label: string }> = {
  waiting: { color: "default", label: "等待上传" },
  uploading: { color: "processing", label: "正在上传" },
  uploaded: { color: "cyan", label: "已上传" },
  parsing: { color: "processing", label: "解析中" },
  completed: { color: "success", label: "已完成" },
  failed: { color: "error", label: "失败" },
};

export function KnowledgeUploadQueue({
  knowledgeBaseId,
  documents,
  readOnly = false,
  onDocumentsChanged,
  onBusyChange,
}: {
  knowledgeBaseId: string;
  documents: KnowledgeDocument[];
  readOnly?: boolean;
  onDocumentsChanged: () => void | Promise<void>;
  onBusyChange?: (busy: boolean) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const batchRefreshPending = useRef(false);
  const [items, setItems] = useState<KnowledgeUploadItem[]>([]);
  const [rejected, setRejected] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [dragging, setDragging] = useState(false);
  const busy = items.some(
    (item) => item.status === "waiting" || item.status === "uploading" || item.retrying,
  );
  const waiting = items.some((item) => item.status === "waiting");
  const settled = items.filter(
    (item) => item.status === "completed" || item.status === "failed",
  ).length;
  const progress = items.length === 0 ? 0 : Math.round((settled / items.length) * 100);

  const addFiles = useCallback(
    (files: Iterable<File>) => {
      setItems((current) => {
        const selection = selectKnowledgeUploadFiles(current, documents, files);
        setRejected(selection.rejected);
        return [...current, ...selection.accepted];
      });
    },
    [documents],
  );

  const refreshWithoutChangingUploadStatus = useCallback(async () => {
    try {
      await onDocumentsChanged();
    } catch {
      return;
    }
  }, [onDocumentsChanged]);

  useEffect(() => onBusyChange?.(busy), [busy, onBusyChange]);

  useEffect(() => {
    if (running && !busy) setRunning(false);
  }, [busy, running]);

  useEffect(() => {
    const hasUploadWork = items.some(
      (item) => item.status === "waiting" || item.status === "uploading",
    );
    if (hasUploadWork || !batchRefreshPending.current) return;
    batchRefreshPending.current = false;
    void refreshWithoutChangingUploadStatus();
  }, [items, refreshWithoutChangingUploadStatus]);

  useEffect(() => {
    setItems((current) =>
      current.map((item) => {
        if (!item.documentId || item.status === "uploading") return item;
        const document = documents.find((value) => value.id === item.documentId);
        if (!document) return item;
        if (
          item.retrying &&
          document.parsing_status === "failed" &&
          (item.retryFailureSamples ?? 0) < RETRY_STALE_FAILURE_SAMPLES
        ) {
          return { ...item, retryFailureSamples: (item.retryFailureSamples ?? 0) + 1 };
        }
        const status = statusFromDocument(document);
        const error = status === "failed" ? document.error_code ?? "文档解析失败" : undefined;
        if (status === item.status && error === item.error && !item.retrying) return item;
        return { ...item, status, error, retrying: false, retryFailureSamples: undefined };
      }),
    );
  }, [documents]);

  useEffect(() => {
    if (!running) return;
    const uploading = items.filter((item) => item.status === "uploading").length;
    const selected = items
      .filter((item) => item.status === "waiting")
      .slice(0, Math.max(0, UPLOAD_CONCURRENCY - uploading));
    if (selected.length === 0) return;
    const selectedIds = new Set(selected.map((item) => item.id));
    setItems((current) =>
      current.map((item) =>
        selectedIds.has(item.id) ? { ...item, status: "uploading", error: undefined } : item,
      ),
    );
    for (const item of selected) void runUpload(item);

    async function runUpload(item: KnowledgeUploadItem) {
      let document: KnowledgeDocument;
      try {
        document = item.documentId
          ? await retryKnowledgeDocument(knowledgeBaseId, item.documentId)
          : await uploadKnowledgeDocument(knowledgeBaseId, item.file);
      } catch (error) {
        setItems((current) =>
          current.map((value) =>
            value.id === item.id
              ? {
                  ...value,
                  status: "failed",
                  error: getErrorMessage(error),
                  retrying: false,
                  retryFailureSamples: undefined,
                }
              : value,
          ),
        );
        return;
      }

      if (!item.documentId) batchRefreshPending.current = true;
      setItems((current) =>
        current.map((value) =>
          value.id === item.id
            ? {
                ...value,
                documentId: document.id,
                status: statusFromDocument(document),
                retrying: Boolean(item.documentId),
                retryFailureSamples: 0,
              }
            : value,
        ),
      );
      if (item.documentId) await refreshWithoutChangingUploadStatus();
    }
  }, [items, knowledgeBaseId, refreshWithoutChangingUploadStatus, running]);

  const queueRows = useMemo(
    () =>
      items.map((item) => {
        const presentation = statusPresentation[item.status];
        return (
          <div className="knowledge-upload-item" key={item.id}>
            <Flex align="center" justify="space-between" gap={12}>
              <Flex vertical gap={2} className="knowledge-upload-item-copy">
                <Text strong>{item.file.name}</Text>
                <Text type="secondary">{formatBytes(item.file.size)}</Text>
                {item.error && <Text type="danger">{item.error}</Text>}
              </Flex>
              <Flex align="center" gap={8}>
                <Tag color={presentation.color}>{presentation.label}</Tag>
                {item.status === "failed" && (
                  <Button
                    size="small"
                    icon={<RotateCcw aria-hidden="true" size={14} />}
                    aria-label={`重试 ${item.file.name}`}
                    disabled={readOnly}
                    onClick={() => {
                      setRunning(true);
                      setItems((current) =>
                        current.map((value) =>
                          value.id === item.id
                            ? {
                                ...value,
                                status: "waiting",
                                error: undefined,
                                retryFailureSamples: 0,
                              }
                            : value,
                        ),
                      );
                    }}
                  >
                    重试
                  </Button>
                )}
                {item.status === "waiting" && (
                  <Button
                    size="small"
                    type="text"
                    danger
                    icon={<Trash2 aria-hidden="true" size={14} />}
                    aria-label={`移除 ${item.file.name}`}
                    onClick={() => setItems((current) => current.filter((value) => value.id !== item.id))}
                  />
                )}
              </Flex>
            </Flex>
          </div>
        );
      }),
    [items, readOnly],
  );

  return (
    <div className="knowledge-upload-queue">
      <div
        role="button"
        tabIndex={readOnly ? -1 : 0}
        aria-label="拖拽上传区域"
        className={`knowledge-upload-dropzone ${dragging ? "is-dragging" : ""}`}
        onClick={() => !readOnly && inputRef.current?.click()}
        onKeyDown={(event) => {
          if (!readOnly && (event.key === "Enter" || event.key === " ")) inputRef.current?.click();
        }}
        onDragEnter={(event) => {
          event.preventDefault();
          if (!readOnly) setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (!readOnly) addFiles(event.dataTransfer.files);
        }}
      >
        <UploadCloud aria-hidden="true" size={24} />
        <Text strong>拖拽文档到这里，或点击批量选择</Text>
        <Text type="secondary">支持 TXT、Markdown、PDF、DOCX；单文件最大 20 MiB</Text>
        <input
          ref={inputRef}
          type="file"
          multiple
          aria-label="选择或拖拽文档"
          disabled={readOnly}
          accept={ACCEPTED_DOCUMENTS}
          onClick={(event) => event.stopPropagation()}
          onChange={(event) => {
            if (event.target.files) addFiles(event.target.files);
            event.target.value = "";
          }}
        />
      </div>

      {rejected.length > 0 && (
        <Alert
          type="warning"
          showIcon
          closable
          title="部分文件未加入队列"
          description={rejected.map((message) => <div key={message}>{message}</div>)}
          onClose={() => setRejected([])}
        />
      )}

      {items.length > 0 && (
        <div className="knowledge-upload-list">
          <Flex align="center" justify="space-between" gap={12}>
            <Flex align="center" gap={8}>
              <FileUp aria-hidden="true" size={16} />
              <Text strong>上传队列（{items.length}）</Text>
            </Flex>
            <Flex gap={8}>
              <Button
                icon={<Play aria-hidden="true" size={14} />}
                disabled={readOnly || !waiting}
                onClick={() => setRunning(true)}
              >
                开始上传
              </Button>
              <Button
                disabled={busy}
                onClick={() => setItems((current) => current.filter((item) => item.status !== "completed"))}
              >
                清除已完成
              </Button>
            </Flex>
          </Flex>
          <Progress percent={progress} size="small" />
          {queueRows}
        </div>
      )}
    </div>
  );
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}
