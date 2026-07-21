import { Button, Card, Empty, Flex, Input, Select, Tag, Typography } from "antd";
import { Trash2 } from "lucide-react";
import { lazy, Suspense, type Dispatch, type UIEvent } from "react";

import type { WorkflowEditorAction, WorkflowEditorState } from "./workflowEditor";
import type { useWorkflowRun } from "./useWorkflowRun";

const { Text } = Typography;
const WorkflowRunPanel = lazy(async () => {
  const module = await import("./WorkflowRunPanel");
  return { default: module.WorkflowRunPanel };
});

export function WorkflowInspector({
  state,
  knowledgeBases,
  employees,
  models,
  targetLoading,
  targetError,
  onTargetPopupScroll,
  knowledgeLoading,
  knowledgeError,
  knowledgeSearch,
  onKnowledgeSearch,
  onKnowledgePopupScroll,
  editingLocked,
  readOnly = false,
  runController,
  dispatch,
}: {
  state: WorkflowEditorState;
  knowledgeBases: Array<{ id: string; name: string }>;
  employees: Array<{ id: string; name: string; default_model_identifier: string }>;
  models: Array<{ id: string; display_name: string; model_identifier: string }>;
  targetLoading: boolean;
  targetError?: string;
  onTargetPopupScroll: (event: UIEvent<HTMLDivElement>) => void;
  knowledgeLoading: boolean;
  knowledgeError?: string;
  knowledgeSearch: string;
  onKnowledgeSearch: (value: string) => void;
  onKnowledgePopupScroll: (event: UIEvent<HTMLDivElement>) => void;
  editingLocked: boolean;
  readOnly?: boolean;
  runController: ReturnType<typeof useWorkflowRun>;
  dispatch: Dispatch<WorkflowEditorAction>;
}) {
  const selected = state.nodes.find((node) => node.id === state.selectedNodeId);
  const selectedAiConfig =
    selected?.data.nodeType === "ai_chat" ? selected.data.config : undefined;

  return (
    <aside className="workflow-inspector" aria-label="工作流配置面板">
      <div className="workflow-panel-heading">
        <Text strong>工作流配置</Text>
        {state.workflowId ? <Tag color="blue">编辑</Tag> : <Tag color="green">新建</Tag>}
      </div>
      <label className="workflow-field">
        <Text>工作流名称</Text>
        <Input
          aria-label="工作流名称"
          value={state.name}
          maxLength={128}
          disabled={editingLocked}
          onChange={(event) =>
            dispatch({
              type: "metadata_changed",
              name: event.target.value,
              description: state.description,
            })
          }
        />
      </label>
      <label className="workflow-field">
        <Text>说明</Text>
        <Input.TextArea
          aria-label="工作流说明"
          value={state.description}
          maxLength={1_000}
          rows={3}
          disabled={editingLocked}
          onChange={(event) =>
            dispatch({
              type: "metadata_changed",
              name: state.name,
              description: event.target.value,
            })
          }
        />
      </label>

      <div className="workflow-node-inspector-heading">
        <Text strong>节点配置</Text>
      </div>
      {!selected ? (
        <Card size="small" className="workflow-inspector-empty">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择画布节点后编辑配置" />
        </Card>
      ) : (
        <div className="workflow-selected-node">
          <Flex justify="space-between" align="center" gap={8}>
            <div>
              <Text strong>{selected.data.label}</Text>
              <Text type="secondary" className="workflow-selected-node-id">
                {selected.id}
              </Text>
            </div>
            <Button
              danger
              type="text"
              icon={<Trash2 aria-hidden="true" size={15} />}
              aria-label={`删除节点 ${selected.data.label} ${selected.id}`}
              disabled={editingLocked}
              onClick={() =>
                dispatch({
                  type: "nodes_changed",
                  changes: [{ id: selected.id, type: "remove" }],
                })
              }
            >
              删除
            </Button>
          </Flex>

          {selectedAiConfig && (
            <>
              <label className="workflow-field">
                <Text>执行目标</Text>
                <Select
                  aria-label="AI 对话执行目标"
                  value={targetValue(selectedAiConfig.target)}
                  loading={targetLoading}
                  disabled={editingLocked || Boolean(targetError)}
                  placeholder={targetError ? "执行目标暂时不可用" : "选择数字员工或模型"}
                  showSearch
                  optionFilterProp="label"
                  options={[
                    {
                      label: "数字员工",
                      options: employees.map((item) => ({
                        value: `employee:${item.id}`,
                        label: `${item.name} · ${item.default_model_identifier}`,
                      })),
                    },
                    {
                      label: "已启用模型",
                      options: models.map((item) => ({
                        value: `model:${item.id}`,
                        label: `${item.display_name} · ${item.model_identifier}`,
                      })),
                    },
                  ]}
                  onPopupScroll={onTargetPopupScroll}
                  onChange={(value: string) =>
                    dispatch({
                      type: "node_config_changed",
                      nodeId: selected.id,
                      config: {
                        prompt: selectedAiConfig.prompt,
                        target: workflowTarget(value),
                      },
                    })
                  }
                />
                {targetError && <Text type="danger">{targetError}</Text>}
                <Text type="secondary">
                  数字员工会在运行时继承其当前提示词、知识库、授权工作流和默认模型。
                </Text>
              </label>
              <label className="workflow-field">
                <Text>节点提示词</Text>
                <Input.TextArea
                  aria-label="节点提示词"
                  value={selectedAiConfig.prompt}
                  maxLength={12_000}
                  rows={8}
                  disabled={editingLocked}
                  onChange={(event) =>
                    dispatch({
                      type: "node_config_changed",
                      nodeId: selected.id,
                      config: {
                        prompt: event.target.value,
                        target: selectedAiConfig.target,
                      },
                    })
                  }
                />
              </label>
            </>
          )}
          {selected.data.nodeType === "knowledge_retrieval" && (
            <label className="workflow-field">
              <Text>知识库</Text>
              <Select
                aria-label="节点知识库"
                value={selected.data.config.knowledge_base_id || undefined}
                loading={knowledgeLoading}
                disabled={editingLocked || Boolean(knowledgeError)}
                placeholder={knowledgeError ? "知识库暂时不可用" : "选择知识库"}
                showSearch
                filterOption={false}
                searchValue={knowledgeSearch}
                options={knowledgeBases.map((item) => ({ value: item.id, label: item.name }))}
                onSearch={onKnowledgeSearch}
                onPopupScroll={onKnowledgePopupScroll}
                onChange={(value) =>
                  dispatch({
                    type: "node_config_changed",
                    nodeId: selected.id,
                    config: { knowledge_base_id: value },
                  })
                }
              />
              {knowledgeError && <Text type="danger">{knowledgeError}</Text>}
            </label>
          )}
          {selected.data.nodeType === "start" && (
            <Text type="secondary">开始节点没有业务配置，只允许连接到下一个节点。</Text>
          )}
          {selected.data.nodeType === "end" && (
            <Text type="secondary">结束节点接收上游结果，不允许再连接后续节点。</Text>
          )}
        </div>
      )}
      <Suspense fallback={<Text type="secondary">正在加载运行面板…</Text>}>
        <WorkflowRunPanel
          workflowId={state.workflowId}
          dirty={state.dirty}
          nodes={state.nodes}
          controller={runController}
          readOnly={readOnly}
        />
      </Suspense>
    </aside>
  );
}

function targetValue(
  target: Extract<WorkflowEditorState["nodes"][number]["data"], { nodeType: "ai_chat" }>[
    "config"
  ]["target"],
): string | undefined {
  if (target === null) return undefined;
  return target.type === "employee"
    ? `employee:${target.employee_id}`
    : `model:${target.model_configuration_id}`;
}

function workflowTarget(value: string) {
  const [type, id] = value.split(":", 2);
  if (type === "employee") return { type, employee_id: id } as const;
  return { type: "model", model_configuration_id: id } as const;
}
