import {
  ApartmentOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  PlusOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Connection,
  type NodeTypes,
} from "@xyflow/react";
import {
  Alert,
  Button,
  Card,
  Empty,
  Flex,
  Input,
  Modal,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";
import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  type Dispatch,
  type DragEvent,
  type ReactNode,
} from "react";

import {
  createWorkflow,
  fetchWorkflows,
  updateWorkflow,
  validateWorkflow,
  type Workflow,
  type WorkflowConfigurationInput,
  type WorkflowNodeType,
  type WorkflowValidationResult,
} from "../../api/workflows";
import { getErrorMessage } from "../../api/errors";
import { fetchKnowledgeBases } from "../../api/knowledge";
import type { WorkflowRun } from "../../api/workflowRuns";
import { WorkflowNodeCard } from "./WorkflowNodeCard";
import { WorkflowRunPanel } from "./WorkflowRunPanel";
import {
  WORKFLOW_NODE_LABELS,
  createNewWorkflowEditorState,
  editorStateToConfiguration,
  workflowEditorReducer,
  type WorkflowEditorAction,
  type WorkflowEditorEdge,
  type WorkflowEditorState,
} from "./workflowEditor";
import { isWorkflowRunActive, useWorkflowRun } from "./useWorkflowRun";

const { Paragraph, Text, Title } = Typography;
const WORKFLOW_NODE_MIME = "application/common-agent-workflow-node";
const nodeTypes: NodeTypes = { workflowNode: WorkflowNodeCard };
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

interface SaveRequest {
  workflowId: string | null;
  configuration: WorkflowConfigurationInput;
}

interface SaveResult {
  validation: WorkflowValidationResult;
  workflow?: Workflow;
}

export function WorkflowsPage() {
  const queryClient = useQueryClient();
  const initialized = useRef(false);
  const synchronizedRunId = useRef<string | undefined>(undefined);
  const [state, dispatch] = useReducer(
    workflowEditorReducer,
    undefined,
    createNewWorkflowEditorState,
  );
  const [localValidationMessage, setLocalValidationMessage] = useState<string>();
  const runController = useWorkflowRun(state.workflowId, state.dirty);
  const activeRun = isWorkflowRunActive(runController.run);
  const visibleRun =
    runController.run?.workflow_id === state.workflowId ? runController.run : undefined;

  const workflows = useQuery({ queryKey: ["workflows"], queryFn: fetchWorkflows });
  const knowledgeBases = useQuery({
    queryKey: ["knowledge-bases"],
    queryFn: fetchKnowledgeBases,
  });

  useEffect(() => {
    if (initialized.current || !workflows.data) return;
    initialized.current = true;
    if (workflows.data[0]) {
      dispatch({ type: "workflow_loaded", workflow: workflows.data[0] });
    }
  }, [workflows.data]);

  useEffect(() => {
    const restoredRun = runController.run;
    if (
      !restoredRun ||
      !workflows.data ||
      state.dirty ||
      synchronizedRunId.current === restoredRun.id
    ) {
      return;
    }
    synchronizedRunId.current = restoredRun.id;
    if (state.workflowId === restoredRun.workflow_id) return;
    const workflow = workflows.data.find((item) => item.id === restoredRun.workflow_id);
    if (workflow) dispatch({ type: "workflow_loaded", workflow });
  }, [runController.run, state.dirty, state.workflowId, workflows.data]);

  const saveMutation = useMutation({
    mutationFn: async ({ workflowId, configuration }: SaveRequest): Promise<SaveResult> => {
      const validation = await validateWorkflow(configuration);
      if (!validation.valid) return { validation };
      const workflow = workflowId
        ? await updateWorkflow(workflowId, configuration)
        : await createWorkflow(configuration);
      return { validation, workflow };
    },
    onSuccess: async (result) => {
      dispatch({ type: "validation_received", issues: result.validation.issues });
      if (!result.workflow) return;
      dispatch({ type: "saved", workflow: result.workflow });
      await queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
  });

  const selectWorkflow = (workflow: Workflow) => {
    const load = () => {
      saveMutation.reset();
      setLocalValidationMessage(undefined);
      if (workflow.id !== state.workflowId) runController.clear();
      dispatch({ type: "workflow_loaded", workflow });
    };
    if (!state.dirty) {
      load();
      return;
    }
    Modal.confirm({
      title: "放弃未保存修改？",
      content: "切换工作流会丢弃当前草稿中的修改。",
      okText: "放弃并切换",
      cancelText: "继续编辑",
      onOk: load,
    });
  };

  const createDraft = () => {
    const reset = () => {
      saveMutation.reset();
      setLocalValidationMessage(undefined);
      runController.clear();
      dispatch({ type: "new_workflow" });
    };
    if (!state.dirty) {
      reset();
      return;
    }
    Modal.confirm({
      title: "放弃未保存修改？",
      content: "新建工作流会丢弃当前草稿中的修改。",
      okText: "放弃并新建",
      cancelText: "继续编辑",
      onOk: reset,
    });
  };

  const save = () => {
    saveMutation.reset();
    const localIssue = validateDraftLocally(state);
    setLocalValidationMessage(localIssue);
    if (localIssue) return;
    saveMutation.mutate({
      workflowId: state.workflowId,
      configuration: editorStateToConfiguration(state),
    });
  };

  if (workflows.isPending) {
    return (
      <section className="workflows-page" aria-label="工作流加载中">
        <Skeleton active paragraph={{ rows: 12 }} />
      </section>
    );
  }

  if (workflows.isError) {
    return (
      <section className="workflows-page">
        <Alert
          type="error"
          showIcon
          title="工作流加载失败"
          description={getErrorMessage(workflows.error)}
          action={
            <Button
              icon={<ReloadOutlined />}
              aria-label="重试加载工作流"
              onClick={() => void workflows.refetch()}
            >
              重试
            </Button>
          }
        />
      </section>
    );
  }

  return (
    <section className="workflows-page">
      <Flex justify="space-between" align="flex-start" gap={24} className="workflows-heading">
        <div>
          <Space align="center">
            <ApartmentOutlined className="workflows-title-icon" />
            <Title level={2}>工作流</Title>
            {state.dirty ? <Tag color="gold">有未保存修改</Tag> : <Tag>已保存</Tag>}
          </Space>
          <Paragraph type="secondary">
            拖入节点并通过连接点编排流程，保存前由服务端执行最终校验。
          </Paragraph>
        </div>
        <Space>
          <Button
            icon={<PlusOutlined />}
            aria-label="新建工作流"
            disabled={activeRun}
            onClick={createDraft}
          >
            新建工作流
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            aria-label="保存工作流"
            loading={saveMutation.isPending}
            disabled={activeRun}
            onClick={save}
          >
            校验并保存
          </Button>
        </Space>
      </Flex>

      {(localValidationMessage || saveMutation.isError) && (
        <Alert
          type="error"
          showIcon
          title="工作流保存失败"
          description={
            localValidationMessage ?? getErrorMessage(saveMutation.error ?? new Error("保存失败"))
          }
          className="workflows-alert"
        />
      )}
      {state.validationIssues.length > 0 && (
        <Alert
          type="warning"
          showIcon
          title="服务端校验未通过"
          description={
            <ul className="workflow-issue-list">
              {state.validationIssues.map((issue, index) => (
                <li key={`${issue.code}-${issue.node_id}-${issue.edge_id}-${index}`}>
                  {issue.message}
                  {issue.node_id && (
                    <Button
                      type="link"
                      size="small"
                      onClick={() => dispatch({ type: "node_selected", nodeId: issue.node_id })}
                    >
                      定位节点 {issue.node_id}
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          }
          className="workflows-alert"
        />
      )}

      <div className="workflow-designer">
        <aside className="workflow-sidebar" aria-label="工作流与节点面板">
          <div className="workflow-panel-heading">
            <Text strong>工作流列表</Text>
            <Text type="secondary">{workflows.data.length} 个</Text>
          </div>
          <div className="workflow-list">
            {workflows.data.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有已保存工作流" />
            ) : (
              workflows.data.map((workflow) => (
                <button
                  type="button"
                  key={workflow.id}
                  className={`workflow-list-item${state.workflowId === workflow.id ? " is-active" : ""}`}
                  aria-label={`选择工作流 ${workflow.name}`}
                  disabled={activeRun && state.workflowId !== workflow.id}
                  onClick={() => selectWorkflow(workflow)}
                >
                  <Text strong>{workflow.name}</Text>
                  <Text type="secondary">
                    {workflow.nodes.length} 个节点 · {workflow.edges.length} 条连线
                  </Text>
                </button>
              ))
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
                draggable={!activeRun}
                disabled={activeRun}
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

        <ReactFlowProvider>
          <WorkflowCanvas
            state={state}
            run={visibleRun}
            editingLocked={activeRun}
            dispatch={dispatch}
          />
        </ReactFlowProvider>

        <WorkflowInspector
          state={state}
          knowledgeBases={knowledgeBases.data ?? []}
          knowledgeLoading={knowledgeBases.isPending}
          knowledgeError={knowledgeBases.isError ? getErrorMessage(knowledgeBases.error) : undefined}
          editingLocked={activeRun}
          runController={runController}
          dispatch={dispatch}
        />
      </div>
    </section>
  );
}

function WorkflowCanvas({
  state,
  run,
  editingLocked,
  dispatch,
}: {
  state: WorkflowEditorState;
  run?: WorkflowRun;
  editingLocked: boolean;
  dispatch: Dispatch<WorkflowEditorAction>;
}) {
  const flow = useReactFlow();
  const renderedNodes = useMemo(
    () =>
      state.nodes.map((node) => ({
        ...node,
        className: [
          node.className,
          state.invalidNodeIds.has(node.id) ? "is-invalid" : undefined,
          workflowNodeRunClass(run, node.id),
        ]
          .filter(Boolean)
          .join(" "),
      })),
    [run, state.invalidNodeIds, state.nodes],
  );
  const renderedEdges = useMemo(
    () =>
      state.edges.map((edge) => ({
        ...edge,
        className: state.invalidEdgeIds.has(edge.id) ? "is-invalid" : edge.className,
      })),
    [state.edges, state.invalidEdgeIds],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (editingLocked || !connection.source || !connection.target) return;
      dispatch({
        type: "nodes_connected",
        source: connection.source,
        target: connection.target,
      });
    },
    [dispatch, editingLocked],
  );

  const isValidConnection = useCallback(
    (connection: Connection | WorkflowEditorEdge) => {
      if (editingLocked) return false;
      if (!connection.source || !connection.target || connection.source === connection.target) {
        return false;
      }
      const source = state.nodes.find((node) => node.id === connection.source);
      const target = state.nodes.find((node) => node.id === connection.target);
      if (!source || !target || source.data.nodeType === "end" || target.data.nodeType === "start") {
        return false;
      }
      return (
        !state.edges.some((edge) => edge.source === connection.source) &&
        !state.edges.some(
          (edge) => edge.source === connection.source && edge.target === connection.target,
        )
      );
    },
    [editingLocked, state.edges, state.nodes],
  );

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      if (editingLocked) return;
      const nodeType = event.dataTransfer.getData(WORKFLOW_NODE_MIME);
      if (!isWorkflowNodeType(nodeType)) return;
      dispatch({
        type: "node_added",
        nodeType,
        position: flow.screenToFlowPosition({ x: event.clientX, y: event.clientY }),
      });
    },
    [dispatch, editingLocked, flow],
  );

  return (
    <section
      className="workflow-canvas"
      role="region"
      aria-label="工作流画布"
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
      }}
      onDrop={onDrop}
    >
      <ReactFlow
        nodes={renderedNodes}
        edges={renderedEdges}
        nodeTypes={nodeTypes}
        onNodesChange={(changes) => dispatch({ type: "nodes_changed", changes })}
        onEdgesChange={(changes) => dispatch({ type: "edges_changed", changes })}
        onConnect={onConnect}
        onNodeClick={(_, node) => dispatch({ type: "node_selected", nodeId: node.id })}
        onPaneClick={() => dispatch({ type: "node_selected", nodeId: null })}
        isValidConnection={isValidConnection}
        nodesDraggable={!editingLocked}
        nodesConnectable={!editingLocked}
        defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed }, type: "smoothstep" }}
        deleteKeyCode={editingLocked ? null : ["Backspace", "Delete"]}
        fitView
        fitViewOptions={{ maxZoom: 1 }}
        minZoom={0.35}
        maxZoom={1.8}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} />
        <MiniMap pannable zoomable />
        <Controls showInteractive={false} />
      </ReactFlow>
    </section>
  );
}

function WorkflowInspector({
  state,
  knowledgeBases,
  knowledgeLoading,
  knowledgeError,
  editingLocked,
  runController,
  dispatch,
}: {
  state: WorkflowEditorState;
  knowledgeBases: Array<{ id: string; name: string }>;
  knowledgeLoading: boolean;
  knowledgeError?: string;
  editingLocked: boolean;
  runController: ReturnType<typeof useWorkflowRun>;
  dispatch: Dispatch<WorkflowEditorAction>;
}) {
  const selected = state.nodes.find((node) => node.id === state.selectedNodeId);

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
              icon={<DeleteOutlined />}
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

          {selected.data.nodeType === "ai_chat" && (
            <label className="workflow-field">
              <Text>节点提示词</Text>
              <Input.TextArea
                aria-label="节点提示词"
                value={selected.data.config.prompt}
                maxLength={12_000}
                rows={8}
                disabled={editingLocked}
                onChange={(event) =>
                  dispatch({
                    type: "node_config_changed",
                    nodeId: selected.id,
                    config: { prompt: event.target.value },
                  })
                }
              />
            </label>
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
                options={knowledgeBases.map((item) => ({ value: item.id, label: item.name }))}
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
      <WorkflowRunPanel
        workflowId={state.workflowId}
        dirty={state.dirty}
        nodes={state.nodes}
        controller={runController}
      />
    </aside>
  );
}

function workflowNodeRunClass(run: WorkflowRun | undefined, nodeId: string): string | undefined {
  if (!run) return undefined;
  if (run.failed_node_id === nodeId) return "is-run-failed";
  if (run.current_node_id === nodeId && isWorkflowRunActive(run)) return "is-run-active";
  if (run.completed_node_ids.includes(nodeId)) return "is-run-completed";
  return undefined;
}

function beginNodeDrag(event: DragEvent<HTMLButtonElement>, nodeType: WorkflowNodeType) {
  event.dataTransfer.setData(WORKFLOW_NODE_MIME, nodeType);
  event.dataTransfer.effectAllowed = "move";
}

function isWorkflowNodeType(value: string): value is WorkflowNodeType {
  return ["start", "ai_chat", "knowledge_retrieval", "end"].includes(value);
}

function validateDraftLocally(state: WorkflowEditorState): string | undefined {
  if (!state.name.trim()) return "请输入工作流名称";
  for (const node of state.nodes) {
    if (node.data.nodeType === "ai_chat" && !node.data.config.prompt.trim()) {
      return `请填写 AI 对话节点 ${node.id} 的提示词`;
    }
    if (
      node.data.nodeType === "knowledge_retrieval" &&
      !node.data.config.knowledge_base_id.trim()
    ) {
      return `请选择知识检索节点 ${node.id} 使用的知识库`;
    }
  }
  return undefined;
}
