import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Empty,
  Flex,
  Form,
  Input,
  Modal,
  Row,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";
import { Pencil, Plus, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getErrorMessage } from "../../api/errors";
import { toast } from "../../components/toast";
import {
  createExternalMcpSource,
  deleteExternalMcpSource,
  fetchExternalMcpSources,
  syncExternalMcpSource,
  updateExternalMcpSource,
  type ExternalMcpSource,
  type ExternalMcpSourceInput,
  type ToolCapability,
} from "../../api/tools";
import { ResourceDeleteButton } from "../../components/ResourceDeleteButton";

const { Paragraph, Text, Title } = Typography;
const externalQueryKey = ["external-mcp-sources"] as const;

type ExternalEditor =
  | { mode: "create" }
  | { mode: "edit"; source: ExternalMcpSource };

function editorValues(source?: ExternalMcpSource): ExternalMcpSourceInput {
  return source
    ? {
        name: source.name,
        description: source.description,
        endpoint_url: source.endpoint_url,
      }
    : { name: "", description: "", endpoint_url: "" };
}

const sourceStatus = {
  draft: { color: "default", label: "待同步" },
  ready: { color: "success", label: "可用" },
  unavailable: { color: "error", label: "连接异常" },
  disabled: { color: "default", label: "停用" },
} as const;

const capabilityStatus = {
  active: { color: "blue", label: "可用" },
  unavailable: { color: "warning", label: "待确认" },
  disabled: { color: "default", label: "停用" },
} as const;

export function ExternalMcpSection({
  readOnly,
  onCredential,
  onTestCapability,
}: {
  readOnly: boolean;
  onCredential: (source: Pick<ExternalMcpSource, "id" | "name">) => void;
  onTestCapability: (source: ExternalMcpSource, capability: ToolCapability) => void;
}) {
  const queryClient = useQueryClient();
  const [editor, setEditor] = useState<ExternalEditor>();
  const [notice, setNotice] = useState<{ type: "success" | "error"; text: string }>();
  const [form] = Form.useForm<ExternalMcpSourceInput>();
  const query = useQuery({ queryKey: externalQueryKey, queryFn: fetchExternalMcpSources });
  const sources = useMemo(() => query.data ?? [], [query.data]);

  useEffect(() => {
    if (!editor) return;
    form.setFieldsValue(
      editorValues(editor.mode === "edit" ? editor.source : undefined),
    );
  }, [editor, form]);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: externalQueryKey }),
      queryClient.invalidateQueries({ queryKey: ["tool-catalog"] }),
    ]);
  };
  const save = useMutation({
    mutationFn: (values: ExternalMcpSourceInput) =>
      editor?.mode === "edit"
        ? updateExternalMcpSource(editor.source.id, values)
        : createExternalMcpSource(values),
    onSuccess: async (saved, values) => {
      const endpointChanged =
        editor?.mode === "edit" && editor.source.endpoint_url !== saved.endpoint_url;
      setEditor(undefined);
      form.resetFields();
      setNotice({
        type: "success",
        text:
          endpointChanged
            ? `${values.name} 端点已变更；为防止旧凭据泄漏，原鉴权已清除，请重新配置后再同步。`
            : saved.status === "draft"
            ? `${values.name} 已保存为草稿；平台尚未连接远端，请显式同步能力。`
            : `${values.name} 配置已保存；平台保留当前能力状态，需要时可显式同步。`,
      });
      await refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (sourceId: string) => deleteExternalMcpSource(sourceId),
    onSuccess: refresh,
    onError: (error) => toast.error(`外部 MCP 删除失败：${getErrorMessage(error)}`),
  });
  const synchronize = useMutation({
    mutationFn: (sourceId: string) => syncExternalMcpSource(sourceId),
    onSuccess: async (result) => {
      setNotice({
        type: "success",
        text:
          `同步完成：新增 ${result.added}，变化隔离 ${result.schema_changed}，` +
          `移除 ${result.removed}，重新启用 ${result.reactivated}`,
      });
      await refresh();
    },
    onError: (error) => setNotice({ type: "error", text: getErrorMessage(error) }),
  });

  const cards = sources.map((source) => ({
    key: source.id,
    label: (
      <Flex align="center" gap={8} wrap>
        <Text strong>{source.name}</Text>
        <Tag color={sourceStatus[source.status].color}>
          {sourceStatus[source.status].label}
        </Tag>
        <Tag>{source.capabilities.length} 项能力</Tag>
      </Flex>
    ),
    children: (
      <Space orientation="vertical" size={16} className="tools-full-width">
        <Flex justify="space-between" align="flex-start" gap={16} wrap>
          <div>
            <Text code>{source.endpoint_url}</Text>
            {source.description ? (
              <Paragraph type="secondary">{source.description}</Paragraph>
            ) : null}
          </div>
          <Space wrap>
            <Button
              aria-label={`同步能力 ${source.name}`}
              icon={<RefreshCw size={15} />}
              loading={synchronize.isPending && synchronize.variables === source.id}
              disabled={readOnly}
              onClick={() => synchronize.mutate(source.id)}
            >
              同步能力
            </Button>
            <Button
              aria-label={`配置鉴权 ${source.name}`}
              icon={<Pencil size={15} />}
              disabled={readOnly}
              onClick={() => onCredential(source)}
            >
              配置鉴权
            </Button>
            <Button
              aria-label={`编辑外部来源 ${source.name}`}
              icon={<Pencil size={15} />}
              disabled={readOnly}
              onClick={() => setEditor({ mode: "edit", source })}
            >
              编辑
            </Button>
            <ResourceDeleteButton
              resourceKind="外部 MCP"
              resourceName={source.name}
              impact="已被业务工具集或精确授权引用时平台会拒绝删除。"
              disabled={readOnly}
              onConfirm={() => remove.mutateAsync(source.id)}
            />
          </Space>
        </Flex>
        {source.capabilities.length ? (
          <Row gutter={[12, 12]}>
            {source.capabilities.map((capability) => (
              <Col xs={24} xl={12} key={capability.id}>
                <Card
                  size="small"
                  title={capability.display_name}
                  extra={
                    <Tag color={capabilityStatus[capability.status].color}>
                      {capabilityStatus[capability.status].label}
                    </Tag>
                  }
                >
                  <Space orientation="vertical" className="tools-full-width">
                    <Text code>{capability.remote_name}</Text>
                    <Text type="secondary">{capability.description}</Text>
                    {capability.status === "unavailable" ? (
                      <Alert
                        type="warning"
                        showIcon
                        title="能力定义已变化，需再次同步确认"
                      />
                    ) : null}
                    <Flex justify="flex-end">
                      <Button
                        aria-label={`测试调用 ${capability.display_name}`}
                        icon={<RefreshCw size={15} />}
                        disabled={
                          readOnly ||
                          source.status !== "ready" ||
                          capability.status !== "active"
                        }
                        onClick={() => onTestCapability(source, capability)}
                      >
                        测试调用
                      </Button>
                    </Flex>
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未同步能力" />
        )}
      </Space>
    ),
  }));

  return (
    <section className="tools-section" aria-labelledby="external-mcp-title">
      <Flex justify="space-between" align="flex-start" gap={16} wrap>
        <div>
          <Title level={3} id="external-mcp-title">外部 MCP</Title>
          <Paragraph type="secondary">
            接入第三方 Streamable HTTP 服务；保存配置不会联网，只有显式同步才更新能力目录。
          </Paragraph>
        </div>
        <Button
          icon={<Plus size={16} />}
          disabled={readOnly}
          onClick={() => setEditor({ mode: "create" })}
        >
          新建外部 MCP
        </Button>
      </Flex>
      {notice ? (
        <Alert
          type={notice.type}
          showIcon
          closable
          title={notice.text}
          onClose={() => setNotice(undefined)}
          className="tools-inline-alert"
        />
      ) : null}
      {query.isPending ? <Skeleton active paragraph={{ rows: 4 }} /> : null}
      {query.isError ? (
        <Alert
          type="error"
          showIcon
          title="外部 MCP 加载失败"
          description={getErrorMessage(query.error)}
          action={<Button onClick={() => void query.refetch()}>重试加载</Button>}
        />
      ) : null}
      {!query.isPending && !query.isError ? (
        cards.length ? (
          <Collapse items={cards} defaultActiveKey={sources.map((source) => source.id)} />
        ) : (
          <Card><Empty description="还没有外部 MCP 来源" /></Card>
        )
      ) : null}

      <Modal
        open={Boolean(editor)}
        title={editor?.mode === "edit" ? "编辑外部 MCP" : "新建外部 MCP"}
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
            <Input autoFocus placeholder="例如：合作方订单 MCP" />
          </Form.Item>
          <Form.Item label="说明" name="description" rules={[{ max: 1_000 }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item
            label="MCP Endpoint"
            name="endpoint_url"
            rules={[{ required: true, type: "url", max: 2_048 }]}
            extra="仅支持固定 HTTP(S) Streamable HTTP Endpoint。"
          >
            <Input placeholder="https://partner.example/mcp" />
          </Form.Item>
          {save.isError ? (
            <Alert type="error" showIcon title={getErrorMessage(save.error)} />
          ) : null}
        </Form>
      </Modal>
    </section>
  );
}
