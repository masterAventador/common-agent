import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  LoadingOutlined,
  PlayCircleOutlined,
  StopOutlined,
} from "@ant-design/icons";
import { Alert, Button, Flex, Input, Space, Tag, Typography } from "antd";
import type { ReactNode } from "react";

import { getErrorMessage } from "../../api/errors";
import type { WorkflowRun } from "../../api/workflowRuns";
import type { WorkflowEditorNode } from "./workflowEditor";
import {
  isWorkflowRunActive,
  type WorkflowRunController,
} from "./useWorkflowRun";

const { Text } = Typography;
const statusPresentation: Record<
  WorkflowRun["status"],
  { label: string; color: string; icon: ReactNode }
> = {
  pending: { label: "等待运行", color: "default", icon: <ClockCircleOutlined /> },
  running: { label: "运行中", color: "processing", icon: <LoadingOutlined spin /> },
  completed: { label: "运行完成", color: "success", icon: <CheckCircleOutlined /> },
  failed: { label: "运行失败", color: "error", icon: <CloseCircleOutlined /> },
  stopped: { label: "已停止", color: "default", icon: <StopOutlined /> },
};

export function WorkflowRunPanel({
  workflowId,
  dirty,
  nodes,
  controller,
}: {
  workflowId: string | null;
  dirty: boolean;
  nodes: WorkflowEditorNode[];
  controller: WorkflowRunController;
}) {
  const run =
    controller.run && controller.run.workflow_id === workflowId ? controller.run : undefined;
  const active = isWorkflowRunActive(run);
  const operationError = controller.restoreError ?? controller.startError ?? controller.stopError;

  return (
    <section className="workflow-run-panel" aria-label="手动运行面板">
      <div className="workflow-node-inspector-heading workflow-run-heading">
        <Text strong>手动运行</Text>
        {run && (
          <Tag color={statusPresentation[run.status].color} icon={statusPresentation[run.status].icon}>
            {statusPresentation[run.status].label}
          </Tag>
        )}
      </div>

      {(!workflowId || dirty) && (
        <Alert
          type="info"
          showIcon
          title="请先保存工作流，再从正式定义启动运行。"
          className="workflow-run-alert"
        />
      )}
      {operationError !== null && operationError !== undefined && (
        <Alert
          type="error"
          showIcon
          title="工作流运行操作失败"
          description={getErrorMessage(operationError)}
          className="workflow-run-alert"
        />
      )}
      {controller.streamNotice && (
        <Alert
          type="warning"
          showIcon
          title={controller.streamNotice}
          className="workflow-run-alert"
        />
      )}

      <label className="workflow-field">
        <Text>运行输入</Text>
        <Input.TextArea
          aria-label="工作流运行输入"
          value={controller.input}
          maxLength={200_000}
          rows={5}
          disabled={active}
          placeholder="输入要交给工作流处理的内容"
          onChange={(event) => controller.setInput(event.target.value)}
        />
      </label>
      <Flex justify="flex-end" className="workflow-run-actions">
        {active ? (
          <Button
            danger
            icon={<StopOutlined />}
            loading={controller.stopping}
            aria-label="停止工作流"
            onClick={controller.stop}
          >
            停止
          </Button>
        ) : (
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={controller.starting}
            disabled={!workflowId || dirty || !controller.input.trim()}
            aria-label="运行工作流"
            onClick={controller.start}
          >
            运行
          </Button>
        )}
      </Flex>

      {run && (
        <div className="workflow-run-summary" aria-live="polite">
          <Flex justify="space-between" align="center" gap={8}>
            <Text strong>节点进度</Text>
            <Text type="secondary" className="workflow-run-id">
              {run.id}
            </Text>
          </Flex>
          <div className="workflow-run-node-list">
            {nodes.map((node) => {
              const state = nodeRunState(run, node.id);
              return (
                <div key={node.id} className={`workflow-run-node is-${state}`}>
                  <span className="workflow-run-node-dot" aria-hidden="true" />
                  <Text>{node.data.label}</Text>
                  <Text type="secondary">{nodeStateLabel(state)}</Text>
                </div>
              );
            })}
          </div>
          {run.status === "completed" && (
            <div className="workflow-run-output">
              <Text strong>最终结果</Text>
              <pre>{run.output}</pre>
            </div>
          )}
          {run.status === "failed" && (
            <Alert
              type="error"
              showIcon
              title="运行失败"
              description={
                <Space orientation="vertical" size={2}>
                  <Text type="secondary">错误代码</Text>
                  <Text code>{run.error_code ?? "workflow_execution_failed"}</Text>
                </Space>
              }
            />
          )}
          {run.status === "stopped" && <Alert type="info" showIcon title="工作流已停止" />}
        </div>
      )}
    </section>
  );
}

function nodeRunState(
  run: WorkflowRun,
  nodeId: string,
): "waiting" | "active" | "completed" | "failed" {
  if (run.failed_node_id === nodeId) return "failed";
  if (run.current_node_id === nodeId && isWorkflowRunActive(run)) return "active";
  if (run.completed_node_ids.includes(nodeId)) return "completed";
  return "waiting";
}

function nodeStateLabel(state: ReturnType<typeof nodeRunState>): string {
  return {
    waiting: "等待",
    active: "执行中",
    completed: "完成",
    failed: "失败",
  }[state];
}
