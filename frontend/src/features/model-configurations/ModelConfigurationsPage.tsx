import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
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
  Switch,
  Tag,
  Typography,
} from "antd";
import { Bot, CircleCheck, Pencil, Plus, RefreshCw, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  createModelConfiguration,
  deleteModelConfiguration,
  fetchModelConfigurations,
  updateModelConfiguration,
  verifyModelConfiguration,
  type ModelConfiguration,
  type ModelConfigurationInput,
} from "../../api/modelConfigurations";
import { ApiClientError, getErrorMessage } from "../../api/errors";
import { flattenCursorPages, nextPageCursor } from "../../api/pagination";
import { ResourceDeleteButton } from "../../components/ResourceDeleteButton";

const { Text, Title } = Typography;
type EditorState = { mode: "create" } | { mode: "edit"; item: ModelConfiguration };

function formValues(item: ModelConfiguration): ModelConfigurationInput {
  return {
    display_name: item.display_name,
    model_identifier: item.model_identifier,
    enabled: item.enabled,
  };
}

function deletionMessage(error: unknown): string {
  if (error instanceof ApiClientError && error.code === "model_configuration_in_use") {
    return "该模型仍被数字员工或工作流引用，请先解除引用。";
  }
  return getErrorMessage(error);
}

export function ModelConfigurationsPage({ readOnly = false }: { readOnly?: boolean }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [editor, setEditor] = useState<EditorState>();
  const [verificationNotice, setVerificationNotice] = useState<string>();
  const [form] = Form.useForm<ModelConfigurationInput>();

  const configurations = useInfiniteQuery({
    queryKey: ["model-configurations", search],
    queryFn: ({ pageParam }) =>
      fetchModelConfigurations({ search, limit: 20, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageCursor,
    placeholderData: keepPreviousData,
  });
  const items = useMemo(
    () => flattenCursorPages(configurations.data),
    [configurations.data],
  );

  useEffect(() => {
    if (!editor) return;
    form.setFieldsValue(
      editor.mode === "edit"
        ? formValues(editor.item)
        : {
            display_name: "",
            model_identifier: "",
            enabled: true,
          },
    );
  }, [editor, form]);

  const saveMutation = useMutation({
    mutationFn: (values: ModelConfigurationInput) =>
      editor?.mode === "edit"
        ? updateModelConfiguration(editor.item.id, values)
        : createModelConfiguration(values),
    onSuccess: async () => {
      setEditor(undefined);
      form.resetFields();
      await queryClient.resetQueries({ queryKey: ["model-configurations"] });
    },
  });
  const verifyMutation = useMutation({
    mutationFn: (item: ModelConfiguration) => verifyModelConfiguration(item.id),
    onMutate: () => setVerificationNotice(undefined),
    onSuccess: (result) =>
      setVerificationNotice(`模型调用成功 · ${result.response_preview}`),
  });
  const deleteMutation = useMutation({
    mutationFn: (item: ModelConfiguration) => deleteModelConfiguration(item.id),
    onSuccess: async () => {
      await queryClient.resetQueries({ queryKey: ["model-configurations"] });
    },
  });

  const closeEditor = () => {
    setEditor(undefined);
    saveMutation.reset();
    form.resetFields();
  };

  if (configurations.isPending) {
    return (
      <section className="model-configurations-page" aria-label="模型管理加载中">
        <Skeleton active paragraph={{ rows: 8 }} />
      </section>
    );
  }

  if (configurations.isError) {
    return (
      <section className="model-configurations-page">
        <Alert
          type="error"
          showIcon
          title="模型配置加载失败"
          description={getErrorMessage(configurations.error)}
          action={
            <Button
              icon={<RefreshCw aria-hidden="true" size={16} />}
              onClick={() => void configurations.refetch()}
            >
              重试加载
            </Button>
          }
        />
      </section>
    );
  }

  return (
    <section className="model-configurations-page">
      <Flex
        justify="space-between"
        align="flex-start"
        gap={24}
        className="model-configurations-heading"
      >
        <div>
          <Space align="center">
            <Bot aria-hidden="true" className="model-configurations-title-icon" size={22} />
            <Title level={2}>模型管理</Title>
          </Space>
          <Typography.Paragraph type="secondary">
            管理当前工作区可用的聊天模型；平台凭据由服务端统一保管。
          </Typography.Paragraph>
        </div>
        <Button
          type="primary"
          icon={<Plus aria-hidden="true" size={16} />}
          disabled={readOnly}
          onClick={() => setEditor({ mode: "create" })}
        >
          创建模型
        </Button>
      </Flex>

      <Input.Search
        aria-label="搜索模型"
        allowClear
        value={search}
        placeholder="搜索显示名称、模型标识或完整 ID"
        onChange={(event) => setSearch(event.target.value)}
      />

      {verificationNotice ? (
        <Alert
          type="success"
          showIcon
          closable
          title="模型调用成功"
          description={verificationNotice.split(" · ")[1]}
          className="model-configurations-inline-alert"
          onClose={() => setVerificationNotice(undefined)}
        />
      ) : null}
      {verifyMutation.isError ? (
        <Alert
          type="error"
          showIcon
          closable
          title="模型调用失败"
          description={getErrorMessage(verifyMutation.error)}
          className="model-configurations-inline-alert"
          onClose={() => verifyMutation.reset()}
        />
      ) : null}
      {deleteMutation.isError ? (
        <Alert
          type="error"
          showIcon
          closable
          title="模型删除失败"
          description={deletionMessage(deleteMutation.error)}
          className="model-configurations-inline-alert"
          onClose={() => deleteMutation.reset()}
        />
      ) : null}

      {items.length === 0 ? (
        <Card className="model-configurations-empty-card">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有模型配置">
            <Text type="secondary">创建后才能在 AI 会话、数字员工和工作流中选择。</Text>
          </Empty>
        </Card>
      ) : (
        <div className="model-configuration-grid">
          {items.map((item) => (
            <Card
              key={item.id}
              className="model-configuration-card"
              title={item.display_name}
              extra={<Tag color={item.enabled ? "success" : "default"}>{item.enabled ? "启用" : "停用"}</Tag>}
            >
              <div className="model-configuration-details">
                <Text type="secondary">模型标识</Text>
                <Text code>{item.model_identifier}</Text>
              </div>
              <Flex gap={8} justify="flex-end" wrap>
                <Button
                  icon={<Zap aria-hidden="true" size={15} />}
                  aria-label={`测试调用 ${item.display_name}`}
                  loading={
                    verifyMutation.isPending && verifyMutation.variables?.id === item.id
                  }
                  disabled={readOnly}
                  onClick={() => verifyMutation.mutate(item)}
                >
                  测试调用
                </Button>
                <Button
                  icon={<Pencil aria-hidden="true" size={15} />}
                  aria-label={`编辑 ${item.display_name}`}
                  disabled={readOnly}
                  onClick={() => setEditor({ mode: "edit", item })}
                >
                  编辑
                </Button>
                <ResourceDeleteButton
                  resourceKind="模型"
                  resourceName={item.display_name}
                  impact="模型配置会被永久删除；存在数字员工、工作流或会话引用时平台会拒绝本次操作。"
                  disabled={readOnly || deleteMutation.isPending}
                  loading={deleteMutation.isPending && deleteMutation.variables?.id === item.id}
                  onConfirm={() => deleteMutation.mutateAsync(item)}
                />
              </Flex>
            </Card>
          ))}
        </div>
      )}

      {configurations.hasNextPage ? (
        <Flex justify="center" className="model-configurations-load-more">
          <Button
            loading={configurations.isFetchingNextPage}
            onClick={() => void configurations.fetchNextPage()}
          >
            加载更多
          </Button>
        </Flex>
      ) : null}

      <Modal
        open={Boolean(editor)}
        title={editor?.mode === "edit" ? "编辑模型" : "创建模型"}
        okText={editor?.mode === "edit" ? "保存修改" : "确认创建"}
        cancelText="取消"
        confirmLoading={saveMutation.isPending}
        onCancel={closeEditor}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form<ModelConfigurationInput>
          form={form}
          layout="vertical"
          onFinish={(values) => saveMutation.mutate(values)}
        >
          <Form.Item
            label="显示名称"
            name="display_name"
            rules={[{ required: true, whitespace: true, max: 128 }]}
          >
            <Input autoFocus placeholder="例如：Qwen Plus" />
          </Form.Item>
          <Form.Item
            label="模型标识"
            name="model_identifier"
            rules={[
              { required: true, whitespace: true, max: 128 },
              {
                pattern: /^[A-Za-z0-9][A-Za-z0-9._-]*$/,
                message: "只能包含字母、数字、点、下划线和连字符",
              },
            ]}
            extra="填写平台支持的模型标识，不需要填写 API Key。常用：qwen-plus、qwen-max、qwen-turbo、qwen-long、deepseek-v3、deepseek-r1。"
          >
            <Input placeholder="例如：qwen-plus" />
          </Form.Item>
          <Form.Item label="启用状态" name="enabled" valuePropName="checked">
            <Switch
              aria-label="启用状态"
              checkedChildren={<CircleCheck aria-hidden="true" size={14} />}
            />
          </Form.Item>
          {saveMutation.isError ? (
            <Alert
              type="error"
              showIcon
              title="模型保存失败"
              description={getErrorMessage(saveMutation.error)}
            />
          ) : null}
        </Form>
      </Modal>
    </section>
  );
}
