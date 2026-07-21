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
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";
import { Bot, MessageSquare, Pencil, Plus, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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
import { flattenCursorPages, nextPageCursor } from "../../api/pagination";
import { fetchWorkflows } from "../../api/workflows";
import {
  ResourceDeleteButton,
} from "../../components/ResourceDeleteButton";
import { getResourceDeletionErrorMessage } from "../../components/resourceDeletion";

const { Text, Title } = Typography;

type EditorState = { mode: "create" } | { mode: "edit"; employee: Employee };

function employeeFormValues(employee: Employee): EmployeeConfigurationInput {
  return {
    name: employee.name,
    description: employee.description,
    system_prompt: employee.system_prompt,
    knowledge_base_id: employee.knowledge_base_id,
    allowed_workflow_ids: employee.allowed_workflow_ids,
  };
}

export function EmployeesPage({ readOnly = false }: { readOnly?: boolean }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editor, setEditor] = useState<EditorState>();
  const [deleteNotice, setDeleteNotice] = useState<string>();
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [knowledgeSearch, setKnowledgeSearch] = useState("");
  const [workflowSearch, setWorkflowSearch] = useState("");
  const [form] = Form.useForm<EmployeeConfigurationInput>();

  const employees = useInfiniteQuery({
    queryKey: ["employees", employeeSearch],
    queryFn: ({ pageParam }) =>
      fetchEmployees({ search: employeeSearch, limit: 20, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageCursor,
    placeholderData: keepPreviousData,
  });
  const knowledgeBases = useInfiniteQuery({
    queryKey: ["knowledge-bases", knowledgeSearch],
    queryFn: ({ pageParam }) =>
      fetchKnowledgeBases({ search: knowledgeSearch, limit: 50, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageCursor,
    placeholderData: keepPreviousData,
  });
  const workflows = useInfiniteQuery({
    queryKey: ["workflows", workflowSearch],
    queryFn: ({ pageParam }) =>
      fetchWorkflows({ search: workflowSearch, limit: 50, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageCursor,
    placeholderData: keepPreviousData,
  });
  const items = useMemo(() => flattenCursorPages(employees.data), [employees.data]);
  const knowledgeItems = useMemo(
    () => flattenCursorPages(knowledgeBases.data),
    [knowledgeBases.data],
  );
  const workflowItems = useMemo(() => flattenCursorPages(workflows.data), [workflows.data]);

  const knowledgeBaseNames = useMemo(
    () => new Map(knowledgeItems.map((item) => [item.id, item.name])),
    [knowledgeItems],
  );
  const workflowNames = useMemo(
    () => new Map(workflowItems.map((item) => [item.id, item.name])),
    [workflowItems],
  );

  useEffect(() => {
    if (!editor) return;
    form.setFieldsValue(
      editor.mode === "edit"
        ? employeeFormValues(editor.employee)
        : {
            name: "",
            description: "",
            system_prompt: "",
            knowledge_base_id: null,
            allowed_workflow_ids: [],
          },
    );
  }, [editor, form]);

  const saveMutation = useMutation({
    mutationFn: (values: EmployeeConfigurationInput) => {
      const normalizedValues = {
        ...values,
        knowledge_base_id: values.knowledge_base_id ?? null,
        allowed_workflow_ids: values.allowed_workflow_ids ?? [],
      };
      return editor?.mode === "edit"
        ? updateEmployee(editor.employee.id, normalizedValues)
        : createEmployee(normalizedValues);
    },
    onSuccess: async () => {
      setEditor(undefined);
      form.resetFields();
      await queryClient.resetQueries({ queryKey: ["employees"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (employee: Employee) => {
      setDeleteNotice(undefined);
      await deleteEmployee(employee.id);
      return employee;
    },
    onSuccess: async (deleted) => {
      setDeleteNotice(`数字员工“${deleted.name}”已删除`);
      await queryClient.resetQueries({ queryKey: ["employees"] });
    },
  });

  const closeEditor = () => {
    setEditor(undefined);
    saveMutation.reset();
    form.resetFields();
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
            配置通用会话角色和系统指令，可按需绑定一个知识库并授权独立工作流。
          </Typography.Paragraph>
        </div>
        <Button
          type="primary"
          aria-label="创建数字员工"
          icon={<Plus aria-hidden="true" size={16} />}
          disabled={readOnly}
          onClick={() => setEditor({ mode: "create" })}
        >
          创建数字员工
        </Button>
      </Flex>

      <Input.Search
        aria-label="搜索数字员工"
        allowClear
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

      {deleteNotice && (
        <Alert
          type="success"
          showIcon
          closable
          title={deleteNotice}
          className="employees-inline-alert"
        />
      )}

      {deleteMutation.isError && (
        <Alert
          type="error"
          showIcon
          closable
          title="数字员工删除失败"
          description={getResourceDeletionErrorMessage(deleteMutation.error)}
          className="employees-inline-alert"
          onClose={() => deleteMutation.reset()}
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
            <Card
              key={employee.id}
              className="employee-card"
              title={employee.name}
              extra={knowledgeBaseLabel(employee)}
            >
              <Text type="secondary" className="employee-description">
                {employee.description || "暂无说明"}
              </Text>
              <div className="employee-prompt-preview">
                <Text type="secondary">系统指令</Text>
                <Text>{employee.system_prompt}</Text>
              </div>
              <div className="employee-prompt-preview">
                <Text type="secondary">工作流权限</Text>
                <div>{workflowPermissionLabel(employee)}</div>
              </div>
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
                  onClick={() => setEditor({ mode: "edit", employee })}
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
        okButtonProps={{ disabled: readOnly }}
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
        </Form>
      </Modal>
    </section>
  );
}
