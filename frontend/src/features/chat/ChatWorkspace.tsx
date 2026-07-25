import { Alert, Button, Flex, Input, Select, Skeleton, Tag, Typography } from "antd";
import { Bot, Send, Square } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { Employee } from "../../api/employees";
import { getErrorMessage } from "../../api/errors";
import { ToolGrantSelector } from "../tools/index";
import { MessageBubble } from "./ChatMessages";
import { shouldFollowBottom } from "./textReveal";
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
    stopMutation,
    workflowsById,
    hasMoreRuns,
    loadMoreRuns,
    loadingMoreRuns,
    openWorkflowRun,
  } = controller;

  const scrollBottomRef = useRef<HTMLDivElement>(null);
  const scrollViewRef = useRef<HTMLDivElement>(null);
  // 通用会话可以逐轮换模型，署名行要说明这条回复实际由哪个模型生成
  const modelNames = useMemo(
    () =>
      new Map(
        controller.modelConfigurationItems.map((configuration) => [
          configuration.id,
          configuration.display_name,
        ]),
      ),
    [controller.modelConfigurationItems],
  );
  const authorNameOf = (message: { model_configuration_id: string | null; model_identifier: string | null }) =>
    employee?.name ??
    (message.model_configuration_id ? modelNames.get(message.model_configuration_id) : undefined) ??
    message.model_identifier ??
    "AI";
  const renderedMessages = messages.isSuccess ? messages.data : undefined;
  // 内容变长（新消息或流式增量）时把对话区滚到最新，避免用户手动下拉。
  const scrollSignal = renderedMessages
    ? `${renderedMessages.length}:${renderedMessages.at(-1)?.content.length ?? 0}`
    : "";
  const streaming = Boolean(activeMessage);
  // 读者在生成过程中往回翻去看前文时, 本轮就不再自动跟随, 免得跟他的滚动打架;
  // 等他自己发下一条消息, 或者自己滚回底部, 再恢复默认的跟随最新内容。
  const [autoFollow, setAutoFollow] = useState(true);
  const noteReaderScroll = () => {
    const view = scrollViewRef.current;
    if (view) setAutoFollow(shouldFollowBottom(view));
  };
  // 用户主动开启下一轮(发送或重新生成)时回到默认跟随
  const followFromNextTurn = () => setAutoFollow(true);

  useEffect(() => {
    if (!scrollSignal || !autoFollow) return;
    // 生成中每个增量都会触发一次滚动, 用平滑滚动会不断打断上一次动画, 看上去就是一顿一顿的;
    // 流式期间直接贴底, 只有新消息、切换会话这类跳跃才用平滑滚动。
    scrollBottomRef.current?.scrollIntoView({
      block: "end",
      behavior: streaming ? "auto" : "smooth",
    });
  }, [scrollSignal, streaming, autoFollow]);

  // 文字是按帧逐个吐出来的, 光靠增量事件驱动滚动会跟不上; 生成期间每帧贴一次底,
  // 读者往上翻去看前文时就停止跟随, 不把他拽回来。
  useEffect(() => {
    if (!streaming || !autoFollow) return;
    let frame = 0;
    const follow = () => {
      const view = scrollViewRef.current;
      if (view && shouldFollowBottom(view)) view.scrollTop = view.scrollHeight;
      frame = requestAnimationFrame(follow);
    };
    frame = requestAnimationFrame(follow);
    return () => cancelAnimationFrame(frame);
  }, [streaming, autoFollow]);

  return (
    <div className="chat-workspace">
      <main className="chat-messages-panel" role="region" aria-label="消息区域">
        <div
          className="chat-message-scroll"
          ref={scrollViewRef}
          aria-live="polite"
          onWheel={noteReaderScroll}
          onTouchMove={noteReaderScroll}
        >
          {!selectedConversation ? (
            <ChatWelcome employee={employee} />
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
            <ChatWelcome employee={employee} />
          ) : (
            messages.data.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                authorName={authorNameOf(message)}
                reasoning={controller.reasoningByMessageId.get(message.id)}
                toolCalls={controller.toolCallsByMessageId.get(message.id) ?? []}
                toolCapabilityNames={controller.toolCapabilityNames}
                workflowRuns={runsByMessageId.get(message.id) ?? []}
                workflows={workflowsById}
                retrying={retryMutation.isPending && retryMutation.variables === message.id}
                readOnly={readOnly}
                onOpenWorkflowRun={openWorkflowRun}
                onRetry={(messageId) => {
                  followFromNextTurn();
                  retryMutation.mutate(messageId);
                }}
              />
            ))
          )}
          {hasMoreRuns && (
            <Button loading={loadingMoreRuns} onClick={() => void loadMoreRuns()}>
              加载更多运行记录
            </Button>
          )}
          <div ref={scrollBottomRef} aria-hidden="true" />
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
              followFromNextTurn();
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
                onClick={() => {
                  followFromNextTurn();
                  sendDraft();
                }}
              >
                发送
              </Button>
            )}
          </Flex>
        </div>
      </main>

      <aside className="chat-employee-panel" role="region" aria-label="数字员工信息">
        {employee ? (
          <EmployeeDetails
            employee={employee}
            toolGrantCount={controller.employeeToolGrants.data?.capability_ids.length}
            toolGrantError={controller.employeeToolGrants.error}
          />
        ) : (
          <GenericAssistantDetails controller={controller} readOnly={readOnly} />
        )}
      </aside>
    </div>
  );
}

function ChatWelcome({ employee }: { employee?: Employee }) {
  return (
    <div className="chat-welcome">
      <span className="chat-welcome-mark" aria-hidden="true">
        <Bot size={26} strokeWidth={1.75} />
      </span>
      {/* 不绑数字员工时不自报名号：通用 AI 是使用方式而不是一个有名字的对象 */}
      <Title level={2} className="chat-welcome-title">
        {employee ? `你好，我是${employee.name}` : "你好"}
      </Title>
      <Text type="secondary">
        {employee
          ? employee.description ||
            (employee.knowledge_base_id
              ? "每次提问都会自动检索绑定的知识库后回答。"
              : "直接使用所选模型回答你的问题。")
          : "输入下面第一条消息即可开始，会话会自动保存。"}
      </Text>
    </div>
  );
}

function GenericAssistantDetails({
  controller,
  readOnly,
}: {
  controller: ChatPageController;
  readOnly: boolean;
}) {
  const grantsPending = Boolean(
    controller.selectedConversationId && controller.conversationToolGrants.isPending,
  );
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
      <div className="chat-tool-grants">
        <Text strong>会话工具授权</Text>
        {controller.toolCatalog.isPending || grantsPending ? (
          <Skeleton active paragraph={{ rows: 3 }} />
        ) : controller.toolCatalog.isError ? (
          <Alert
            type="warning"
            showIcon
            title="工具目录暂不可用，对话仍可继续"
            description={getErrorMessage(controller.toolCatalog.error)}
            action={
              <Button size="small" onClick={() => void controller.toolCatalog.refetch()}>
                重试
              </Button>
            }
          />
        ) : controller.conversationToolGrants.isError ? (
          <Alert
            type="warning"
            showIcon
            title="会话工具授权加载失败"
            description={getErrorMessage(controller.conversationToolGrants.error)}
            action={
              <Button
                size="small"
                onClick={() => void controller.conversationToolGrants.refetch()}
              >
                重试
              </Button>
            }
          />
        ) : controller.toolCatalog.data ? (
          <>
            <ToolGrantSelector
              catalog={controller.toolCatalog.data}
              value={controller.toolSelection}
              disabled={readOnly || Boolean(controller.activeMessage)}
              onChange={controller.setToolSelection}
            />
            {controller.selectedConversationId ? (
              <Button
                type="primary"
                loading={controller.saveToolGrantsMutation.isPending}
                disabled={readOnly || Boolean(controller.activeMessage)}
                onClick={() =>
                  controller.saveToolGrantsMutation.mutate(controller.toolSelection)
                }
              >
                保存会话工具
              </Button>
            ) : (
              <Text type="secondary">首条消息会将当前授权与会话原子保存。</Text>
            )}
            {controller.saveToolGrantsMutation.isSuccess ? (
              <Text type="success">会话工具授权已保存</Text>
            ) : null}
          </>
        ) : null}
      </div>
      <Alert type="info" showIcon title="发送第一条消息时会自动创建并保存会话" />
    </>
  );
}

function EmployeeDetails({
  employee,
  toolGrantCount,
  toolGrantError,
}: {
  employee: Employee;
  toolGrantCount?: number;
  toolGrantError: Error | null;
}) {
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
        {toolGrantCount !== undefined ? <Tag>{toolGrantCount} 个工具权限</Tag> : null}
      </div>
      {toolGrantError ? (
        <Alert type="warning" showIcon title="数字员工工具权限暂不可用" />
      ) : null}
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
