import { Alert, Button, Empty, Flex, Input, Select, Skeleton, Tag, Typography } from "antd";
import { Bot, Send, Square } from "lucide-react";

import type { Employee } from "../../api/employees";
import { getErrorMessage } from "../../api/errors";
import { MessageBubble } from "./ChatMessages";
import type { ChatPageController } from "./useChatPageController";

const { Text, Title } = Typography;

export function ChatWorkspace({
  controller,
  employee,
  readOnly = false,
}: {
  controller: ChatPageController;
  employee?: Employee;
  readOnly?: boolean;
}) {
  const {
    activeMessage,
    draft,
    messages,
    retryMutation,
    runsByMessageId,
    selectedConversation,
    selectedModelConfigurationId,
    sendDraft,
    sendMutation,
    setDraft,
    setSelectedModelConfigurationId,
    startNewConversation,
    stopMutation,
    workflowsById,
    hasMoreRuns,
    loadMoreRuns,
    loadingMoreRuns,
    openWorkflowRun,
  } = controller;

  return (
    <div className="chat-workspace">
      <main className="chat-messages-panel" role="region" aria-label="消息区域">
        <div className="chat-messages-heading">
          <div>
            <Title level={3}>{selectedConversation?.title ?? "新会话"}</Title>
            <Text type="secondary">{employee?.name ?? "通用 AI"}</Text>
          </div>
          <Flex align="center" gap={8}>
            {activeMessage && <Tag color="processing">正在生成</Tag>}
            <Button size="small" disabled={readOnly} onClick={startNewConversation}>
              新建会话
            </Button>
          </Flex>
        </div>
        <div className="chat-message-scroll" aria-live="polite">
          {!selectedConversation ? (
            <Empty description="输入第一条消息后会自动创建会话" />
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
                readOnly={readOnly}
                onOpenWorkflowRun={openWorkflowRun}
                onRetry={(messageId) => retryMutation.mutate(messageId)}
              />
            ))
          )}
          {hasMoreRuns && (
            <Button loading={loadingMoreRuns} onClick={() => void loadMoreRuns()}>
              加载更多运行记录
            </Button>
          )}
        </div>
        <div className="chat-composer">
          <Input.TextArea
            aria-label="消息输入"
            value={draft}
            autoSize={{ minRows: 2, maxRows: 6 }}
            maxLength={200_000}
            disabled={readOnly || !selectedModelConfigurationId}
            placeholder="输入消息，Enter 发送，Shift+Enter 换行"
            onChange={(event) => setDraft(event.target.value)}
            onPressEnter={(event) => {
              if (readOnly) return;
              if (event.shiftKey) return;
              event.preventDefault();
              sendDraft();
            }}
          />
          <Flex justify="space-between" align="center" gap={12} wrap="wrap">
            <Select
              aria-label="选择模型"
              value={selectedModelConfigurationId || undefined}
              options={controller.modelConfigurationItems.map((configuration) => ({
                value: configuration.id,
                label: configuration.display_name,
              }))}
              onChange={setSelectedModelConfigurationId}
              onPopupScroll={(event) => {
                const target = event.currentTarget;
                if (
                  controller.modelConfigurations.hasNextPage &&
                  !controller.modelConfigurations.isFetchingNextPage &&
                  target.scrollTop + target.clientHeight >= target.scrollHeight - 16
                ) {
                  void controller.modelConfigurations.fetchNextPage();
                }
              }}
              className="chat-model-select"
              disabled={readOnly || Boolean(activeMessage)}
            />
            <Text type="secondary" className="chat-composer-note">
              本轮回复将使用所选模型，消息和引用会自动保存。
            </Text>
            {activeMessage ? (
              <Button
                danger
                icon={<Square aria-hidden="true" size={15} />}
                loading={stopMutation.isPending}
                disabled={readOnly}
                aria-label="停止生成"
                onClick={() => stopMutation.mutate()}
              >
                停止生成
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<Send aria-hidden="true" size={15} />}
                loading={sendMutation.isPending}
                disabled={readOnly || !selectedModelConfigurationId || !draft.trim()}
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
        {employee ? <EmployeeDetails employee={employee} /> : <GenericAssistantDetails />}
      </aside>
    </div>
  );
}

function GenericAssistantDetails() {
  return (
    <>
      <div className="chat-employee-avatar" aria-hidden="true">
        <Bot aria-hidden="true" size={23} strokeWidth={1.75} />
      </div>
      <Title level={4}>通用 AI</Title>
      <Text type="secondary">不绑定数字员工，直接使用当前选择的模型持续对话。</Text>
      <div className="chat-employee-binding">
        <Tag color="blue">模型可逐轮切换</Tag>
        <Tag>不检索知识库</Tag>
      </div>
      <Alert type="info" showIcon title="发送第一条消息时会自动创建并保存会话" />
    </>
  );
}

function EmployeeDetails({ employee }: { employee: Employee }) {
  return (
    <>
      <div className="chat-employee-avatar" aria-hidden="true">
        <Bot aria-hidden="true" size={23} strokeWidth={1.75} />
      </div>
      <Title level={4}>{employee.name}</Title>
      <Text type="secondary">{employee.description || "暂无说明"}</Text>
      <div className="chat-employee-binding">
        {employee.knowledge_base_id ? <Tag color="blue">已绑定知识库</Tag> : <Tag>未绑定知识库</Tag>}
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
