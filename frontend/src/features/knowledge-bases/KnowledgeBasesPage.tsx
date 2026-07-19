import {
  CloudUploadOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { useMemo, useState } from "react";

import {
  createKnowledgeBase,
  fetchKnowledgeBases,
  fetchKnowledgeDocuments,
  uploadKnowledgeDocument,
  type CreateKnowledgeBaseInput,
  type KnowledgeDocument,
} from "../../api/knowledge";

const { Text, Title } = Typography;
const ACCEPTED_DOCUMENTS =
  ".txt,.md,.markdown,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

const parsingStatus = {
  uploaded: { color: "default", label: "已上传" },
  parsing: { color: "processing", label: "解析中" },
  completed: { color: "success", label: "已完成" },
  failed: { color: "error", label: "解析失败" },
} as const;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "请求失败，请稍后重试";
}

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
        <FileTextOutlined />
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

export function KnowledgeBasesPage() {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string>();
  const [selectedFile, setSelectedFile] = useState<File>();
  const [fileInputKey, setFileInputKey] = useState(0);
  const [form] = Form.useForm<CreateKnowledgeBaseInput>();

  const knowledgeBases = useQuery({
    queryKey: ["knowledge-bases"],
    queryFn: fetchKnowledgeBases,
  });
  const activeId = useMemo(() => {
    const items = knowledgeBases.data ?? [];
    return items.some((item) => item.id === selectedId) ? selectedId : items[0]?.id;
  }, [knowledgeBases.data, selectedId]);

  const documents = useQuery({
    queryKey: ["knowledge-bases", activeId, "documents"],
    queryFn: () => fetchKnowledgeDocuments(activeId ?? ""),
    enabled: Boolean(activeId),
    refetchInterval: (query) => {
      const current = query.state.data;
      return current?.some(
        (document) => document.parsing_status === "uploaded" || document.parsing_status === "parsing",
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
      await queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
    },
  });

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!activeId || !selectedFile) throw new Error("请先选择知识库和文档");
      return uploadKnowledgeDocument(activeId, selectedFile);
    },
    onSuccess: async () => {
      setSelectedFile(undefined);
      setFileInputKey((value) => value + 1);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] }),
        queryClient.invalidateQueries({ queryKey: ["knowledge-bases", activeId, "documents"] }),
      ]);
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
          description={errorMessage(knowledgeBases.error)}
          action={
            <Button
              aria-label="重试加载"
              onClick={() => void knowledgeBases.refetch()}
              icon={<ReloadOutlined />}
            >
              重试加载
            </Button>
          }
        />
      </section>
    );
  }

  const items = knowledgeBases.data;

  return (
    <section className="knowledge-page">
      <Flex justify="space-between" align="flex-start" gap={24} className="knowledge-page-heading">
        <div>
          <Space align="center">
            <DatabaseOutlined className="knowledge-title-icon" />
            <Title level={2}>知识库</Title>
          </Space>
          <Typography.Paragraph type="secondary">
            创建通用知识库，上传文档并查看 RAGFlow 返回的真实解析状态。
          </Typography.Paragraph>
        </div>
        <Button
          type="primary"
          aria-label="创建知识库"
          icon={<PlusOutlined />}
          onClick={() => setCreateOpen(true)}
        >
          创建知识库
        </Button>
      </Flex>

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
            </div>
          </Card>

          <Card
            title="文档与解析状态"
            className="knowledge-documents-card"
            extra={
              <Button
                icon={<ReloadOutlined />}
                loading={documents.isFetching}
                onClick={() => void documents.refetch()}
              >
                刷新状态
              </Button>
            }
          >
            <Flex gap={12} align="center" wrap className="knowledge-upload-row">
              <label className="knowledge-file-picker">
                <CloudUploadOutlined /> 选择文档
                <input
                  key={fileInputKey}
                  type="file"
                  aria-label="选择文档"
                  accept={ACCEPTED_DOCUMENTS}
                  onChange={(event) => setSelectedFile(event.target.files?.[0])}
                />
              </label>
              <Text type="secondary">{selectedFile?.name ?? "尚未选择文件（最大 20 MiB）"}</Text>
              <Button
                type="primary"
                disabled={!selectedFile}
                loading={uploadMutation.isPending}
                onClick={() => uploadMutation.mutate()}
              >
                上传文档
              </Button>
            </Flex>

            {uploadMutation.isError && (
              <Alert
                type="error"
                showIcon
                closable
                title="文档上传失败"
                description={errorMessage(uploadMutation.error)}
                className="knowledge-inline-alert"
                onClose={() => uploadMutation.reset()}
              />
            )}

            {documents.isError ? (
              <Alert
                type="error"
                showIcon
                title="文档状态加载失败"
                description={errorMessage(documents.error)}
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
              description={errorMessage(createMutation.error)}
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
