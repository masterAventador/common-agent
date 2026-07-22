import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  createConversationTurn,
  fetchConversation,
  fetchConversationMessages,
  retryConversationMessage,
  sendConversationMessage,
  stopConversationGeneration,
  subscribeToConversationEvents,
  type ConversationEvent,
  type ConversationMessage,
} from "../../api/conversations";
import { fetchEmployee, fetchEmployees } from "../../api/employees";
import {
  fetchModelConfiguration,
  fetchModelConfigurations,
} from "../../api/modelConfigurations";
import { flattenCursorPages, nextPageCursor } from "../../api/pagination";
import {
  fetchConversationToolGrants,
  fetchEmployeeToolGrants,
  fetchToolCatalog,
  replaceConversationToolGrants,
  type ToolGrantSelection,
} from "../../api/tools";
import { fetchConversationWorkflowRuns } from "../../api/workflowRuns";
import { fetchWorkflows } from "../../api/workflows";
import { explicitToolGrantSelection } from "../tools/index";
import { groupWorkflowRunsByMessage, mergeAcceptedTurn, replaceMessage } from "./chatState";

export const GENERIC_CHAT_VALUE = "__generic__";
const EMPTY_TOOL_SELECTION: ToolGrantSelection = {
  collection_ids: [],
  capability_ids: [],
};

export type ChatToolCallLifecycle = {
  toolCallId: string;
  capabilityId: string;
  capabilityName: string;
  status: "running" | "completed" | "failed";
  errorCode: string | null;
};

export function useChatPageController() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [draft, setDraft] = useState("");
  const [streamNotice, setStreamNotice] = useState<string>();
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [selectedModelConfigurationId, setSelectedModelConfigurationId] = useState("");
  const [toolSelectionOverride, setToolSelectionOverride] = useState<{
    contextKey: string;
    selection: ToolGrantSelection;
  }>();
  const [toolCallState, setToolCallState] = useState<{
    conversationId: string;
    callsByMessageId: Map<string, ChatToolCallLifecycle[]>;
  }>();
  const modelContextRef = useRef("");
  const lastEventSequence = useRef(0);
  const requestedEmployeeId = searchParams.get("employee_id");
  const requestedConversationId = searchParams.get("conversation_id");

  const employees = useInfiniteQuery({
    queryKey: ["employees", employeeSearch],
    queryFn: ({ pageParam }) =>
      fetchEmployees({ search: employeeSearch, limit: 50, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageCursor,
    placeholderData: keepPreviousData,
  });
  const listedEmployeeItems = useMemo(() => flattenCursorPages(employees.data), [employees.data]);
  const selectedConversationQuery = useQuery({
    queryKey: ["conversation", requestedConversationId],
    queryFn: () => fetchConversation(requestedConversationId ?? ""),
    enabled: Boolean(requestedConversationId),
  });
  const selectedConversation = selectedConversationQuery.data;
  const selectedEmployeeId = selectedConversation
    ? (selectedConversation.employee_id ?? undefined)
    : (requestedEmployeeId ?? undefined);
  const selectedEmployeeQuery = useQuery({
    queryKey: ["employee", selectedEmployeeId],
    queryFn: () => fetchEmployee(selectedEmployeeId ?? ""),
    enabled: Boolean(selectedEmployeeId),
  });
  const selectedEmployee = selectedEmployeeQuery.data;
  const employeeItems = useMemo(
    () =>
      selectedEmployee && !listedEmployeeItems.some((employee) => employee.id === selectedEmployee.id)
        ? [selectedEmployee, ...listedEmployeeItems]
        : listedEmployeeItems,
    [listedEmployeeItems, selectedEmployee],
  );
  const contextKey = selectedEmployeeId ? `employee:${selectedEmployeeId}` : "generic";
  const defaultModelConfigurationId =
    selectedConversation?.source === "generic"
      ? selectedConversation.model_configuration_id
      : selectedEmployee?.default_model_configuration_id;
  const modelConfigurations = useInfiniteQuery({
    queryKey: ["model-configurations", "chat"],
    queryFn: ({ pageParam }) =>
      fetchModelConfigurations({ limit: 100, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageCursor,
  });
  const allModelConfigurationItems = useMemo(
    () => flattenCursorPages(modelConfigurations.data),
    [modelConfigurations.data],
  );
  const contextModelConfiguration = useQuery({
    queryKey: ["model-configuration", defaultModelConfigurationId],
    queryFn: () => fetchModelConfiguration(defaultModelConfigurationId ?? ""),
    enabled: Boolean(defaultModelConfigurationId),
  });
  const modelConfigurationItems = useMemo(
    () => {
      const exact = contextModelConfiguration.data;
      const available = exact
        ? [exact, ...allModelConfigurationItems.filter((item) => item.id !== exact.id)]
        : allModelConfigurationItems;
      return available.filter(
        (configuration) =>
          configuration.enabled ||
          configuration.id === selectedEmployee?.default_model_configuration_id,
      );
    },
    [
      allModelConfigurationItems,
      contextModelConfiguration.data,
      selectedEmployee?.default_model_configuration_id,
    ],
  );
  const selectedConversationId = requestedConversationId ?? undefined;
  const messages = useQuery({
    queryKey: ["conversation-messages", selectedConversationId],
    queryFn: () => fetchConversationMessages(selectedConversationId ?? ""),
    enabled: Boolean(selectedConversationId),
  });
  const activeMessage = messages.data?.find(
    (message) =>
      message.role === "assistant" && ["pending", "streaming"].includes(message.status),
  );
  const isEmployeeConversation = selectedConversation?.source === "employee";
  const workflowRuns = useInfiniteQuery({
    queryKey: ["conversation-workflow-runs", selectedConversationId],
    queryFn: ({ pageParam }) =>
      fetchConversationWorkflowRuns(selectedConversationId ?? "", {
        limit: 50,
        cursor: pageParam,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageCursor,
    enabled: Boolean(selectedConversationId && isEmployeeConversation),
    refetchInterval: activeMessage && isEmployeeConversation ? 1_000 : false,
  });
  const workflowRunItems = useMemo(
    () => flattenCursorPages(workflowRuns.data),
    [workflowRuns.data],
  );
  const workflows = useInfiniteQuery({
    queryKey: ["workflows"],
    queryFn: ({ pageParam }) => fetchWorkflows({ limit: 100, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageCursor,
    enabled: isEmployeeConversation && workflowRunItems.length > 0,
  });
  const workflowItems = useMemo(() => flattenCursorPages(workflows.data), [workflows.data]);
  const workflowsById = useMemo(
    () => new Map(workflowItems.map((workflow) => [workflow.id, workflow])),
    [workflowItems],
  );
  const runsByMessageId = useMemo(
    () => groupWorkflowRunsByMessage(workflowRunItems),
    [workflowRunItems],
  );
  const toolCatalog = useQuery({
    queryKey: ["tool-catalog"],
    queryFn: fetchToolCatalog,
  });
  const conversationToolGrants = useQuery({
    queryKey: ["conversation-tool-grants", selectedConversationId],
    queryFn: () => fetchConversationToolGrants(selectedConversationId ?? ""),
    enabled: Boolean(selectedConversationId && selectedConversation?.source === "generic"),
  });
  const employeeToolGrants = useQuery({
    queryKey: ["employee-tool-grants", selectedEmployeeId],
    queryFn: () => fetchEmployeeToolGrants(selectedEmployeeId ?? ""),
    enabled: Boolean(selectedEmployeeId),
  });
  const toolCapabilityNames = useMemo(
    () =>
      new Map(
        (toolCatalog.data?.capabilities ?? []).map((capability) => [
          capability.id,
          capability.display_name,
        ]),
      ),
    [toolCatalog.data],
  );
  const toolSelectionContextKey = selectedConversationId
    ? `conversation:${selectedConversationId}`
    : selectedEmployeeId
      ? `employee:${selectedEmployeeId}`
      : "generic:new";
  const persistedToolSelection =
    selectedConversationId &&
    selectedConversation?.source === "generic" &&
    toolCatalog.data &&
    conversationToolGrants.data
      ? explicitToolGrantSelection(toolCatalog.data, conversationToolGrants.data)
      : EMPTY_TOOL_SELECTION;
  const toolSelection =
    toolSelectionOverride?.contextKey === toolSelectionContextKey
      ? toolSelectionOverride.selection
      : persistedToolSelection;
  const toolCallsByMessageId =
    toolCallState && toolCallState.conversationId === selectedConversationId
      ? toolCallState.callsByMessageId
      : new Map<string, ChatToolCallLifecycle[]>();

  const modelContextKey = `${contextKey}:${requestedConversationId ?? "new"}:${
    defaultModelConfigurationId ?? "first"
  }`;
  useEffect(() => {
    if (
      !modelConfigurationItems.length ||
      modelContextRef.current === modelContextKey ||
      (defaultModelConfigurationId && contextModelConfiguration.isPending)
    ) {
      return;
    }
    const availableDefault = modelConfigurationItems.some(
      (item) => item.id === defaultModelConfigurationId,
    );
    setSelectedModelConfigurationId(
      availableDefault && defaultModelConfigurationId
        ? defaultModelConfigurationId
        : modelConfigurationItems[0].id,
    );
    modelContextRef.current = modelContextKey;
  }, [
    contextModelConfiguration.isPending,
    defaultModelConfigurationId,
    modelConfigurationItems,
    modelContextKey,
  ]);

  useEffect(() => {
    if (!selectedConversationId) return;
    lastEventSequence.current = 0;
    const subscription = subscribeToConversationEvents(selectedConversationId, {
      afterSequence: 0,
      onEvent: (event: ConversationEvent) => {
        if (event.sequence <= lastEventSequence.current) return;
        lastEventSequence.current = event.sequence;
        const toolCall = event.tool_call;
        if (toolCall) {
          const status = toolCallStatus(event.type);
          if (status) {
            setToolCallState((current) => {
              const next = new Map(
                current?.conversationId === selectedConversationId
                  ? current.callsByMessageId
                  : undefined,
              );
              const existing = next.get(event.message_id) ?? [];
              const lifecycle: ChatToolCallLifecycle = {
                toolCallId: toolCall.tool_call_id,
                capabilityId: toolCall.capability_id,
                capabilityName: toolCall.capability_name,
                status,
                errorCode: toolCall.error_code,
              };
              const index = existing.findIndex(
                (item) => item.toolCallId === lifecycle.toolCallId,
              );
              next.set(
                event.message_id,
                index === -1
                  ? [...existing, lifecycle]
                  : existing.map((item, itemIndex) =>
                      itemIndex === index ? lifecycle : item,
                    ),
              );
              return { conversationId: selectedConversationId, callsByMessageId: next };
            });
          }
        }
        queryClient.setQueryData<ConversationMessage[]>(
          ["conversation-messages", selectedConversationId],
          (current) => replaceMessage(current, event.message),
        );
        setStreamNotice(undefined);
        if (["assistant.completed", "assistant.failed", "assistant.stopped"].includes(event.type)) {
          void queryClient.invalidateQueries({ queryKey: ["conversations"] });
          void queryClient.invalidateQueries({
            queryKey: ["conversation-workflow-runs", selectedConversationId],
          });
        }
      },
      onError: () => {
        setStreamNotice("会话连接已中断，正在恢复消息历史");
        void queryClient.invalidateQueries({
          queryKey: ["conversation-messages", selectedConversationId],
        });
        void queryClient.invalidateQueries({
          queryKey: ["conversation-workflow-runs", selectedConversationId],
        });
      },
    });
    return () => subscription.close();
  }, [queryClient, selectedConversationId]);

  const startNewConversation = () => {
    setStreamNotice(undefined);
    setSearchParams(selectedEmployeeId ? { employee_id: selectedEmployeeId } : {});
  };

  const sendMutation = useMutation({
    mutationFn: async (content: string) => {
      if (!selectedModelConfigurationId) throw new Error("请先选择模型");
      const messageId = crypto.randomUUID();
      if (selectedConversationId) {
        const turn = await sendConversationMessage(selectedConversationId, {
          message_id: messageId,
          model_configuration_id: selectedModelConfigurationId,
          content,
        });
        return { conversation: undefined, turn };
      }
      return createConversationTurn({
        conversation_id: crypto.randomUUID(),
        message_id: messageId,
        employee_id: selectedEmployeeId ?? null,
        model_configuration_id: selectedModelConfigurationId,
        content,
        tool_collection_ids: selectedEmployeeId ? [] : toolSelection.collection_ids,
        tool_capability_ids: selectedEmployeeId ? [] : toolSelection.capability_ids,
      });
    },
    onSuccess: async (accepted) => {
      setDraft("");
      const conversationId = accepted.conversation?.id ?? selectedConversationId;
      if (!conversationId) return;
      queryClient.setQueryData<ConversationMessage[]>(
        ["conversation-messages", conversationId],
        (current) =>
          mergeAcceptedTurn(
            current,
            accepted.turn.user_message,
            accepted.turn.assistant_message,
          ),
      );
      if (accepted.conversation) {
        queryClient.setQueryData(
          ["conversation", accepted.conversation.id],
          {
            ...accepted.conversation,
            employee_name:
              accepted.conversation.source === "employee"
                ? (selectedEmployee?.name ?? null)
                : null,
          },
        );
        setSearchParams(
          accepted.conversation.source === "employee" && accepted.conversation.employee_id
            ? {
                employee_id: accepted.conversation.employee_id,
                conversation_id: accepted.conversation.id,
              }
            : { conversation_id: accepted.conversation.id },
        );
        await queryClient.invalidateQueries({ queryKey: ["conversations"] });
      } else {
        await queryClient.invalidateQueries({
          queryKey: ["conversation", conversationId],
          exact: true,
        });
      }
    },
  });
  const stopMutation = useMutation({
    mutationFn: async () => {
      if (!selectedConversationId) throw new Error("当前没有可停止的会话");
      return stopConversationGeneration(selectedConversationId);
    },
  });
  const retryMutation = useMutation({
    mutationFn: (messageId: string) => retryConversationMessage(messageId),
    onSuccess: (turn) => {
      if (!selectedConversationId) return;
      queryClient.setQueryData<ConversationMessage[]>(
        ["conversation-messages", selectedConversationId],
        (current) => replaceMessage(current, turn.assistant_message),
      );
    },
  });
  const saveToolGrantsMutation = useMutation({
    mutationFn: async (selection: ToolGrantSelection) => {
      if (!selectedConversationId || selectedConversation?.source !== "generic") {
        throw new Error("只有通用 AI 会话可以单独配置工具");
      }
      return replaceConversationToolGrants(selectedConversationId, selection);
    },
    onSuccess: (grant) => {
      queryClient.setQueryData(
        ["conversation-tool-grants", selectedConversationId],
        grant,
      );
    },
  });

  const sendDraft = () => {
    const content = draft.trim();
    if (!content || activeMessage || sendMutation.isPending) return;
    sendMutation.mutate(content);
  };

  return {
    activeMessage,
    draft,
    employees,
    employeeItems,
    employeeSearch,
    messages,
    modelConfigurations,
    contextModelConfiguration,
    modelConfigurationItems,
    toolCatalog,
    toolSelection,
    toolCallsByMessageId,
    toolCapabilityNames,
    conversationToolGrants,
    employeeToolGrants,
    saveToolGrantsMutation,
    selectedModelConfigurationId,
    operationError:
      selectedConversationQuery.error ??
      selectedEmployeeQuery.error ??
      sendMutation.error ??
      stopMutation.error ??
      retryMutation.error ??
      saveToolGrantsMutation.error,
    retryMutation,
    runsByMessageId,
    selectedConversation,
    selectedConversationQuery,
    selectedConversationId,
    selectedEmployee,
    selectedEmployeeId,
    selectedEmployeeQuery,
    requestedEmployeeId,
    selectEmployee: (value: string) =>
      setSearchParams(value === GENERIC_CHAT_VALUE ? {} : { employee_id: value }),
    sendDraft,
    sendMutation,
    setDraft,
    setEmployeeSearch,
    setSelectedModelConfigurationId,
    setToolSelection: (selection: ToolGrantSelection) =>
      setToolSelectionOverride({ contextKey: toolSelectionContextKey, selection }),
    startNewConversation,
    stopMutation,
    streamNotice,
    workflowsById,
    loadMoreRuns: () => workflowRuns.fetchNextPage(),
    loadingMoreRuns: workflowRuns.isFetchingNextPage,
    hasMoreRuns: workflowRuns.hasNextPage,
    openWorkflowRun: (runId: string) => navigate(`/workflows?run_id=${runId}`),
  };
}

function toolCallStatus(
  eventType: ConversationEvent["type"],
): ChatToolCallLifecycle["status"] | undefined {
  if (eventType === "assistant.tool.started") return "running";
  if (eventType === "assistant.tool.completed") return "completed";
  if (eventType === "assistant.tool.failed") return "failed";
  return undefined;
}

export type ChatPageController = ReturnType<typeof useChatPageController>;
