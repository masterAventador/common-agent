import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Modal } from "antd";
import { useEffect, useReducer, useRef, useState } from "react";

import { getErrorMessage } from "../../api/errors";
import { fetchKnowledgeBases } from "../../api/knowledge";
import {
  createWorkflow,
  deleteWorkflow,
  fetchWorkflows,
  updateWorkflow,
  validateWorkflow,
  type Workflow,
  type WorkflowConfigurationInput,
  type WorkflowValidationResult,
} from "../../api/workflows";
import {
  createNewWorkflowEditorState,
  editorStateToConfiguration,
  workflowEditorReducer,
  type WorkflowEditorState,
} from "./workflowEditor";
import { isWorkflowRunActive, useWorkflowRun } from "./useWorkflowRun";

interface SaveRequest {
  workflowId: string | null;
  configuration: WorkflowConfigurationInput;
}

interface SaveResult {
  validation: WorkflowValidationResult;
  workflow?: Workflow;
}

export function useWorkflowDesigner() {
  const queryClient = useQueryClient();
  const initialized = useRef(false);
  const synchronizedRunId = useRef<string | undefined>(undefined);
  const [state, dispatch] = useReducer(
    workflowEditorReducer,
    undefined,
    createNewWorkflowEditorState,
  );
  const [localValidationMessage, setLocalValidationMessage] = useState<string>();
  const [deleteNotice, setDeleteNotice] = useState<string>();
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
    if (workflows.data[0]) dispatch({ type: "workflow_loaded", workflow: workflows.data[0] });
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

  const deleteMutation = useMutation({
    mutationFn: async (workflow: Workflow) => {
      setDeleteNotice(undefined);
      await deleteWorkflow(workflow.id);
      return workflow;
    },
    onSuccess: async (deleted) => {
      const current = queryClient.getQueryData<Workflow[]>(["workflows"]) ?? [];
      const remaining = current.filter((item) => item.id !== deleted.id);
      queryClient.setQueryData(["workflows"], remaining);
      runController.clear();
      if (state.workflowId === deleted.id) {
        const next = remaining[0];
        dispatch(next ? { type: "workflow_loaded", workflow: next } : { type: "new_workflow" });
      }
      setDeleteNotice(`工作流“${deleted.name}”已删除`);
      await queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
  });

  const selectWorkflow = (workflow: Workflow) => {
    const load = () => {
      saveMutation.reset();
      deleteMutation.reset();
      setDeleteNotice(undefined);
      setLocalValidationMessage(undefined);
      if (workflow.id !== state.workflowId) runController.clear();
      dispatch({ type: "workflow_loaded", workflow });
    };
    if (!state.dirty) return load();
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
      deleteMutation.reset();
      setDeleteNotice(undefined);
      setLocalValidationMessage(undefined);
      runController.clear();
      dispatch({ type: "new_workflow" });
    };
    if (!state.dirty) return reset();
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

  const deleteSelectedWorkflow = async () => {
    const selected = workflows.data?.find((workflow) => workflow.id === state.workflowId);
    if (!selected) return;
    await deleteMutation.mutateAsync(selected);
  };

  return {
    activeRun,
    createDraft,
    deleteMutation,
    deleteNotice,
    deleteSelectedWorkflow,
    dispatch,
    knowledgeBases,
    knowledgeError: knowledgeBases.isError ? getErrorMessage(knowledgeBases.error) : undefined,
    localValidationMessage,
    runController,
    save,
    saveMutation,
    selectWorkflow,
    state,
    visibleRun,
    workflows,
  };
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

export type WorkflowDesignerController = ReturnType<typeof useWorkflowDesigner>;
