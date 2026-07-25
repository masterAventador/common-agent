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
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";
import { Bot, MessageSquare, Pencil, Plus, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  createEmployee,
  deleteEmployee,
  fetchEmployees,
  updateEmployee,
  type Employee,
  type EmployeeConfigurationInput,
} from "../../api/employees";
import { getErrorMessage } from "../../api/errors";
import { fetchKnowledgeBases } from "../../api/knowledge";
import {
  fetchModelConfigurations,
  type ModelConfiguration,
} from "../../api/modelConfigurations";
import { flattenCursorPages, nextPageCursor } from "../../api/pagination";
import { fetchWorkflows } from "../../api/workflows";
import {
  ResourceDeleteButton,
} from "../../components/ResourceDeleteButton";
import { getResourceDeletionErrorMessage } from "../../components/resourceDeletion";
import { resourceTint } from "../../components/resourceTint";
import { toast } from "../../components/toast";
import {
  fetchEmployeeToolGrants,
  fetchToolCatalog,
  replaceEmployeeToolGrants,
  type ToolGrantSelection,
} from "../../api/tools";
import { explicitToolGrantSelection, ToolGrantSelector } from "../tools/index";

const { Text, Title } = Typography;

type EditorState = { mode: "create" } | { mode: "edit"; employee: Employee };

function employeeFormValues(employee: Employee): EmployeeConfigurationInput {
  return {
    name: employee.name,
    description: employee.description,
    system_prompt: employee.system_prompt,
    default_model_configuration_id: employee.default_model_configuration_id,
    knowledge_base_id: employee.knowledge_base_id,
    allowed_workflow_ids: employee.allowed_workflow_ids,
  };
}

export function EmployeesPage({ readOnly = false }: { readOnly?: boolean }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editor, setEditor] = useState<EditorState>();
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [knowledgeSearch, setKnowledgeSearch] = useState("");
  const [workflowSearch, setWorkflowSearch] = useState("");
  const [modelSearch, setModelSearch] = useState("");
  const [toolSelectionOverride, setToolSelectionOverride] =
    useState<ToolGrantSelection>();
  const [form] = Form.useForm<EmployeeConfigurationInput>();

  const employees = useInfiniteQuery({
    queryKey: ["employees", employeeSearch],
    queryFn: ({ pageParam }) =>
      fetchEmployees({ search: employeeSearch, limit: 20, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageCursor,
    placeholderData: keepPreviousData,
  });
  const items = useMemo(() => flattenCursorPages(employees.data), [employees.data]);
  const referenceOptionsEnabled = Boolean(editor) || items.length > 0;
  const knowledgeBases = useInfiniteQuery({
    queryKey: ["knowledge-bases", knowledgeSearch],
    queryFn: ({ pageParam }) =>
      fetchKnowledgeBases({ search: knowledgeSearch, limit: 50, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageCursor,
    placeholderData: keepPreviousData,
    enabled: referenceOptionsEnabled,
  });
  const workflows = useInfiniteQuery({
    queryKey: ["workflows", workflowSearch],
    queryFn: ({ pageParam }) =>
      fetchWorkflows({ search: workflowSearch, limit: 50, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageCursor,
    placeholderData: keepPreviousData,
    enabled: referenceOptionsEnabled,
  });
  const modelConfigurations = useInfiniteQuery({
    queryKey: ["model-configurations", "employee-options", modelSearch],
    queryFn: ({ pageParam }) =>
      fetchModelConfigurations(
        { search: modelSearch, limit: 50, cursor: pageParam },
        false,
      ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageCursor,
    placeholderData: keepPreviousData,
    enabled: referenceOptionsEnabled,
  });
  const editedEmployeeId = editor?.mode === "edit" ? editor.employee.id : undefined;
  const toolCatalog = useQuery({
    queryKey: ["tool-catalog"],
    queryFn: fetchToolCatalog,
    enabled: Boolean(editedEmployeeId),
  });
  const toolGrants = useQuery({
    queryKey: ["employee-tool-grants", editedEmployeeId],
    queryFn: () => fetchEmployeeToolGrants(editedEmployeeId ?? ""),
    enabled: Boolean(editedEmployeeId),
  });
  const knowledgeItems = useMemo(
    () => flattenCursorPages(knowledgeBases.data),
    [knowledgeBases.data],
  );
  const workflowItems = useMemo(() => flattenCursorPages(workflows.data), [workflows.data]);
  const modelItems = useMemo(
    () => flattenCursorPages(modelConfigurations.data),
    [modelConfigurations.data],
  );

  const knowledgeBaseNames = useMemo(
    () => new Map(knowledgeItems.map((item) => [item.id, item.name])),
    [knowledgeItems],
  );
  const workflowNames = useMemo(
    () => new Map(workflowItems.map((item) => [item.id, item.name])),
    [workflowItems],
  );
  const modelsById = useMemo(
    () => new Map(modelItems.map((item) => [item.id, item])),
    [modelItems],
  );

  const toolSelection =
    toolSelectionOverride ??
    (toolCatalog.data && toolGrants.data
      ? explicitToolGrantSelection(toolCatalog.data, toolGrants.data)
      : { collection_ids: [], capability_ids: [] });

  const saveMutation = useMutation({
    mutationFn: async (values: EmployeeConfigurationInput) => {
      const normalizedValues = {
        ...values,
        knowledge_base_id: values.knowledge_base_id ?? null,
        allowed_workflow_ids: values.allowed_workflow_ids ?? [],
      };
      if (editor?.mode !== "edit") return createEmployee(normalizedValues);
      if (!toolCatalog.data || !toolGrants.data) {
        throw new Error("工具授权尚未加载完成");
      }
      await replaceEmployeeToolGrants(editor.employee.id, toolSelection);
      return updateEmployee(editor.employee.id, normalizedValues);
    },
    onSuccess: async (saved) => {
      toast.success(editor?.mode === "edit" ? "数字员工已保存" : "数字员工已创建");
      queryClient.setQueryData(["employee", saved.id], saved);
      setEditor(undefined);
      setToolSelectionOverride(undefined);
      form.resetFields();
      await queryClient.resetQueries({ queryKey: ["employees"] });
      await queryClient.invalidateQueries({
        queryKey: ["employee-tool-grants", saved.id],
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (employee: Employee) => {
      await deleteEmployee(employee.id);
      return employee;
    },
    onSuccess: async (deleted) => {
      toast.success(`数字员工“${deleted.name}”已删除`);
      await queryClient.resetQueries({ queryKey: ["employees"] });
    },
    onError: (error) => toast.error(getResourceDeletionErrorMessage(error)),
  });

  const closeEditor = () => {
    setEditor(undefined);
    setToolSelectionOverride(undefined);
    saveMutation.reset();
    form.resetFields();
  };

  const openCreateEditor = () => {
    setToolSelectionOverride(undefined);
    form.setFieldsValue({
      name: "",
      description: "",
      system_prompt: "",
      default_model_configuration_id: undefined,
      knowledge_base_id: null,
      allowed_workflow_ids: [],
    });
    setEditor({ mode: "create" });
  };

  const openEditEditor = (employee: Employee) => {
    setToolSelectionOverride(undefined);
    form.setFieldsValue(employeeFormValues(employee));
    setEditor({ mode: "edit", employee });
  };

  const knowledgeBaseLabel = (employee: Employee) => {
    if (!employee.knowledge_base_id) return <Tag>未绑定知识库</Tag>;
    const name = knowledgeBaseNames.get(employee.knowledge_base_id);
    if (name) return <Tag color="blue">{name}</Tag>;
    if (knowledgeBases.isError) return <Tag color="warning">已绑定知识库</Tag>;
    if (knowledgeBases.isPending) return <Tag>正在读取知识库</Tag>;
    return <Tag color="error">知识库已失效</Tag>;
  };

  const workflowPermissionLabel = (employee: Employee) => {
    const count = employee.allowed_workflow_ids.length;
    if (count === 0) return <Tag>未授权工作流</Tag>;
    const names = employee.allowed_workflow_ids
      .map((workflowId) => workflowNames.get(workflowId))
      .filter((name): name is string => Boolean(name));
    return (
      <Tag color="purple" title={names.join("、") || undefined}>
        已授权 {count} 个工作流
      </Tag>
    );
  };

  // 设计稿的卡片底栏是等宽小字的模型名；只有模型不可用时才升级成警告色标签
  const defaultModelLabel = (employee: Employee) => {
    const configured = modelsById.get(employee.default_model_configuration_id);
    if (configured?.enabled) return <span>{configured.display_name}</span>;
    if (configured) return <Tag color="warning">{configured.display_name}（已停用）</Tag>;
    if (modelConfigurations.isPending) return <span>正在读取默认模型</span>;
    return <Tag color="warning">{employee.default_model_identifier}</Tag>;
  };

  const selectableModels = (employee?: Employee): ModelConfiguration[] =>
    modelItems.filter(
      (item) => item.enabled || item.id === employee?.default_model_configuration_id,
    );

  if (employees.isPending) {
    return (
      <section className="employees-page" aria-label="数字员工加载中">
        <Skeleton active paragraph={{ rows: 8 }} />
      </section>
    );
  }

  if (employees.isError) {
    return (
      <section className="employees-page">
        <Alert
          type="error"
          showIcon
          title="数字员工加载失败"
          description={getErrorMessage(employees.error)}
          action={
            <Button
              aria-label="重试加载"
              icon={<RefreshCw aria-hidden="true" size={16} />}
              onClick={() => void employees.refetch()}
            >
              重试加载
            </Button>
          }
        />
      </section>
    );
  }

  return (
    <section className="employees-page">
      <Flex justify="space-between" align="flex-start" gap={24} className="employees-page-heading">
        <div>
          <Space align="center">
            <Bot aria-hidden="true" className="employees-title-icon" size={22} strokeWidth={1.75} />
            <Title level={2}>数字员工</Title>
          </Space>
          <Typography.Paragraph type="secondary">
            配置角色、系统指令、知识库、工作流和精确工具权限。
          </Typography.Paragraph>
        </div>
        <Button
          type="primary"
          aria-label="创建数字员工"
          icon={<Plus aria-hidden="true" size={16} />}
          disabled={readOnly}
          onClick={openCreateEditor}
        >
          创建数字员工
        </Button>
      </Flex>

      <Input.Search
        aria-label="搜索数字员工"
        allowClear
        className="page-search"
        value={employeeSearch}
        placeholder="搜索名称前缀或完整 ID"
        onChange={(event) => setEmployeeSearch(event.target.value)}
      />

      {knowledgeBases.isError && (
        <Alert
          type="warning"
          showIcon
          title="知识库选项加载失败"
          description={getErrorMessage(knowledgeBases.error)}
          action={<Button onClick={() => void knowledgeBases.refetch()}>重试知识库</Button>}
          className="employees-inline-alert"
        />
      )}

      {workflows.isError && (
        <Alert
          type="warning"
          showIcon
          title="工作流选项加载失败"
          description={getErrorMessage(workflows.error)}
          action={<Button onClick={() => void workflows.refetch()}>重试工作流</Button>}
          className="employees-inline-alert"
        />
      )}

      {modelConfigurations.isError && (
        <Alert
          type="warning"
          showIcon
          title="模型选项加载失败"
          description={getErrorMessage(modelConfigurations.error)}
          action={
            <Button onClick={() => void modelConfigurations.refetch()}>重试模型</Button>
          }
          className="employees-inline-alert"
        />
      )}



      {items.length === 0 ? (
        <Card className="employees-empty-card">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有数字员工">
            <Text type="secondary">创建后即可配置知识库并开始会话。</Text>
          </Empty>
        </Card>
      ) : (
        <div className="employee-card-grid">
          {items.map((employee) => (
            <Card key={employee.id} className="employee-card">
              <div className="resource-card-head">
                <span
                  className="resource-card-icon"
                  style={resourceTint(employee.id)}
                  aria-hidden="true"
                >
                  <Bot size={20} strokeWidth={1.75} />
                </span>
                <Text strong className="resource-card-title">
                  {employee.name}
                </Text>
              </div>
              <Text type="secondary" className="employee-description">
                {employee.description || "暂无说明"}
              </Text>
              {/* 设计稿把绑定信息放在描述下的独立一行，标题行只留图标和名称 */}
              <div className="employee-card-meta">
                {knowledgeBaseLabel(employee)}
                {workflowPermissionLabel(employee)}
              </div>
              <div className="resource-card-footer">{defaultModelLabel(employee)}</div>
              <Flex gap={8} justify="flex-end" wrap>
                <ResourceDeleteButton
                  resourceKind="数字员工"
                  resourceName={employee.name}
                  impact="数字员工配置会被永久删除；存在会话引用时平台会拒绝本次操作。"
                  loading={
                    deleteMutation.isPending && deleteMutation.variables?.id === employee.id
                  }
                  disabled={readOnly || deleteMutation.isPending}
                  onConfirm={() => deleteMutation.mutateAsync(employee)}
                />
                <Button
                  aria-label={`编辑 ${employee.name}`}
                  icon={<Pencil aria-hidden="true" size={15} />}
                  disabled={readOnly}
                  onClick={() => openEditEditor(employee)}
                >
                  编辑
                </Button>
                <Button
                  type="primary"
                  aria-label={`与${employee.name}开始对话`}
                  icon={<MessageSquare aria-hidden="true" size={15} />}
                  onClick={() =>
                    navigate(`/chat?${new URLSearchParams({ employee_id: employee.id })}`)
                  }
                >
                  开始对话
                </Button>
              </Flex>
            </Card>
          ))}
          {employees.hasNextPage && (
            <Button
              loading={employees.isFetchingNextPage}
              onClick={() => void employees.fetchNextPage()}
            >
              加载更多数字员工
            </Button>
          )}
        </div>
      )}

      <Modal
        title={editor?.mode === "edit" ? "编辑数字员工" : "创建数字员工"}
        open={Boolean(editor)}
        styles={{ body: { maxHeight: "calc(100vh - 280px)", overflowY: "auto" } }}
        okText={editor?.mode === "edit" ? "保存修改" : "确认创建"}
        cancelText="取消"
        confirmLoading={saveMutation.isPending}
        okButtonProps={{
          disabled:
            readOnly ||
            (editor?.mode === "edit" &&
              (toolCatalog.isPending ||
                toolGrants.isPending ||
                toolCatalog.isError ||
                toolGrants.isError)),
        }}
        onOk={() => form.submit()}
        onCancel={closeEditor}
      >
        <Form<EmployeeConfigurationInput>
          form={form}
          layout="vertical"
          requiredMark={false}
          onFinish={(values) => saveMutation.mutate(values)}
        >
          {saveMutation.isError && (
            <Alert
              type="error"
              showIcon
              title="保存失败"
              description={getErrorMessage(saveMutation.error)}
              className="employees-inline-alert"
            />
          )}
          <Form.Item
            label="名称"
            name="name"
            rules={[{ required: true, whitespace: true, message: "请输入数字员工名称" }]}
          >
            <Input placeholder="例如：知识助理" autoFocus />
          </Form.Item>
          <Form.Item label="说明" name="description">
            <Input.TextArea placeholder="说明这个数字员工适合处理什么问题" rows={3} />
          </Form.Item>
          <Form.Item
            label="系统指令"
            name="system_prompt"
            rules={[{ required: true, whitespace: true, message: "请输入系统指令" }]}
          >
            <Input.TextArea placeholder="定义回答风格、边界和信息使用原则" rows={6} />
          </Form.Item>
          <Form.Item
            label="默认模型"
            name="default_model_configuration_id"
            rules={[{ required: true, message: "请选择默认模型" }]}
            extra="仅可选择模型管理中已启用的配置；当前已停用绑定可原样保留。"
          >
            <Select
              disabled={modelConfigurations.isError}
              loading={modelConfigurations.isPending}
              placeholder={
                modelConfigurations.isError
                  ? "模型配置暂时不可用"
                  : "选择已启用模型"
              }
              showSearch
              filterOption={false}
              searchValue={modelSearch}
              options={selectableModels(
                editor?.mode === "edit" ? editor.employee : undefined,
              ).map((item) => ({
                value: item.id,
                label: `${item.display_name} · ${item.model_identifier}${item.enabled ? "" : "（已停用，仅保留现有绑定）"}`,
                disabled: !item.enabled,
              }))}
              onSearch={setModelSearch}
              onPopupScroll={(event) => {
                const target = event.currentTarget;
                if (
                  modelConfigurations.hasNextPage &&
                  !modelConfigurations.isFetchingNextPage &&
                  target.scrollTop + target.clientHeight >= target.scrollHeight - 16
                ) {
                  void modelConfigurations.fetchNextPage();
                }
              }}
            />
          </Form.Item>
          <Form.Item label="知识库" name="knowledge_base_id">
            <Select
              allowClear
              disabled={knowledgeBases.isError}
              loading={knowledgeBases.isPending}
              placeholder={knowledgeBases.isError ? "知识库暂时不可用" : "不绑定知识库"}
              showSearch
              filterOption={false}
              searchValue={knowledgeSearch}
              options={knowledgeItems.map((item) => ({ value: item.id, label: item.name }))}
              onSearch={setKnowledgeSearch}
              onPopupScroll={(event) => {
                const target = event.currentTarget;
                if (
                  knowledgeBases.hasNextPage &&
                  !knowledgeBases.isFetchingNextPage &&
                  target.scrollTop + target.clientHeight >= target.scrollHeight - 16
                ) {
                  void knowledgeBases.fetchNextPage();
                }
              }}
            />
          </Form.Item>
          <Form.Item label="允许工作流" name="allowed_workflow_ids">
            <Select
              mode="multiple"
              allowClear
              disabled={workflows.isError}
              loading={workflows.isPending}
              placeholder={workflows.isError ? "工作流暂时不可用" : "不授权工作流"}
              showSearch
              filterOption={false}
              searchValue={workflowSearch}
              options={workflowItems.map((item) => ({ value: item.id, label: item.name }))}
              onSearch={setWorkflowSearch}
              onPopupScroll={(event) => {
                const target = event.currentTarget;
                if (
                  workflows.hasNextPage &&
                  !workflows.isFetchingNextPage &&
                  target.scrollTop + target.clientHeight >= target.scrollHeight - 16
                ) {
                  void workflows.fetchNextPage();
                }
              }}
              maxTagCount="responsive"
            />
          </Form.Item>
          <Text type="secondary">数字员工只会看到并调用这里明确授权的工作流。</Text>
          {editor?.mode === "edit" ? (
            <div className="employees-tool-grants">
              <Typography.Title level={5}>工具权限</Typography.Title>
              {toolCatalog.isPending || toolGrants.isPending ? (
                <Skeleton active paragraph={{ rows: 3 }} />
              ) : toolCatalog.isError || toolGrants.isError ? (
                <Alert
                  type="error"
                  showIcon
                  title="工具授权加载失败"
                  description={getErrorMessage(toolCatalog.error ?? toolGrants.error)}
                />
              ) : toolCatalog.data && toolGrants.data ? (
                <ToolGrantSelector
                  catalog={toolCatalog.data}
                  value={toolSelection}
                  disabled={readOnly}
                  onChange={setToolSelectionOverride}
                />
              ) : null}
            </div>
          ) : (
            <Text type="secondary">新员工默认无工具；创建后可在编辑页精确授权。</Text>
          )}
        </Form>
      </Modal>
    </section>
  );
}
