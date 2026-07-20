import {
  CheckCircleOutlined,
  DatabaseOutlined,
  PlayCircleOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import { Button, Empty, Input, Typography } from "antd";
import type { Dispatch, DragEvent, ReactNode } from "react";

import type { Workflow, WorkflowNodeType } from "../../api/workflows";
import {
  WORKFLOW_NODE_LABELS,
  type WorkflowEditorAction,
  type WorkflowEditorState,
} from "./workflowEditor";
import { WORKFLOW_NODE_MIME } from "./workflowDnd";

const palette = [
  { type: "start" as const, icon: <PlayCircleOutlined />, description: "流程唯一入口" },
  { type: "ai_chat" as const, icon: <RobotOutlined />, description: "调用模型生成文本" },
  {
    type: "knowledge_retrieval" as const,
    icon: <DatabaseOutlined />,
    description: "检索指定知识库",
  },
  { type: "end" as const, icon: <CheckCircleOutlined />, description: "收敛最终结果" },
] satisfies Array<{ type: WorkflowNodeType; icon: ReactNode; description: string }>;
const { Text } = Typography;

export function WorkflowSidebar({
  workflows,
  state,
  editingLocked,
  search,
  onSearch,
  hasMore,
  loadingMore,
  onLoadMore,
  onSelectWorkflow,
  dispatch,
}: {
  workflows: Workflow[];
  state: WorkflowEditorState;
  editingLocked: boolean;
  search: string;
  onSearch: (value: string) => void;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  onSelectWorkflow: (workflow: Workflow) => void;
  dispatch: Dispatch<WorkflowEditorAction>;
}) {
  return (
    <aside className="workflow-sidebar" aria-label="工作流与节点面板">
      <div className="workflow-panel-heading">
        <Text strong>工作流列表</Text>
        <Text type="secondary">{workflows.length} 个</Text>
      </div>
      <Input.Search
        aria-label="搜索工作流"
        allowClear
        value={search}
        placeholder="搜索工作流"
        onChange={(event) => onSearch(event.target.value)}
      />
      <div className="workflow-list">
        {workflows.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有已保存工作流" />
        ) : (
          workflows.map((workflow) => (
            <button
              type="button"
              key={workflow.id}
              className={`workflow-list-item${state.workflowId === workflow.id ? " is-active" : ""}`}
              aria-label={`选择工作流 ${workflow.name}`}
              disabled={editingLocked && state.workflowId !== workflow.id}
              onClick={() => onSelectWorkflow(workflow)}
            >
              <Text strong>{workflow.name}</Text>
              <Text type="secondary">
                {workflow.nodes.length} 个节点 · {workflow.edges.length} 条连线
              </Text>
            </button>
          ))
        )}
        {hasMore && (
          <Button block loading={loadingMore} onClick={onLoadMore}>
            加载更多工作流
          </Button>
        )}
      </div>

      <div className="workflow-panel-heading workflow-node-panel-heading">
        <Text strong>节点面板</Text>
        <Text type="secondary">拖入或点击添加</Text>
      </div>
      <div className="workflow-palette">
        {palette.map((item, index) => (
          <button
            type="button"
            draggable={!editingLocked}
            disabled={editingLocked}
            key={item.type}
            className="workflow-palette-item"
            aria-label={`添加${WORKFLOW_NODE_LABELS[item.type]}节点`}
            onDragStart={(event) => beginNodeDrag(event, item.type)}
            onClick={() =>
              dispatch({
                type: "node_added",
                nodeType: item.type,
                position: { x: 80 + (index % 2) * 220, y: 80 + state.nodes.length * 36 },
              })
            }
          >
            <span className={`workflow-palette-icon is-${item.type}`}>{item.icon}</span>
            <span>
              <Text strong>{WORKFLOW_NODE_LABELS[item.type]}</Text>
              <Text type="secondary">{item.description}</Text>
            </span>
          </button>
        ))}
      </div>

      <div className="workflow-panel-heading workflow-node-list-heading">
        <Text strong>画布节点</Text>
        <Text type="secondary">{state.nodes.length} 个</Text>
      </div>
      <div className="workflow-canvas-node-list" aria-label="画布节点列表">
        {state.nodes.length === 0 ? (
          <Text type="secondary">从上方添加节点后可在这里用键盘选择。</Text>
        ) : (
          state.nodes.map((node) => (
            <button
              type="button"
              key={node.id}
              className={`workflow-canvas-node-item${state.selectedNodeId === node.id ? " is-active" : ""}`}
              aria-label={`选择节点 ${node.data.label} ${node.id}`}
              onClick={() => dispatch({ type: "node_selected", nodeId: node.id })}
            >
              <Text>{node.data.label}</Text>
              <Text type="secondary">{node.id}</Text>
            </button>
          ))
        )}
      </div>
    </aside>
  );
}

function beginNodeDrag(event: DragEvent<HTMLButtonElement>, nodeType: WorkflowNodeType) {
  event.dataTransfer.setData(WORKFLOW_NODE_MIME, nodeType);
  event.dataTransfer.effectAllowed = "move";
}
