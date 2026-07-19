import {
  CheckCircleOutlined,
  DatabaseOutlined,
  PlayCircleOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { WorkflowEditorNode } from "./workflowEditor";

const icons = {
  start: <PlayCircleOutlined />,
  ai_chat: <RobotOutlined />,
  knowledge_retrieval: <DatabaseOutlined />,
  end: <CheckCircleOutlined />,
};

export function WorkflowNodeCard({ id, data, selected }: NodeProps<WorkflowEditorNode>) {
  return (
    <>
      {data.nodeType !== "start" && (
        <Handle type="target" position={Position.Left} aria-label={`${data.label}输入连接点`} />
      )}
      <div className={`workflow-node-card${selected ? " is-selected" : ""}`}>
        <span className={`workflow-node-icon is-${data.nodeType}`}>{icons[data.nodeType]}</span>
        <span>
          <span className="workflow-node-title">{data.label}</span>
          <span className="workflow-node-id">{id}</span>
        </span>
      </div>
      {data.nodeType !== "end" && (
        <Handle type="source" position={Position.Right} aria-label={`${data.label}输出连接点`} />
      )}
    </>
  );
}
