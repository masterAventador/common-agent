import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Alert, Button, Skeleton, Space, Tag, Typography } from "antd";
import { ArrowLeft, FileText } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getErrorMessage } from "../../api/errors";
import {
  fetchDocumentChunks,
  fetchKnowledgeBase,
  fetchKnowledgeDocuments,
  type DocumentChunk,
} from "../../api/knowledge";
import { flattenCursorPages, nextPageCursor } from "../../api/pagination";

const { Text, Title } = Typography;

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}

/**
 * 文档详情：左侧按切片顺序还原正文，右侧列出切片，点击切片在左侧定位。
 *
 * 左侧不做原版式预览：PDF 与 DOCX 各自都要额外的渲染/转换依赖，会撑破单路由包体门禁，
 * 且只覆盖部分格式。切片本身就是解析后的全文分段，按顺序拼接即正文，TXT/Markdown/PDF/DOCX
 * 四种格式因此统一可读，也让「点切片定位原文」这个核心交互天然成立。
 */
export function KnowledgeDocumentPage() {
  const { knowledgeBaseId = "", documentId = "" } = useParams();
  const [activeChunkId, setActiveChunkId] = useState<string>();

  const knowledgeBase = useQuery({
    queryKey: ["knowledge-base", knowledgeBaseId],
    queryFn: () => fetchKnowledgeBase(knowledgeBaseId),
    enabled: Boolean(knowledgeBaseId),
  });
  const documents = useQuery({
    queryKey: ["knowledge-bases", knowledgeBaseId, "documents"],
    queryFn: () => fetchKnowledgeDocuments(knowledgeBaseId),
    enabled: Boolean(knowledgeBaseId),
  });
  const chunks = useInfiniteQuery({
    queryKey: ["knowledge-bases", knowledgeBaseId, "documents", documentId, "chunks"],
    queryFn: ({ pageParam }) =>
      fetchDocumentChunks(knowledgeBaseId, documentId, { limit: 50, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageCursor,
    enabled: Boolean(knowledgeBaseId && documentId),
  });

  const document = documents.data?.find((item) => item.id === documentId);
  const items = flattenCursorPages(chunks.data);

  return (
    <section className="knowledge-document-page">
      <div className="knowledge-document-heading">
        <Link to="/knowledge-bases" aria-label="返回知识库列表">
          <Button icon={<ArrowLeft aria-hidden="true" size={16} />} aria-hidden="true" />
        </Link>
        <div className="knowledge-document-identity">
          <Title level={2}>{document?.name ?? "文档"}</Title>
          <Space size={4} wrap>
            <Text type="secondary">{knowledgeBase.data?.name ?? "知识库"}</Text>
            {document ? (
              <>
                <Text type="secondary">·</Text>
                <Text type="secondary">{formatBytes(document.size_bytes)}</Text>
              </>
            ) : null}
            {items.length ? (
              <>
                <Text type="secondary">·</Text>
                <Text type="secondary">{items.length} 段</Text>
              </>
            ) : null}
          </Space>
        </div>
      </div>

      {chunks.isError ? (
        <Alert
          type="error"
          showIcon
          title="切片加载失败"
          description={getErrorMessage(chunks.error)}
          action={
            <Space>
              <Button onClick={() => void chunks.refetch()}>重试加载</Button>
              <Link to="/knowledge-bases">返回知识库</Link>
            </Space>
          }
        />
      ) : (
        <div className="knowledge-document-workspace">
          <article
            className="knowledge-document-preview"
            role="region"
            aria-label="文档预览"
          >
            <div className="knowledge-panel-heading">
              <Text strong>正文预览</Text>
              <Text type="secondary">按切片顺序还原</Text>
            </div>
            <div className="knowledge-preview-body">
              {chunks.isPending ? (
                <Skeleton active paragraph={{ rows: 10 }} />
              ) : items.length === 0 ? (
                <Text type="secondary">该文档还没有解析出可展示的正文。</Text>
              ) : (
                items.map((chunk) => (
                  <p
                    key={chunk.id}
                    id={`preview-${chunk.id}`}
                    className={`knowledge-preview-block${
                      chunk.id === activeChunkId ? " is-active" : ""
                    }`}
                  >
                    {chunk.content}
                  </p>
                ))
              )}
            </div>
          </article>

          <aside className="knowledge-chunk-list" role="region" aria-label="切片列表">
            <div className="knowledge-panel-heading">
              <Text strong>切片列表</Text>
              <Text type="secondary">点击切片可在左侧定位原文</Text>
            </div>
            <div className="knowledge-chunk-body">
              {chunks.isPending ? (
                <Skeleton active paragraph={{ rows: 6 }} />
              ) : items.length === 0 ? (
                <Text type="secondary">暂无切片</Text>
              ) : (
                items.map((chunk) => (
                  <ChunkCard
                    key={chunk.id}
                    chunk={chunk}
                    active={chunk.id === activeChunkId}
                    onSelect={() => {
                      setActiveChunkId(chunk.id);
                      window.document
                        .getElementById(`preview-${chunk.id}`)
                        ?.scrollIntoView({ block: "center" });
                    }}
                  />
                ))
              )}
              {chunks.hasNextPage ? (
                <Button
                  block
                  loading={chunks.isFetchingNextPage}
                  onClick={() => void chunks.fetchNextPage()}
                >
                  加载更多切片
                </Button>
              ) : null}
            </div>
          </aside>
        </div>
      )}
    </section>
  );
}

function ChunkCard({
  chunk,
  active,
  onSelect,
}: {
  chunk: DocumentChunk;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`knowledge-chunk-item${active ? " is-active" : ""}`}
      aria-label={`切片 ${chunk.position}`}
      aria-pressed={active}
      onClick={onSelect}
    >
      <div className="knowledge-chunk-meta">
        <Tag>{`#${chunk.position}`}</Tag>
        <Text type="secondary">
          <FileText aria-hidden="true" size={13} /> {chunk.content.length} 字
        </Text>
      </div>
      <Text className="knowledge-chunk-text">{chunk.content}</Text>
    </button>
  );
}
