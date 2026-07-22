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
  Select,
  Skeleton,
  Space,
  Switch,
  Tag,
  Typography,
} from "antd";
import {
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getErrorMessage } from "../../api/errors";
import {
  addManagedMcpCapability,
  createManagedMcpSource,
  deleteManagedMcpCapability,
  deleteManagedMcpSource,
  discoverManagedMcpSource,
  fetchManagedMcpSources,
  fetchMcpCredential,
  testManagedMcpCapability,
  updateManagedMcpCapability,
  updateManagedMcpSource,
  updateMcpCredential,
  type ManagedMcpCapability,
  type ManagedMcpCapabilityInput,
  type ManagedMcpParameterBinding,
  type ManagedMcpSource,
  type ManagedMcpSourceInput,
} from "../../api/tools";
import { ResourceDeleteButton } from "../../components/ResourceDeleteButton";

const { Paragraph, Text, Title } = Typography;
const queryKey = ["managed-mcp-sources"] as const;

type SourceEditor = { mode: "create" } | { mode: "edit"; source: ManagedMcpSource };
type CapabilityEditor = {
  source: ManagedMcpSource;
  capability?: ManagedMcpCapability;
};
type CapabilityParameterForm = ManagedMcpParameterBinding & {
  type: "string" | "number" | "integer" | "boolean";
  description: string;
  required: boolean;
};
type CapabilityForm = Omit<
  ManagedMcpCapabilityInput,
  "input_schema" | "parameter_bindings"
> & { parameters: CapabilityParameterForm[] };
type CredentialForm = {
  kind: "none" | "bearer" | "custom_headers";
  bearer_token?: string;
  headers?: Array<{ name: string; value: string }>;
};
type TestCallEditor = { source: ManagedMcpSource; capability: ManagedMcpCapability };

function sourceValues(source?: ManagedMcpSource): ManagedMcpSourceInput {
  return source
    ? {
        name: source.name,
        description: source.description,
        base_url: source.base_url,
        enabled: source.enabled,
      }
    : { name: "", description: "", base_url: "", enabled: true };
}

function capabilityValues(capability?: ManagedMcpCapability): CapabilityForm {
  if (!capability) {
    return {
      remote_name: "",
      display_name: "",
      description: "",
      method: "GET",
      path_template: "/",
      timeout_seconds: 30,
      response_json_pointer: null,
      enabled: true,
      parameters: [],
    };
  }
  const properties = capability.input_schema.properties;
  const propertyMap =
    properties && typeof properties === "object" && !Array.isArray(properties)
      ? (properties as Record<string, Record<string, unknown>>)
      : {};
  const required = new Set(
    Array.isArray(capability.input_schema.required)
      ? capability.input_schema.required.filter(
          (value): value is string => typeof value === "string",
        )
      : [],
  );
  return {
    remote_name: capability.remote_name,
    display_name: capability.display_name,
    description: capability.description,
    method: capability.method,
    path_template: capability.path_template,
    timeout_seconds: capability.timeout_seconds,
    response_json_pointer: capability.response_json_pointer,
    enabled: capability.enabled,
    parameters: capability.parameter_bindings.map((binding) => {
      const schema = propertyMap[binding.argument_name] ?? {};
      const rawType = schema.type;
      const type = ["string", "number", "integer", "boolean"].includes(String(rawType))
        ? (rawType as CapabilityParameterForm["type"])
        : "string";
      return {
        ...binding,
        type,
        description: typeof schema.description === "string" ? schema.description : "",
        required: required.has(binding.argument_name),
      };
    }),
  };
}

function capabilityInput(values: CapabilityForm): ManagedMcpCapabilityInput {
  const required = values.parameters
    .filter((parameter) => parameter.required)
    .map((parameter) => parameter.argument_name);
  return {
    remote_name: values.remote_name,
    display_name: values.display_name,
    description: values.description,
    method: values.method,
    path_template: values.path_template,
    timeout_seconds: Number(values.timeout_seconds),
    response_json_pointer: values.response_json_pointer || null,
    enabled: values.enabled,
    input_schema: {
      type: "object",
      properties: Object.fromEntries(
        values.parameters.map((parameter) => [
          parameter.argument_name,
          { type: parameter.type, description: parameter.description },
        ]),
      ),
      required,
      additionalProperties: false,
    },
    parameter_bindings: values.parameters.map(
      ({ argument_name, location, target_name }) => ({
        argument_name,
        location,
        target_name,
      }),
    ),
  };
}

function compactJson(value: Record<string, unknown>): string {
  return JSON.stringify(value);
}

export function ToolsPage({ readOnly = false }: { readOnly?: boolean }) {
  const queryClient = useQueryClient();
  const [sourceEditor, setSourceEditor] = useState<SourceEditor>();
  const [capabilityEditor, setCapabilityEditor] = useState<CapabilityEditor>();
  const [credentialSource, setCredentialSource] = useState<ManagedMcpSource>();
  const [testEditor, setTestEditor] = useState<TestCallEditor>();
  const [notice, setNotice] = useState<{ type: "success" | "error"; text: string }>();
  const [testResult, setTestResult] = useState<Record<string, unknown>>();
  const [sourceForm] = Form.useForm<ManagedMcpSourceInput>();
  const [capabilityForm] = Form.useForm<CapabilityForm>();
  const [credentialForm] = Form.useForm<CredentialForm>();
  const [testForm] = Form.useForm<{ arguments_json: string }>();

  const sourcesQuery = useQuery({ queryKey, queryFn: fetchManagedMcpSources });
  const sources = useMemo(() => sourcesQuery.data ?? [], [sourcesQuery.data]);
  const credentialQuery = useQuery({
    queryKey: ["mcp-credential", credentialSource?.id],
    queryFn: () => fetchMcpCredential(credentialSource!.id),
    enabled: Boolean(credentialSource),
  });

  useEffect(() => {
    if (!sourceEditor) return;
    sourceForm.setFieldsValue(
      sourceValues(sourceEditor.mode === "edit" ? sourceEditor.source : undefined),
    );
  }, [sourceEditor, sourceForm]);
  useEffect(() => {
    if (!capabilityEditor) return;
    capabilityForm.setFieldsValue(capabilityValues(capabilityEditor.capability));
  }, [capabilityEditor, capabilityForm]);
  useEffect(() => {
    if (!credentialSource || !credentialQuery.data) return;
    credentialForm.setFieldsValue({
      kind: credentialQuery.data.credential?.kind ?? "none",
      bearer_token: "",
      headers: [{ name: "", value: "" }],
    });
  }, [credentialForm, credentialQuery.data, credentialSource]);
  useEffect(() => {
    if (!testEditor) return;
    testForm.setFieldsValue({ arguments_json: "{}" });
  }, [testEditor, testForm]);

  const openTestEditor = (editor: TestCallEditor) => {
    setTestResult(undefined);
    setTestEditor(editor);
  };

  const resetSources = () => queryClient.invalidateQueries({ queryKey });
  const saveSource = useMutation({
    mutationFn: (values: ManagedMcpSourceInput) =>
      sourceEditor?.mode === "edit"
        ? updateManagedMcpSource(sourceEditor.source.id, values)
        : createManagedMcpSource(values),
    onSuccess: async () => {
      setSourceEditor(undefined);
      sourceForm.resetFields();
      await resetSources();
    },
  });
  const deleteSource = useMutation({
    mutationFn: deleteManagedMcpSource,
    onSuccess: resetSources,
  });
  const saveCapability = useMutation({
    mutationFn: (values: CapabilityForm) => {
      if (!capabilityEditor) throw new Error("能力编辑器未打开");
      const input = capabilityInput(values);
      return capabilityEditor.capability
        ? updateManagedMcpCapability(
            capabilityEditor.source.id,
            capabilityEditor.capability.id,
            input,
          )
        : addManagedMcpCapability(capabilityEditor.source.id, input);
    },
    onSuccess: async () => {
      setCapabilityEditor(undefined);
      capabilityForm.resetFields();
      await resetSources();
    },
  });
  const deleteCapability = useMutation({
    mutationFn: ({ sourceId, capabilityId }: { sourceId: string; capabilityId: string }) =>
      deleteManagedMcpCapability(sourceId, capabilityId),
    onSuccess: resetSources,
  });
  const discovery = useMutation({
    mutationFn: (sourceId: string) => discoverManagedMcpSource(sourceId),
    onSuccess: (result) =>
      setNotice({ type: "success", text: `已通过 MCP 发现 ${result.tools.length} 项启用能力` }),
    onError: (error) => setNotice({ type: "error", text: getErrorMessage(error) }),
  });
  const saveCredential = useMutation({
    mutationFn: async (values: CredentialForm) => {
      if (!credentialSource) throw new Error("凭据编辑器未打开");
      if (values.kind === "none") {
        return updateMcpCredential(credentialSource.id, {
          action: "clear",
          kind: null,
          bearer_token: null,
          headers: null,
        });
      }
      if (values.kind === "bearer") {
        return updateMcpCredential(credentialSource.id, {
          action: "replace",
          kind: "bearer",
          bearer_token: values.bearer_token ?? "",
          headers: null,
        });
      }
      return updateMcpCredential(credentialSource.id, {
        action: "replace",
        kind: "custom_headers",
        bearer_token: null,
        headers: Object.fromEntries(
          (values.headers ?? []).map((header) => [header.name, header.value]),
        ),
      });
    },
    onSuccess: async () => {
      const sourceId = credentialSource?.id;
      credentialForm.resetFields();
      setCredentialSource(undefined);
      if (sourceId) {
        await queryClient.invalidateQueries({ queryKey: ["mcp-credential", sourceId] });
      }
    },
  });
  const testCall = useMutation({
    mutationFn: async ({ arguments_json }: { arguments_json: string }) => {
      if (!testEditor) throw new Error("测试调用编辑器未打开");
      const parsed = JSON.parse(arguments_json) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("调用参数必须是 JSON 对象");
      }
      return testManagedMcpCapability(
        testEditor.source.id,
        testEditor.capability.id,
        parsed as Record<string, unknown>,
      );
    },
    onSuccess: (result) => setTestResult(result.output),
  });

  const credentialKind = Form.useWatch("kind", credentialForm);
  const cards = useMemo(
    () =>
      sources.map((source) => ({
        key: source.id,
        label: (
          <Flex align="center" gap={8} wrap>
            <Text strong>{source.name}</Text>
            <Tag color={source.enabled ? "success" : "default"}>
              {source.enabled ? "启用" : "停用"}
            </Tag>
            <Tag>{source.capabilities.length} 项能力</Tag>
          </Flex>
        ),
        children: (
          <SourcePanel
            source={source}
            readOnly={readOnly}
            discoveryBusy={discovery.isPending && discovery.variables === source.id}
            onDiscover={() => discovery.mutate(source.id)}
            onEdit={() => setSourceEditor({ mode: "edit", source })}
            onCredential={() => setCredentialSource(source)}
            onAddCapability={() => setCapabilityEditor({ source })}
            onEditCapability={(capability) => setCapabilityEditor({ source, capability })}
            onTestCapability={(capability) => openTestEditor({ source, capability })}
            onDeleteCapability={(capability) =>
              deleteCapability.mutateAsync({
                sourceId: source.id,
                capabilityId: capability.id,
              })
            }
            onDeleteSource={() => deleteSource.mutateAsync(source.id)}
          />
        ),
      })),
    [deleteCapability, deleteSource, discovery, readOnly, sources],
  );

  if (sourcesQuery.isPending) {
    return <Skeleton active paragraph={{ rows: 10 }} />;
  }
  if (sourcesQuery.isError) {
    return (
      <Alert
        type="error"
        showIcon
        title="托管 MCP 加载失败"
        description={getErrorMessage(sourcesQuery.error)}
        action={<Button onClick={() => void sourcesQuery.refetch()}>重试加载</Button>}
      />
    );
  }

  return (
    <section className="tools-page">
      <Flex justify="space-between" align="flex-start" gap={24} className="tools-heading">
        <div>
          <Space align="center">
            <Title level={2}>工具与 MCP</Title>
          </Space>
          <Paragraph type="secondary">
            把业务 HTTP 接口维护为统一 MCP 能力；凭据只在服务端加密保存。
          </Paragraph>
        </div>
        <Button
          type="primary"
          icon={<Plus aria-hidden="true" size={16} />}
          disabled={readOnly}
          onClick={() => setSourceEditor({ mode: "create" })}
        >
          新建托管 MCP
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
      {sources.length ? (
        <Collapse items={cards} defaultActiveKey={sources.map((source) => source.id)} />
      ) : (
        <Card><Empty description="还没有托管 MCP 来源" /></Card>
      )}

      <Modal
        open={Boolean(sourceEditor)}
        title={sourceEditor?.mode === "edit" ? "编辑托管 MCP" : "新建托管 MCP"}
        okText={sourceEditor?.mode === "edit" ? "保存修改" : "确认创建"}
        cancelText="取消"
        confirmLoading={saveSource.isPending}
        onCancel={() => setSourceEditor(undefined)}
        onOk={() => sourceForm.submit()}
        destroyOnHidden
      >
        <Form form={sourceForm} layout="vertical" onFinish={(values) => saveSource.mutate(values)}>
          <Form.Item label="名称" name="name" rules={[{ required: true, whitespace: true, max: 128 }]}>
            <Input autoFocus placeholder="例如：订单系统" />
          </Form.Item>
          <Form.Item label="说明" name="description" rules={[{ max: 1_000 }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item
            label="Base URL"
            name="base_url"
            rules={[{ required: true, type: "url", max: 2_048 }]}
            extra="只配置固定 HTTP(S) 来源；每项能力再填写相对 Path。"
          >
            <Input placeholder="https://business.example/api" />
          </Form.Item>
          <Form.Item label="启用状态" name="enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          {saveSource.isError ? <Alert type="error" showIcon title={getErrorMessage(saveSource.error)} /> : null}
        </Form>
      </Modal>

      <CapabilityModal
        editor={capabilityEditor}
        form={capabilityForm}
        busy={saveCapability.isPending}
        error={saveCapability.error}
        onCancel={() => setCapabilityEditor(undefined)}
        onSubmit={(values) => saveCapability.mutate(values)}
      />

      <Modal
        open={Boolean(credentialSource)}
        title="配置 MCP 鉴权"
        okText="保存鉴权"
        cancelText="取消"
        confirmLoading={saveCredential.isPending}
        onCancel={() => setCredentialSource(undefined)}
        onOk={() => credentialForm.submit()}
        destroyOnHidden
      >
        {credentialQuery.isPending ? <Skeleton active paragraph={{ rows: 3 }} /> : (
          <Form form={credentialForm} layout="vertical" onFinish={(values) => saveCredential.mutate(values)}>
            {credentialQuery.data?.configured ? (
              <Alert
                type="info"
                showIcon
                title={
                  credentialQuery.data.credential?.kind === "bearer"
                    ? "已配置 Bearer Token；平台不会回显原值。"
                    : "已配置自定义 Header；平台只回显 Header 名称。"
                }
                className="tools-modal-alert"
              />
            ) : null}
            <Form.Item label="鉴权方式" name="kind" rules={[{ required: true }]}>
              <Select options={[
                { value: "none", label: "不使用鉴权" },
                { value: "bearer", label: "Bearer Token" },
                { value: "custom_headers", label: "自定义 Header" },
              ]} />
            </Form.Item>
            {credentialKind === "bearer" ? (
              <Form.Item label="Bearer Token" name="bearer_token" rules={[{ required: true }]}>
                <Input.Password autoComplete="new-password" />
              </Form.Item>
            ) : null}
            {credentialKind === "custom_headers" ? (
              <Form.List name="headers">
                {(fields, { add, remove }) => (
                  <Space orientation="vertical" className="tools-full-width">
                    {fields.map((field) => (
                      <Space key={field.key} align="start">
                        <Form.Item name={[field.name, "name"]} rules={[{ required: true }]}>
                          <Input aria-label="Header 名称" placeholder="X-API-Key" />
                        </Form.Item>
                        <Form.Item name={[field.name, "value"]} rules={[{ required: true }]}>
                          <Input.Password aria-label="Header 值" autoComplete="new-password" />
                        </Form.Item>
                        <Button icon={<Trash2 size={15} />} aria-label="删除 Header" onClick={() => remove(field.name)} />
                      </Space>
                    ))}
                    <Button icon={<Plus size={15} />} onClick={() => add({ name: "", value: "" })}>添加 Header</Button>
                  </Space>
                )}
              </Form.List>
            ) : null}
            {saveCredential.isError ? <Alert type="error" showIcon title={getErrorMessage(saveCredential.error)} /> : null}
          </Form>
        )}
      </Modal>

      <Modal
        open={Boolean(testEditor)}
        title={`测试调用 · ${testEditor?.capability.display_name ?? ""}`}
        okText="确认调用"
        cancelText="关闭"
        confirmLoading={testCall.isPending}
        onCancel={() => setTestEditor(undefined)}
        onOk={() => testForm.submit()}
        destroyOnHidden
      >
        <Alert type="warning" showIcon title="测试调用可能触发真实业务副作用，请确认参数和目标环境。" className="tools-modal-alert" />
        <Form form={testForm} layout="vertical" onFinish={(values) => testCall.mutate(values)}>
          <Form.Item
            label="调用参数 JSON"
            name="arguments_json"
            rules={[{ required: true }, { validator: async (_, value) => {
              const parsed = JSON.parse(value as string) as unknown;
              if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("必须是 JSON 对象");
            } }]}
          >
            <Input.TextArea rows={7} className="tools-json-editor" />
          </Form.Item>
          {testCall.isError ? <Alert type="error" showIcon title={getErrorMessage(testCall.error)} /> : null}
          {testResult ? <pre className="tools-test-result">{compactJson(testResult)}</pre> : null}
        </Form>
      </Modal>
    </section>
  );
}

function SourcePanel({
  source,
  readOnly,
  discoveryBusy,
  onDiscover,
  onEdit,
  onCredential,
  onAddCapability,
  onEditCapability,
  onTestCapability,
  onDeleteCapability,
  onDeleteSource,
}: {
  source: ManagedMcpSource;
  readOnly: boolean;
  discoveryBusy: boolean;
  onDiscover: () => void;
  onEdit: () => void;
  onCredential: () => void;
  onAddCapability: () => void;
  onEditCapability: (capability: ManagedMcpCapability) => void;
  onTestCapability: (capability: ManagedMcpCapability) => void;
  onDeleteCapability: (capability: ManagedMcpCapability) => Promise<void>;
  onDeleteSource: () => Promise<void>;
}) {
  return (
    <Space orientation="vertical" size={16} className="tools-full-width">
      <Flex justify="space-between" align="flex-start" gap={16} wrap>
        <div>
          <Text code>{source.base_url}</Text>
          {source.description ? <Paragraph type="secondary">{source.description}</Paragraph> : null}
        </div>
        <Space wrap>
          <Button aria-label={`发现能力 ${source.name}`} icon={<RefreshCw size={15} />} loading={discoveryBusy} disabled={readOnly} onClick={onDiscover}>发现能力</Button>
          <Button aria-label={`配置鉴权 ${source.name}`} icon={<Pencil size={15} />} disabled={readOnly} onClick={onCredential}>配置鉴权</Button>
          <Button aria-label={`编辑来源 ${source.name}`} icon={<Pencil size={15} />} disabled={readOnly} onClick={onEdit}>编辑</Button>
          <Button type="primary" aria-label={`新增能力 ${source.name}`} icon={<Plus size={15} />} disabled={readOnly} onClick={onAddCapability}>新增能力</Button>
          <ResourceDeleteButton resourceKind="托管 MCP" resourceName={source.name} impact="来源和未被授权引用的全部能力会被永久删除。" disabled={readOnly} onConfirm={onDeleteSource} />
        </Space>
      </Flex>
      {source.capabilities.length ? (
        <Row gutter={[12, 12]}>
          {source.capabilities.map((capability) => (
            <Col xs={24} xl={12} key={capability.id}>
              <Card size="small" title={capability.display_name} extra={<Tag color={capability.enabled ? "blue" : "default"}>{capability.enabled ? "启用" : "停用"}</Tag>}>
                <Space orientation="vertical" className="tools-full-width">
                  <Text>{capability.method} {capability.path_template}</Text>
                  <Text type="secondary">MCP 名称：<Text code>{capability.remote_name}</Text></Text>
                  <Text type="secondary">{capability.description}</Text>
                  <Flex justify="flex-end" gap={8} wrap>
                    <Button aria-label={`测试调用 ${capability.display_name}`} icon={<RefreshCw size={15} />} disabled={readOnly || !capability.enabled || !source.enabled} onClick={() => onTestCapability(capability)}>测试调用</Button>
                    <Button aria-label={`编辑能力 ${capability.display_name}`} icon={<Pencil size={15} />} disabled={readOnly} onClick={() => onEditCapability(capability)}>编辑</Button>
                    <ResourceDeleteButton resourceKind="工具能力" resourceName={capability.display_name} impact="已授权给员工或会话时平台会拒绝删除。" disabled={readOnly} onConfirm={() => onDeleteCapability(capability)} />
                  </Flex>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有能力" />}
    </Space>
  );
}

function CapabilityModal({
  editor,
  form,
  busy,
  error,
  onCancel,
  onSubmit,
}: {
  editor?: CapabilityEditor;
  form: ReturnType<typeof Form.useForm<CapabilityForm>>[0];
  busy: boolean;
  error: Error | null;
  onCancel: () => void;
  onSubmit: (values: CapabilityForm) => void;
}) {
  return (
    <Modal open={Boolean(editor)} width={900} title={editor?.capability ? "编辑 HTTP 能力" : "新增 HTTP 能力"} okText={editor?.capability ? "保存修改" : "确认创建"} cancelText="取消" confirmLoading={busy} onCancel={onCancel} onOk={() => form.submit()} destroyOnHidden>
      <Form form={form} layout="vertical" onFinish={onSubmit}>
        <Row gutter={12}>
          <Col span={8}><Form.Item label="MCP 工具名称" name="remote_name" rules={[{ required: true, pattern: /^[A-Za-z0-9][A-Za-z0-9_.-]*$/ }]}><Input placeholder="orders.get" /></Form.Item></Col>
          <Col span={8}><Form.Item label="显示名称" name="display_name" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item></Col>
          <Col span={8}><Form.Item label="HTTP 方法" name="method" rules={[{ required: true }]}><Select options={["GET", "POST", "PUT", "PATCH", "DELETE"].map((value) => ({ value, label: value }))} /></Form.Item></Col>
        </Row>
        <Form.Item label="能力说明" name="description" rules={[{ required: true, whitespace: true, max: 1_000 }]}><Input.TextArea rows={2} /></Form.Item>
        <Row gutter={12}>
          <Col span={12}><Form.Item label="接口 Path" name="path_template" rules={[{ required: true, pattern: /^\/(?!\/)/ }]} extra="路径参数使用 {name} 占位。"><Input placeholder="/orders/{order_id}" /></Form.Item></Col>
          <Col span={6}><Form.Item label="超时（秒）" name="timeout_seconds" rules={[{ required: true }]}><Input type="number" min={1} max={300} /></Form.Item></Col>
          <Col span={6}><Form.Item label="启用状态" name="enabled" valuePropName="checked"><Switch /></Form.Item></Col>
        </Row>
        <Form.Item label="响应 JSON Pointer" name="response_json_pointer" extra="可选，例如 /data/order；留空返回完整 JSON。"><Input placeholder="/data/order" /></Form.Item>
        <Text strong>参数定义与 HTTP 映射</Text>
        <Form.List name="parameters">
          {(fields, { add, remove }) => (
            <Space orientation="vertical" className="tools-full-width tools-parameter-list">
              {fields.map((field) => (
                <Card key={field.key} size="small">
                  <Row gutter={8} align="middle">
                    <Col span={5}><Form.Item label="参数名" name={[field.name, "argument_name"]} rules={[{ required: true, pattern: /^[A-Za-z_][A-Za-z0-9_]*$/ }]}><Input /></Form.Item></Col>
                    <Col span={4}><Form.Item label="类型" name={[field.name, "type"]} rules={[{ required: true }]}><Select options={["string", "number", "integer", "boolean"].map((value) => ({ value, label: value }))} /></Form.Item></Col>
                    <Col span={5}><Form.Item label="参数含义" name={[field.name, "description"]} rules={[{ required: true, whitespace: true }]}><Input /></Form.Item></Col>
                    <Col span={4}><Form.Item label="位置" name={[field.name, "location"]} rules={[{ required: true }]}><Select options={["path", "query", "header", "cookie", "body"].map((value) => ({ value, label: value }))} /></Form.Item></Col>
                    <Col span={4}><Form.Item label="目标名称" name={[field.name, "target_name"]} rules={[{ required: true }]}><Input /></Form.Item></Col>
                    <Col span={2}><Form.Item label="必填" name={[field.name, "required"]} valuePropName="checked"><Switch /></Form.Item><Button aria-label="删除参数" type="text" danger icon={<Trash2 size={15} />} onClick={() => remove(field.name)} /></Col>
                  </Row>
                </Card>
              ))}
              <Button icon={<Plus size={15} />} onClick={() => add({ argument_name: "", type: "string", description: "", location: "query", target_name: "", required: false })}>添加参数</Button>
            </Space>
          )}
        </Form.List>
        {error ? <Alert type="error" showIcon title={getErrorMessage(error)} /> : null}
      </Form>
    </Modal>
  );
}

export default ToolsPage;
