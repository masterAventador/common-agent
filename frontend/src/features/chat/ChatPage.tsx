import {
  CommentOutlined,
  FileTextOutlined,
  PlusOutlined,
  RedoOutlined,
  ReloadOutlined,
  SendOutlined,
  StopOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Collapse,
  Empty,
  Flex,
  Input,
  Progress,
  Select,
  Skeleton,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  createConversation,
  fetchConversationMessages,
  fetchConversations,
  retryConversationMessage,
  sendConversationMessage,
  stopConversationGeneration,
  subscribeToConversationEvents,
  type ConversationEvent,
  type ConversationMessage,
} from "../../api/conversations";
import { fetchEmployees, type Employee } from "../../api/employees";
import { getErrorMessage } from "../../api/errors";
import {
  fetchConversationWorkflowRuns,
  type WorkflowRun,
} from "../../api/workflowRuns";
import { fetchWorkflows, type Workflow } from "../../api/workflows";

const { Text, Title } = Typography;
const messageStatusOrder: Record<ConversationMessage["status"], number> = {
  pending: 0,
  streaming: 1,
  completed: 2,
  failed: 2,
  stopped: 2,
};

function replaceMessage(
  messages: ConversationMessage[] | undefined,
  nextMessage: ConversationMessage,
): ConversationMessage[] {
  const current = messages ?? [];
  const existingIndex = current.findIndex((message) => message.id === nextMessage.id);
  const existing = current[existingIndex];
  if (existing) {
    const existingUpdatedAt = Date.parse(existing.updated_at);
    const nextUpdatedAt = Date.parse(nextMessage.updated_at);
    if (
      nextUpdatedAt < existingUpdatedAt ||
      (nextUpdatedAt === existingUpdatedAt &&
        messageStatusOrder[nextMessage.status] < messageStatusOrder[existing.status])
    ) {
      return current;
    }
  }
  const next =
    existingIndex === -1
      ? [...current, nextMessage]
      : current.map((message, index) => (index === existingIndex ? nextMessage : message));
  return [...next].sort((left, right) => left.sequence_number - right.sequence_number);
}

function mergeAcceptedTurn(
  messages: ConversationMessage[] | undefined,
  userMessage: ConversationMessage,
  assistantMessage: ConversationMessage,
): ConversationMessage[] {
  return replaceMessage(replaceMessage(messages, userMessage), assistantMessage);
}

function formatConversationTime(timestamp: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(timestamp));
}

function EmployeeDetails({ employee }: { employee: Employee }) {
  return (
    <>
      <div className="chat-employee-avatar" aria-hidden="true">
        <TeamOutlined />
      </div>
      <Title level={4}>{employee.name}</Title>
      <Text type="secondary">{employee.description || "暂无说明"}</Text>
      <div className="chat-employee-binding">
        {employee.knowledge_base_id ? (
          <Tag color="blue">已绑定知识库</Tag>
        ) : (
          <Tag>未绑定知识库</Tag>
        )}
        <Tag>{employee.allowed_workflow_ids.length} 个工作流权限</Tag>
      </div>
      <div className="chat-system-prompt">
        <Text type="secondary">系统指令</Text>
        <Text>{employee.system_prompt}</Text>
      </div>
      <Alert
        type="info"
        showIcon
        title={
          employee.knowledge_base_id
            ? "每次提问都会自动检索已绑定知识库"
            : "当前员工使用通用模型能力回答"
        }
      />
    </>
  );
}

function CitationList({ message }: { message: ConversationMessage }) {
  if (message.citations.length === 0) return null;
  return (
    <div className="chat-citations" aria-label={`引用资料 ${message.citations.length}`}>
      <Text strong>
        <FileTextOutlined /> 引用资料 {message.citations.length}
      </Text>
      {message.citations.map((citation) => (
        <div
          key={`${citation.knowledge_base_id}:${citation.chunk_id}`}
          className="chat-citation-item"
        >
          <Flex justify="space-between" align="center" gap={8}>
            <Text strong>{citation.document_name}</Text>
            <Tag color="geekblue">相关度 {Math.round(citation.score * 100)}%</Tag>
          </Flex>
          <Text type="secondary">{citation.content}</Text>
        </div>
      ))}
    </div>
  );
}

const workflowRunStatus: Record<
  WorkflowRun["status"],
  { color: string; label: string }
> = {
  pending: { color: "default", label: "等待运行" },
  running: { color: "processing", label: "运行中" },
  completed: { color: "success", label: "已完成" },
  failed: { color: "error", label: "运行失败" },
  stopped: { color: "default", label: "已停止" },
};

function WorkflowRunCards({
  runs,
  workflows,
  onOpen,
}: {
  runs: WorkflowRun[];
  workflows: Map<string, Workflow>;
  onOpen: (runId: string) => void;
}) {
  if (runs.length === 0) return null;
  return (
    <div className="chat-workflow-runs" aria-label={`工作流运行 ${runs.length}`}>
      <Text strong>工作流运行</Text>
      <Collapse
        size="small"
        items={runs.map((run) => {
          const workflow = workflows.get(run.workflow_id);
          const status = workflowRunStatus[run.status];
          const nodeCount = workflow?.nodes.length ?? run.completed_node_ids.length;
          const progress =
            nodeCount === 0
              ? 0
              : Math.min(100, Math.round((run.completed_node_ids.length / nodeCount) * 100));
          return {
            key: run.id,
            label: (
              <Flex justify="space-between" align="center" gap={8}>
                <Text strong>{workflow?.name ?? `工作流 ${run.workflow_id.slice(0, 8)}`}</Text>
                <Tag color={status.color}>{status.label}</Tag>
              </Flex>
            ),
            children: (
              <div className="chat-workflow-run-summary">
                <Progress
                  percent={run.status === "completed" ? 100 : progress}
                  status={run.status === "failed" ? "exception" : undefined}
                  size="small"
                />
                <div>
                  <Text type="secondary">输入</Text>
                  <Typography.Paragraph>{run.input}</Typography.Paragraph>
                </div>
                {run.output && (
                  <div>
                    <Text type="secondary">运行结果</Text>
                    <Typography.Paragraph>{run.output}</Typography.Paragraph>
                  </div>
                )}
                {run.error_code && <Alert type="error" showIcon title={run.error_code} />}
                <Button size="small" onClick={() => onOpen(run.id)}>
                  查看运行详情
                </Button>
              </div>
            ),
          };
        })}
      />
    </div>
  );
}

function MessageBubble({
  message,
  workflowRuns,
  workflows,
  retrying,
  onOpenWorkflowRun,
  onRetry,
}: {
  message: ConversationMessage;
  workflowRuns: WorkflowRun[];
  workflows: Map<string, Workflow>;
  retrying: boolean;
  onOpenWorkflowRun: (runId: string) => void;
  onRetry: (messageId: string) => void;
}) {
  const isAssistant = message.role === "assistant";
  const isActive = ["pending", "streaming"].includes(message.status);
  const mayRetry = isAssistant && ["failed", "stopped"].includes(message.status);
  return (
    <article
      className={`chat-message ${isAssistant ? "is-assistant" : "is-user"}`}
      aria-label={isAssistant ? "助手消息" : "用户消息"}
    >
      <div className="chat-message-author">{isAssistant ? "AI" : "你"}</div>
      <div className="chat-message-body">
        {message.content ? (
          <Typography.Paragraph className="chat-message-content">
            {message.content}
          </Typography.Paragraph>
        ) : isActive ? (
          <Space>
            <Spin size="small" />
            <Text type="secondary">正在思考…</Text>
          </Space>
        ) : (
          <Text type="secondary">本次没有生成可显示的内容</Text>
        )}
        {message.status === "failed" && <Tag color="error">生成失败</Tag>}
        {message.status === "stopped" && <Tag>已停止</Tag>}
        {mayRetry && (
          <Button
            size="small"
            icon={<RedoOutlined />}
            loading={retrying}
            aria-label="重试回答"
            onClick={() => onRetry(message.id)}
          >
            重新生成
          </Button>
        )}
        <CitationList message={message} />
        {isAssistant && (
          <WorkflowRunCards
            runs={workflowRuns}
            workflows={workflows}
            onOpen={onOpenWorkflowRun}
          />
        )}
      </div>
    </article>
  );
}

export function ChatPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [draft, setDraft] = useState("");
  const [streamNotice, setStreamNotice] = useState<string>();
  const lastEventSequence = useRef(0);
  const requestedEmployeeId = searchParams.get("employee_id");
  const requestedConversationId = searchParams.get("conversation_id");

  const employees = useQuery({ queryKey: ["employees"], queryFn: fetchEmployees });
  const selectedEmployee = useMemo(
    () =>
      employees.data?.find((employee) => employee.id === requestedEmployeeId) ??
      employees.data?.[0],
    [employees.data, requestedEmployeeId],
  );
  const conversations = useQuery({
    queryKey: ["conversations", selectedEmployee?.id],
    queryFn: () => fetchConversations(selectedEmployee?.id),
    enabled: Boolean(selectedEmployee),
  });
  const selectedConversation = conversations.data?.find(
    (conversation) => conversation.id === requestedConversationId,
  );
  const selectedConversationId = selectedConversation?.id;
  const messages = useQuery({
    queryKey: ["conversation-messages", selectedConversation?.id],
    queryFn: () => fetchConversationMessages(selectedConversation?.id ?? ""),
    enabled: Boolean(selectedConversation),
  });
  const hasActiveAssistant = Boolean(
    messages.data?.some(
      (message) =>
        message.role === "assistant" && ["pending", "streaming"].includes(message.status),
    ),
  );
  const workflowRuns = useQuery({
    queryKey: ["conversation-workflow-runs", selectedConversationId],
    queryFn: () => fetchConversationWorkflowRuns(selectedConversationId ?? ""),
    enabled: Boolean(selectedConversationId),
    refetchInterval: hasActiveAssistant ? 1_000 : false,
  });
  const workflows = useQuery({
    queryKey: ["workflows"],
    queryFn: fetchWorkflows,
    enabled: Boolean(selectedConversationId),
  });
  const workflowsById = useMemo(
    () => new Map((workflows.data ?? []).map((workflow) => [workflow.id, workflow])),
    [workflows.data],
  );
  const runsByMessageId = useMemo(() => {
    const grouped = new Map<string, WorkflowRun[]>();
    for (const run of workflowRuns.data ?? []) {
      const messageId = run.origin?.assistant_message_id;
      if (!messageId) continue;
      grouped.set(messageId, [...(grouped.get(messageId) ?? []), run]);
    }
    return grouped;
  }, [workflowRuns.data]);

  useEffect(() => {
    if (!employees.data?.length || !selectedEmployee || selectedEmployee.id === requestedEmployeeId) {
      return;
    }
    setSearchParams({ employee_id: selectedEmployee.id }, { replace: true });
  }, [employees.data, requestedEmployeeId, selectedEmployee, setSearchParams]);

  useEffect(() => {
    if (!selectedEmployee || !conversations.data?.length || selectedConversation) return;
    setSearchParams(
      {
        employee_id: selectedEmployee.id,
        conversation_id: conversations.data[0].id,
      },
      { replace: true },
    );
  }, [conversations.data, selectedConversation, selectedEmployee, setSearchParams]);

  useEffect(() => {
    if (!selectedConversationId) return;
    lastEventSequence.current = 0;
    const subscription = subscribeToConversationEvents(selectedConversationId, {
      afterSequence: 0,
      onEvent: (event: ConversationEvent) => {
        if (event.sequence <= lastEventSequence.current) return;
        lastEventSequence.current = event.sequence;
        queryClient.setQueryData<ConversationMessage[]>(
          ["conversation-messages", selectedConversationId],
          (current) => replaceMessage(current, event.message),
        );
        setStreamNotice(undefined);
        if (["assistant.completed", "assistant.failed", "assistant.stopped"].includes(event.type)) {
          void queryClient.invalidateQueries({
            queryKey: ["conversations", selectedEmployee?.id],
          });
          void queryClient.invalidateQueries({
            queryKey: ["conversation-workflow-runs", selectedConversationId],
          });
        }
      },
      onError: () => {
        setStreamNotice("会话连接已中断，正在恢复消息历史");
        void queryClient.invalidateQueries({
          queryKey: ["conversation-messages", selectedConversationId],
        });
        void queryClient.invalidateQueries({
          queryKey: ["conversation-workflow-runs", selectedConversationId],
        });
      },
    });
    return () => subscription.close();
  }, [queryClient, selectedConversationId, selectedEmployee?.id]);

  const selectConversation = (conversationId: string) => {
    if (!selectedEmployee) return;
    setStreamNotice(undefined);
    setSearchParams({
      employee_id: selectedEmployee.id,
      conversation_id: conversationId,
    });
  };

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!selectedEmployee) throw new Error("请先选择数字员工");
      return createConversation({
        conversation_id: crypto.randomUUID(),
        employee_id: selectedEmployee.id,
        title: "新会话",
      });
    },
    onSuccess: (created) => {
      queryClient.setQueryData<typeof conversations.data>(
        ["conversations", created.employee_id],
        (current) => [created, ...(current ?? []).filter((item) => item.id !== created.id)],
      );
      selectConversation(created.id);
    },
  });

  const sendMutation = useMutation({
    mutationFn: async (content: string) => {
      if (!selectedConversation) throw new Error("请先创建会话");
      return sendConversationMessage(selectedConversation.id, {
        message_id: crypto.randomUUID(),
        content,
      });
    },
    onSuccess: (turn) => {
      if (!selectedConversation) return;
      setDraft("");
      queryClient.setQueryData<ConversationMessage[]>(
        ["conversation-messages", selectedConversation.id],
        (current) => mergeAcceptedTurn(current, turn.user_message, turn.assistant_message),
      );
    },
  });

  const stopMutation = useMutation({
    mutationFn: async () => {
      if (!selectedConversation) throw new Error("当前没有可停止的会话");
      return stopConversationGeneration(selectedConversation.id);
    },
  });

  const retryMutation = useMutation({
    mutationFn: (messageId: string) => retryConversationMessage(messageId),
    onSuccess: (turn) => {
      if (!selectedConversation) return;
      queryClient.setQueryData<ConversationMessage[]>(
        ["conversation-messages", selectedConversation.id],
        (current) => replaceMessage(current, turn.assistant_message),
      );
    },
  });

  const activeMessage = messages.data?.find(
    (message) => message.role === "assistant" && ["pending", "streaming"].includes(message.status),
  );
  const sendDraft = () => {
    const content = draft.trim();
    if (!content || activeMessage || sendMutation.isPending) return;
    sendMutation.mutate(content);
  };

  if (employees.isPending) {
    return (
      <section className="chat-page" aria-label="AI 会话加载中">
        <Skeleton active paragraph={{ rows: 10 }} />
      </section>
    );
  }

  if (employees.isError) {
    return (
      <section className="chat-page">
        <Alert
          type="error"
          showIcon
          title="数字员工加载失败"
          description={getErrorMessage(employees.error)}
          action={
            <Button icon={<ReloadOutlined />} onClick={() => void employees.refetch()}>
              重试加载
            </Button>
          }
        />
      </section>
    );
  }

  if (!selectedEmployee) {
    return (
      <section className="chat-page">
        <Empty description="还没有可用于会话的数字员工" />
      </section>
    );
  }

  return (
    <section className="chat-page">
      <Flex justify="space-between" align="center" gap={24} className="chat-page-heading">
        <div>
          <Space align="center">
            <CommentOutlined className="chat-title-icon" />
            <Title level={2}>AI 会话</Title>
          </Space>
          <Typography.Paragraph type="secondary">
            选择数字员工持续对话，绑定知识库后每次提问都会自动检索。
          </Typography.Paragraph>
        </div>
        <Select
          aria-label="选择数字员工"
          value={selectedEmployee.id}
          options={employees.data?.map((employee) => ({
            value: employee.id,
            label: employee.name,
          }))}
          onChange={(employeeId) => setSearchParams({ employee_id: employeeId })}
          className="chat-employee-select"
        />
      </Flex>

      {(createMutation.isError || sendMutation.isError || stopMutation.isError || retryMutation.isError) && (
        <Alert
          type="error"
          showIcon
          closable
          title="会话操作失败"
          description={getErrorMessage(
            createMutation.error ?? sendMutation.error ?? stopMutation.error ?? retryMutation.error,
          )}
          className="chat-inline-alert"
        />
      )}
      {streamNotice && (
        <Alert
          type="warning"
          showIcon
          title={streamNotice}
          className="chat-inline-alert"
        />
      )}

      <div className="chat-workspace">
        <aside className="chat-conversations-panel" role="region" aria-label="会话列表">
          <Flex justify="space-between" align="center" gap={8} className="chat-panel-heading">
            <Text strong>会话</Text>
            <Button
              type="primary"
              size="small"
              icon={<PlusOutlined />}
              loading={createMutation.isPending}
              aria-label="新建会话"
              onClick={() => createMutation.mutate()}
            >
              新建
            </Button>
          </Flex>
          {conversations.isPending ? (
            <Skeleton active paragraph={{ rows: 6 }} />
          ) : conversations.isError ? (
            <Alert
              type="error"
              showIcon
              title="会话列表加载失败"
              action={<Button onClick={() => void conversations.refetch()}>重试</Button>}
            />
          ) : conversations.data.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有会话" />
          ) : (
            <div className="chat-conversation-list">
              {conversations.data.map((conversation) => (
                <div key={conversation.id} className="chat-conversation-list-item">
                  <button
                    type="button"
                    className={`chat-conversation-button ${
                      selectedConversation?.id === conversation.id ? "is-active" : ""
                    }`}
                    aria-label={`打开会话 ${conversation.title}`}
                    onClick={() => selectConversation(conversation.id)}
                  >
                    <Text strong>{conversation.title}</Text>
                    <Text type="secondary">{formatConversationTime(conversation.updated_at)}</Text>
                  </button>
                </div>
              ))}
            </div>
          )}
        </aside>

        <main className="chat-messages-panel" role="region" aria-label="消息区域">
          <div className="chat-messages-heading">
            <div>
              <Title level={3}>{selectedConversation?.title ?? "选择一个会话"}</Title>
              <Text type="secondary">{selectedEmployee.name}</Text>
            </div>
            {activeMessage && <Tag color="processing">正在生成</Tag>}
          </div>
          <div className="chat-message-scroll" aria-live="polite">
            {!selectedConversation ? (
              <Empty description="新建或选择会话后开始提问" />
            ) : messages.isPending ? (
              <Skeleton active paragraph={{ rows: 8 }} />
            ) : messages.isError ? (
              <Alert
                type="error"
                showIcon
                title="消息历史加载失败"
                description={getErrorMessage(messages.error)}
                action={<Button onClick={() => void messages.refetch()}>重试</Button>}
              />
            ) : messages.data.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="发送第一条消息开始对话" />
            ) : (
              messages.data.map((message) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  workflowRuns={runsByMessageId.get(message.id) ?? []}
                  workflows={workflowsById}
                  retrying={retryMutation.isPending && retryMutation.variables === message.id}
                  onOpenWorkflowRun={(runId) => navigate(`/workflows?run_id=${runId}`)}
                  onRetry={(messageId) => retryMutation.mutate(messageId)}
                />
              ))
            )}
          </div>
          <div className="chat-composer">
            <Input.TextArea
              aria-label="消息输入"
              value={draft}
              autoSize={{ minRows: 2, maxRows: 6 }}
              maxLength={200_000}
              disabled={!selectedConversation}
              placeholder={selectedConversation ? "输入消息，Enter 发送，Shift+Enter 换行" : "请先新建会话"}
              onChange={(event) => setDraft(event.target.value)}
              onPressEnter={(event) => {
                if (event.shiftKey) return;
                event.preventDefault();
                sendDraft();
              }}
            />
            <Flex justify="space-between" align="center" gap={12}>
              <Text type="secondary">回复、引用和状态都会自动保存，刷新后可恢复。</Text>
              {activeMessage ? (
                <Button
                  danger
                  icon={<StopOutlined />}
                  loading={stopMutation.isPending}
                  aria-label="停止生成"
                  onClick={() => stopMutation.mutate()}
                >
                  停止生成
                </Button>
              ) : (
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  loading={sendMutation.isPending}
                  disabled={!selectedConversation || !draft.trim()}
                  aria-label="发送消息"
                  onClick={sendDraft}
                >
                  发送
                </Button>
              )}
            </Flex>
          </div>
        </main>

        <aside className="chat-employee-panel" role="region" aria-label="数字员工信息">
          <EmployeeDetails employee={selectedEmployee} />
        </aside>
      </div>
    </section>
  );
}
