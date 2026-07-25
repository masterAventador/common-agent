import { Alert, Button, Collapse, Flex, Progress, Space, Spin, Tag, Typography } from "antd";
import { FileText, RotateCcw } from "lucide-react";

import type { ConversationMessage } from "../../api/conversations";
import type { WorkflowRun } from "../../api/workflowRuns";
import type { Workflow } from "../../api/workflows";
import type { ChatToolCallLifecycle } from "./useChatPageController";

const { Text } = Typography;
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

export function MessageBubble({
  message,
  toolCalls,
  toolCapabilityNames,
  workflowRuns,
  workflows,
  retrying,
  readOnly = false,
  onOpenWorkflowRun,
  onRetry,
}: {
  message: ConversationMessage;
  toolCalls: ChatToolCallLifecycle[];
  toolCapabilityNames: Map<string, string>;
  workflowRuns: WorkflowRun[];
  workflows: Map<string, Workflow>;
  retrying: boolean;
  readOnly?: boolean;
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
            icon={<RotateCcw aria-hidden="true" size={15} />}
            loading={retrying}
            disabled={readOnly}
            aria-label="重试回答"
            onClick={() => onRetry(message.id)}
          >
            重新生成
          </Button>
        )}
        <CitationList message={message} />
        {isAssistant && (
          <ToolCallLifecycle
            calls={toolCalls}
            capabilityNames={toolCapabilityNames}
          />
        )}
        {isAssistant && (
          <WorkflowRunCards runs={workflowRuns} workflows={workflows} onOpen={onOpenWorkflowRun} />
        )}
      </div>
    </article>
  );
}

function ToolCallLifecycle({
  calls,
  capabilityNames,
}: {
  calls: ChatToolCallLifecycle[];
  capabilityNames: Map<string, string>;
}) {
  if (calls.length === 0) return null;
  const statuses: Record<
    ChatToolCallLifecycle["status"],
    { color: string; label: string }
  > = {
    running: { color: "processing", label: "运行中" },
    completed: { color: "success", label: "已完成" },
    failed: { color: "error", label: "调用失败" },
  };
  return (
    <div className="chat-tool-calls" aria-label={`工具调用 ${calls.length}`}>
      <Text strong>工具调用</Text>
      {calls.map((call) => {
        const status = statuses[call.status];
        return (
          <Flex key={call.toolCallId} justify="space-between" align="center" gap={8}>
            <Text>
              {capabilityNames.get(call.capabilityId) ?? call.capabilityName}
            </Text>
            <Tag color={status.color}>{status.label}</Tag>
            {call.status === "failed" && call.errorCode ? (
              <Text type="danger">{call.errorCode}</Text>
            ) : null}
          </Flex>
        );
      })}
    </div>
  );
}

function CitationList({ message }: { message: ConversationMessage }) {
  // 同一文档可能命中多个片段，按文档名去重，只列引用了哪些资料。
  const documentNames = [...new Set(message.citations.map((citation) => citation.document_name))];
  if (documentNames.length === 0) return null;
  return (
    <div className="chat-citations" aria-label={`引用资料 ${documentNames.length}`}>
      <Text strong>
        <FileText aria-hidden="true" size={14} /> 引用资料 {documentNames.length}
      </Text>
      {documentNames.map((name) => (
        <div key={name} className="chat-citation-item">
          <Text>{name}</Text>
        </div>
      ))}
    </div>
  );
}

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
