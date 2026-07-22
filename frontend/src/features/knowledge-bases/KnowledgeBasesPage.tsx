import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Empty,
  Flex,
  Form,
  Input,
  Modal,
  Skeleton,
  Space,
  Table,
  Tag,
  Typography,
  type TableColumnsType,
} from "antd";
import { Database, FileText, Plus, RefreshCw } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  fetchKnowledgeBases,
  fetchKnowledgeDocuments,
  type CreateKnowledgeBaseInput,
  type KnowledgeBase,
  type KnowledgeDocument,
} from "../../api/knowledge";
import { getErrorMessage } from "../../api/errors";
import { flattenCursorPages, nextPageCursor } from "../../api/pagination";
import {
  ResourceDeleteButton,
} from "../../components/ResourceDeleteButton";
import { getResourceDeletionErrorMessage } from "../../components/resourceDeletion";
import { KnowledgeUploadQueue } from "./KnowledgeUploadQueue";

const { Text, Title } = Typography;
const parsingStatus = {
  uploaded: { color: "default", label: "已上传" },
  parsing: { color: "processing", label: "解析中" },
  completed: { color: "success", label: "已完成" },
  failed: { color: "error", label: "解析失败" },
} as const;

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}

const documentColumns: TableColumnsType<KnowledgeDocument> = [
  {
    title: "文档",
    dataIndex: "name",
    render: (name: string) => (
      <Space>
        <FileText aria-hidden="true" size={15} />
        <Text>{name}</Text>
      </Space>
    ),
  },
  {
    title: "大小",
    dataIndex: "size_bytes",
    width: 110,
    render: (size: number) => <Text type="secondary">{formatBytes(size)}</Text>,
  },
  {
    title: "状态",
    dataIndex: "parsing_status",
    width: 110,
    render: (status: KnowledgeDocument["parsing_status"]) => {
      const presentation = parsingStatus[status];
      return <Tag color={presentation.color}>{presentation.label}</Tag>;
    },
  },
  {
    title: "失败原因",
    dataIndex: "error_code",
    width: 180,
    render: (code: string | null) =>
      code ? <Text type="danger">{code}</Text> : <Text type="secondary">—</Text>,
  },
];

export function KnowledgeBasesPage({ readOnly = false }: { readOnly?: boolean }) {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteNotice, setDeleteNotice] = useState<string>();
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string>();
  const [uploadBusy, setUploadBusy] = useState(false);
  const [form] = Form.useForm<CreateKnowledgeBaseInput>();

  const knowledgeBases = useInfiniteQuery({
    queryKey: ["knowledge-bases", search],
    queryFn: ({ pageParam }) =>
      fetchKnowledgeBases({ search, limit: 20, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageCursor,
    placeholderData: keepPreviousData,
  });
  const items = useMemo(() => flattenCursorPages(knowledgeBases.data), [knowledgeBases.data]);
  const activeId = useMemo(() => {
    return items.some((item) => item.id === selectedId) ? selectedId : items[0]?.id;
  }, [items, selectedId]);
  const activeKnowledgeBase = items.find((item) => item.id === activeId);

  const documents = useQuery({
    queryKey: ["knowledge-bases", activeId, "documents"],
    queryFn: () => fetchKnowledgeDocuments(activeId ?? ""),
    enabled: Boolean(activeId),
    refetchInterval: (query) => {
      const current = query.state.data;
      return uploadBusy ||
        current?.some(
          (document) =>
            document.parsing_status === "uploaded" || document.parsing_status === "parsing",
        )
        ? 2_000
        : false;
    },
  });

  const createMutation = useMutation({
    mutationFn: (values: CreateKnowledgeBaseInput) => createKnowledgeBase(values),
    onSuccess: async (created) => {
      setSelectedId(created.id);
      setCreateOpen(false);
      form.resetFields();
      await queryClient.resetQueries({ queryKey: ["knowledge-bases"] });
    },
  });

  const refreshDocuments = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] }),
      queryClient.invalidateQueries({ queryKey: ["knowledge-bases", activeId, "documents"] }),
    ]);
  }, [activeId, queryClient]);

  const deleteMutation = useMutation({
    mutationFn: async (knowledgeBase: KnowledgeBase) => {
      setDeleteNotice(undefined);
      await deleteKnowledgeBase(knowledgeBase.id);
      return knowledgeBase;
    },
    onSuccess: async (deleted) => {
      const remaining = items.filter((item) => item.id !== deleted.id);
      queryClient.removeQueries({
        queryKey: ["knowledge-bases", deleted.id, "documents"],
        exact: true,
      });
      setSelectedId(remaining[0]?.id);
      setDeleteNotice(`知识库“${deleted.name}”已删除`);
      await queryClient.resetQueries({ queryKey: ["knowledge-bases"] });
    },
  });

  if (knowledgeBases.isPending) {
    return (
      <section className="knowledge-page" aria-label="知识库加载中">
        <Skeleton active paragraph={{ rows: 8 }} />
      </section>
    );
  }

  if (knowledgeBases.isError) {
    return (
      <section className="knowledge-page">
        <Alert
          type="error"
          showIcon
          title="知识库加载失败"
          description={getErrorMessage(knowledgeBases.error)}
          action={
            <Button
              aria-label="重试加载"
              onClick={() => void knowledgeBases.refetch()}
              icon={<RefreshCw aria-hidden="true" size={16} />}
            >
              重试加载
            </Button>
          }
        />
      </section>
    );
  }

  return (
    <section className="knowledge-page">
      <Flex justify="space-between" align="flex-start" gap={24} className="knowledge-page-heading">
        <div>
          <Space align="center">
            <Database aria-hidden="true" className="knowledge-title-icon" size={22} strokeWidth={1.75} />
            <Title level={2}>知识库</Title>
          </Space>
          <Typography.Paragraph type="secondary">
            创建通用知识库，上传文档并查看 RAGFlow 返回的真实解析状态。
          </Typography.Paragraph>
        </div>
        <Button
          type="primary"
          aria-label="创建知识库"
          icon={<Plus aria-hidden="true" size={16} />}
          disabled={readOnly}
          onClick={() => setCreateOpen(true)}
        >
          创建知识库
        </Button>
      </Flex>

      <Input.Search
        aria-label="搜索知识库"
        allowClear
        value={search}
        placeholder="搜索知识库名称"
        onChange={(event) => setSearch(event.target.value)}
      />

      {deleteNotice && (
        <Alert
          type="success"
          showIcon
          closable
          title={deleteNotice}
          className="knowledge-inline-alert"
        />
      )}

      {deleteMutation.isError && (
        <Alert
          type="error"
          showIcon
          closable
          title="知识库删除失败"
          description={getResourceDeletionErrorMessage(deleteMutation.error)}
          className="knowledge-inline-alert"
          onClose={() => deleteMutation.reset()}
        />
      )}

      {items.length === 0 ? (
        <Card className="knowledge-empty-card">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有知识库">
            <Text type="secondary">创建后即可上传 TXT、Markdown、PDF 或 DOCX 文档。</Text>
          </Empty>
        </Card>
      ) : (
        <div className="knowledge-workspace">
          <Card title={`知识库（${items.length}）`} className="knowledge-list-card">
            <div className="knowledge-base-list">
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  disabled={uploadBusy}
                  className={`knowledge-base-item ${item.id === activeId ? "is-active" : ""}`}
                  onClick={() => setSelectedId(item.id)}
                >
                  <Flex justify="space-between" gap={12}>
                    <Text strong>{item.name}</Text>
                    {item.parsing_count > 0 && <Tag color="processing">{item.parsing_count} 个解析中</Tag>}
                  </Flex>
                  <Text type="secondary" className="knowledge-base-description">
                    {item.description || "暂无描述"}
                  </Text>
                  <Text type="secondary">{item.document_count} 个文档</Text>
                </button>
              ))}
              {knowledgeBases.hasNextPage && (
                <Button
                  block
                  loading={knowledgeBases.isFetchingNextPage}
                  onClick={() => void knowledgeBases.fetchNextPage()}
                >
                  加载更多知识库
                </Button>
              )}
            </div>
          </Card>

          <Card
            title="文档与解析状态"
            className="knowledge-documents-card"
            extra={
              <Space>
                {activeKnowledgeBase && (
                  <ResourceDeleteButton
                    resourceKind="知识库"
                    resourceName={activeKnowledgeBase.name}
                    impact="RAGFlow 中的文档、切片和索引都会被永久删除。"
                    loading={deleteMutation.isPending}
                    disabled={readOnly || deleteMutation.isPending || uploadBusy}
                    onConfirm={() => deleteMutation.mutateAsync(activeKnowledgeBase)}
                  />
                )}
                <Button
                  icon={<RefreshCw aria-hidden="true" size={16} />}
                  loading={documents.isFetching}
                  onClick={() => void documents.refetch()}
                >
                  刷新状态
                </Button>
              </Space>
            }
          >
            {activeId && (
              <KnowledgeUploadQueue
                key={activeId}
                knowledgeBaseId={activeId}
                documents={documents.data ?? []}
                readOnly={readOnly}
                onBusyChange={setUploadBusy}
                onDocumentsChanged={refreshDocuments}
              />
            )}

            {documents.isError ? (
              <Alert
                type="error"
                showIcon
                title="文档状态加载失败"
                description={getErrorMessage(documents.error)}
                action={<Button onClick={() => void documents.refetch()}>重试</Button>}
              />
            ) : (
              <Table
                rowKey="id"
                columns={documentColumns}
                dataSource={documents.data ?? []}
                loading={documents.isPending}
                pagination={false}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无文档" /> }}
              />
            )}
          </Card>
        </div>
      )}

      <Modal
        title="创建知识库"
        open={createOpen}
        okText="确认创建"
        cancelText="取消"
        confirmLoading={createMutation.isPending}
        okButtonProps={{ disabled: readOnly }}
        onOk={() => form.submit()}
        onCancel={() => {
          setCreateOpen(false);
          createMutation.reset();
          form.resetFields();
        }}
      >
        <Form<CreateKnowledgeBaseInput>
          form={form}
          layout="vertical"
          requiredMark={false}
          onFinish={(values) => createMutation.mutate(values)}
        >
          {createMutation.isError && (
            <Alert
              type="error"
              showIcon
              title="创建失败"
              description={getErrorMessage(createMutation.error)}
              className="knowledge-inline-alert"
            />
          )}
          <Form.Item
            label="名称"
            name="name"
            rules={[
              { required: true, whitespace: true, message: "请输入知识库名称" },
              { max: 128, message: "名称不能超过 128 个字符" },
            ]}
          >
            <Input placeholder="例如：通用产品手册" maxLength={128} autoFocus />
          </Form.Item>
          <Form.Item
            label="描述"
            name="description"
            initialValue=""
            rules={[{ max: 1024, message: "描述不能超过 1024 个字符" }]}
          >
            <Input.TextArea placeholder="说明知识库包含的通用资料" rows={4} maxLength={1024} showCount />
          </Form.Item>
        </Form>
      </Modal>
    </section>
  );
}
