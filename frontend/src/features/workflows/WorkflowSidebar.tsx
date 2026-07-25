import { Typography } from "antd";
import { Bot, CircleCheckBig, CirclePlay, Database } from "lucide-react";
import type { Dispatch, DragEvent, ReactNode } from "react";

import type { WorkflowNodeType } from "../../api/workflows";
import {
  WORKFLOW_NODE_LABELS,
  type WorkflowEditorAction,
  type WorkflowEditorState,
} from "./workflowEditor";
import { WORKFLOW_NODE_MIME } from "./workflowDnd";

const palette = [
  { type: "start" as const, icon: <CirclePlay aria-hidden="true" size={17} />, description: "流程唯一入口" },
  { type: "ai_chat" as const, icon: <Bot aria-hidden="true" size={17} />, description: "调用模型生成文本" },
  {
    type: "knowledge_retrieval" as const,
    icon: <Database aria-hidden="true" size={17} />,
    description: "检索指定知识库",
  },
  { type: "end" as const, icon: <CircleCheckBig aria-hidden="true" size={17} />, description: "收敛最终结果" },
] satisfies Array<{ type: WorkflowNodeType; icon: ReactNode; description: string }>;
const { Text } = Typography;

export function WorkflowSidebar({
  state,
  editingLocked,
  dispatch,
}: {
  state: WorkflowEditorState;
  editingLocked: boolean;
  dispatch: Dispatch<WorkflowEditorAction>;
}) {
  return (
    <aside className="workflow-sidebar" aria-label="工作流节点面板">
      <div className="workflow-panel-heading">
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
