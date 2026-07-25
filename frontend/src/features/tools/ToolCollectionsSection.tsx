import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Flex,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Skeleton,
  Space,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { Pencil, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getErrorMessage } from "../../api/errors";
import { toast } from "../../components/toast";
import {
  createToolCollection,
  deleteToolCollection,
  fetchToolCatalog,
  updateToolCollection,
  type ToolCatalog,
  type ToolCollection,
  type ToolCollectionInput,
} from "../../api/tools";
import { ResourceDeleteButton } from "../../components/ResourceDeleteButton";

const { Paragraph, Text, Title } = Typography;
const catalogQueryKey = ["tool-catalog"] as const;

type CollectionEditor =
  | { mode: "create" }
  | { mode: "edit"; collection: ToolCollection };

function editorValues(collection?: ToolCollection): ToolCollectionInput {
  return collection
    ? {
        name: collection.name,
        description: collection.description,
        source_ids: collection.source_ids,
      }
    : { name: "", description: "", source_ids: [] };
}

function collectionState(catalog: ToolCatalog, collection: ToolCollection) {
  const sourceIds = new Set(collection.source_ids);
  const sources = catalog.sources.filter((source) => sourceIds.has(source.id));
  const capabilities = catalog.capabilities.filter((item) => sourceIds.has(item.source_id));
  const active = capabilities.filter((item) => item.status === "active").length;
  if (
    sources.length === collection.source_ids.length &&
    sources.every((source) => source.status === "ready") &&
    capabilities.length > 0 &&
    active === capabilities.length
  ) {
    return { label: "可用", color: "success", active, total: capabilities.length };
  }
  if (active > 0) {
    return { label: "部分可用", color: "warning", active, total: capabilities.length };
  }
  return { label: "暂不可用", color: "error", active, total: capabilities.length };
}

export function ToolCollectionsSection({ readOnly }: { readOnly: boolean }) {
  const queryClient = useQueryClient();
  const [editor, setEditor] = useState<CollectionEditor>();
  const [form] = Form.useForm<ToolCollectionInput>();
  const query = useQuery({ queryKey: catalogQueryKey, queryFn: fetchToolCatalog });
  const catalog = query.data;

  useEffect(() => {
    if (!editor) return;
    form.setFieldsValue(
      editorValues(editor.mode === "edit" ? editor.collection : undefined),
    );
  }, [editor, form]);

  const refresh = () => queryClient.invalidateQueries({ queryKey: catalogQueryKey });
  const save = useMutation({
    mutationFn: (values: ToolCollectionInput) =>
      editor?.mode === "edit"
        ? updateToolCollection(editor.collection.id, values)
        : createToolCollection(values),
    onSuccess: async () => {
      setEditor(undefined);
      form.resetFields();
      await refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (collectionId: string) => deleteToolCollection(collectionId),
    onSuccess: refresh,
    onError: (error) => toast.error(`业务工具集删除失败：${getErrorMessage(error)}`),
  });
  const selectableSources = useMemo(
    () =>
      (catalog?.sources ?? [])
        .filter((source) => source.source_type !== "platform")
        .map((source) => ({
          value: source.id,
          label: `${source.name} · ${
            source.source_type === "managed_http" ? "平台托管" : "外部 MCP"
          }`,
        })),
    [catalog?.sources],
  );

  return (
    <section className="tools-section" aria-labelledby="tool-collections-title">
      <Flex justify="space-between" align="flex-start" gap={16} wrap>
        <div>
          <Title level={3} id="tool-collections-title">业务工具集</Title>
          <Paragraph type="secondary">
            聚合多个 MCP 来源；授权时保存当时的精确能力快照，后续新增能力不会自动扩权。
          </Paragraph>
        </div>
        <Tooltip
          title={
            !readOnly && selectableSources.length === 0
              ? "请先在上方创建平台托管 MCP 或外部 MCP 来源，业务工具集需要关联至少一个来源"
              : undefined
          }
        >
          <Button
            icon={<Plus size={16} />}
            disabled={readOnly || selectableSources.length === 0}
            onClick={() => setEditor({ mode: "create" })}
          >
            新建业务工具集
          </Button>
        </Tooltip>
      </Flex>
      {query.isPending ? <Skeleton active paragraph={{ rows: 4 }} /> : null}
      {query.isError ? (
        <Alert
          type="error"
          showIcon
          title="业务工具集加载失败"
          description={getErrorMessage(query.error)}
          action={<Button onClick={() => void query.refetch()}>重试加载</Button>}
        />
      ) : null}
      {catalog && !query.isError ? (
        catalog.collections.length ? (
          <Row gutter={[12, 12]}>
            {catalog.collections.map((collection) => {
              const state = collectionState(catalog, collection);
              return (
                <Col xs={24} xl={12} key={collection.id}>
                  <Card
                    title={collection.name}
                    extra={<Tag color={state.color}>{state.label}</Tag>}
                  >
                    <Space orientation="vertical" className="tools-full-width">
                      {collection.description ? (
                        <Text type="secondary">{collection.description}</Text>
                      ) : null}
                      <Text>
                        {collection.source_ids.length} 个 MCP 来源 · {state.active}/
                        {state.total} 项能力可用
                      </Text>
                      <Flex justify="flex-end" gap={8} wrap>
                        <Button
                          aria-label={`编辑业务工具集 ${collection.name}`}
                          icon={<Pencil size={15} />}
                          disabled={readOnly}
                          onClick={() => setEditor({ mode: "edit", collection })}
                        >
                          编辑
                        </Button>
                        <ResourceDeleteButton
                          resourceKind="业务工具集"
                          resourceName={collection.name}
                          impact="集合选择记录会移除，已经落库的精确能力授权保持不变。"
                          disabled={readOnly}
                          onConfirm={() => remove.mutateAsync(collection.id)}
                        />
                      </Flex>
                    </Space>
                  </Card>
                </Col>
              );
            })}
          </Row>
        ) : (
          <Card><Empty description="还没有业务工具集" /></Card>
        )
      ) : null}

      <Modal
        open={Boolean(editor)}
        title={editor?.mode === "edit" ? "编辑业务工具集" : "新建业务工具集"}
        okText={editor?.mode === "edit" ? "保存修改" : "确认创建"}
        cancelText="取消"
        confirmLoading={save.isPending}
        onCancel={() => setEditor(undefined)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={(values) => save.mutate(values)}>
          <Form.Item
            label="名称"
            name="name"
            rules={[{ required: true, whitespace: true, max: 128 }]}
          >
            <Input autoFocus placeholder="例如：订单履约工具集" />
          </Form.Item>
          <Form.Item label="说明" name="description" rules={[{ max: 1_000 }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item
            label="MCP 来源"
            name="source_ids"
            rules={[{ required: true, type: "array", min: 1 }]}
            extra="只能选择已经维护的平台托管或外部 MCP 来源。"
          >
            <Select mode="multiple" options={selectableSources} />
          </Form.Item>
          {save.isError ? (
            <Alert type="error" showIcon title={getErrorMessage(save.error)} />
          ) : null}
        </Form>
      </Modal>
    </section>
  );
}
