import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  createConversation,
  deleteConversation,
  fetchConversationMessages,
  fetchConversations,
  retryConversationMessage,
  sendConversationMessage,
  stopConversationGeneration,
  subscribeToConversationEvents,
  type ConversationEvent,
  type Conversation,
  type ConversationMessage,
} from "../../api/conversations";
import { fetchEmployees } from "../../api/employees";
import { fetchConversationWorkflowRuns } from "../../api/workflowRuns";
import { fetchWorkflows } from "../../api/workflows";
import { groupWorkflowRunsByMessage, mergeAcceptedTurn, replaceMessage } from "./chatState";

export function useChatPageController() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [draft, setDraft] = useState("");
  const [deleteNotice, setDeleteNotice] = useState<string>();
  const [streamNotice, setStreamNotice] = useState<string>();
  const lastEventSequence = useRef(0);
  const requestedEmployeeId = searchParams.get("employee_id");
  const requestedConversationId = searchParams.get("conversation_id");

  const employees = useQuery({ queryKey: ["employees"], queryFn: fetchEmployees });
  const selectedEmployee = useMemo(
    () =>
      employees.data?.find((employee) => employee.id === requestedEmployeeId) ??
      employees.data?.[0],
    [employees.data, requestedEmployeeId],
  );
  const conversations = useQuery({
    queryKey: ["conversations", selectedEmployee?.id],
    queryFn: () => fetchConversations(selectedEmployee?.id),
    enabled: Boolean(selectedEmployee),
  });
  const selectedConversation = conversations.data?.find(
    (conversation) => conversation.id === requestedConversationId,
  );
  const selectedConversationId = selectedConversation?.id;
  const messages = useQuery({
    queryKey: ["conversation-messages", selectedConversationId],
    queryFn: () => fetchConversationMessages(selectedConversationId ?? ""),
    enabled: Boolean(selectedConversationId),
  });
  const activeMessage = messages.data?.find(
    (message) =>
      message.role === "assistant" && ["pending", "streaming"].includes(message.status),
  );
  const workflowRuns = useQuery({
    queryKey: ["conversation-workflow-runs", selectedConversationId],
    queryFn: () => fetchConversationWorkflowRuns(selectedConversationId ?? ""),
    enabled: Boolean(selectedConversationId),
    refetchInterval: activeMessage ? 1_000 : false,
  });
  const workflows = useQuery({
    queryKey: ["workflows"],
    queryFn: fetchWorkflows,
    enabled: Boolean(selectedConversationId),
  });
  const workflowsById = useMemo(
    () => new Map((workflows.data ?? []).map((workflow) => [workflow.id, workflow])),
    [workflows.data],
  );
  const runsByMessageId = useMemo(
    () => groupWorkflowRunsByMessage(workflowRuns.data ?? []),
    [workflowRuns.data],
  );

  useEffect(() => {
    if (!employees.data?.length || !selectedEmployee || selectedEmployee.id === requestedEmployeeId) {
      return;
    }
    setSearchParams({ employee_id: selectedEmployee.id }, { replace: true });
  }, [employees.data, requestedEmployeeId, selectedEmployee, setSearchParams]);

  useEffect(() => {
    if (!selectedEmployee || !conversations.data?.length || selectedConversation) return;
    setSearchParams(
      {
        employee_id: selectedEmployee.id,
        conversation_id: conversations.data[0].id,
      },
      { replace: true },
    );
  }, [conversations.data, selectedConversation, selectedEmployee, setSearchParams]);

  useEffect(() => {
    if (!selectedConversationId) return;
    lastEventSequence.current = 0;
    const subscription = subscribeToConversationEvents(selectedConversationId, {
      afterSequence: 0,
      onEvent: (event: ConversationEvent) => {
        if (event.sequence <= lastEventSequence.current) return;
        lastEventSequence.current = event.sequence;
        queryClient.setQueryData<ConversationMessage[]>(
          ["conversation-messages", selectedConversationId],
          (current) => replaceMessage(current, event.message),
        );
        setStreamNotice(undefined);
        if (["assistant.completed", "assistant.failed", "assistant.stopped"].includes(event.type)) {
          void queryClient.invalidateQueries({ queryKey: ["conversations", selectedEmployee?.id] });
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
  }, [queryClient, selectedConversationId, selectedEmployee?.id]);

  const selectConversation = (conversationId: string) => {
    if (!selectedEmployee) return;
    setStreamNotice(undefined);
    setSearchParams({ employee_id: selectedEmployee.id, conversation_id: conversationId });
  };

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!selectedEmployee) throw new Error("请先选择数字员工");
      return createConversation({
        conversation_id: crypto.randomUUID(),
        employee_id: selectedEmployee.id,
        title: "新会话",
      });
    },
    onSuccess: (created) => {
      queryClient.setQueryData<typeof conversations.data>(
        ["conversations", created.employee_id],
        (current) => [created, ...(current ?? []).filter((item) => item.id !== created.id)],
      );
      selectConversation(created.id);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (conversation: Conversation) => {
      setDeleteNotice(undefined);
      await deleteConversation(conversation.id);
      return conversation;
    },
    onSuccess: async (deleted) => {
      const listKey = ["conversations", deleted.employee_id] as const;
      const current = queryClient.getQueryData<Conversation[]>(listKey) ?? [];
      const remaining = current.filter((item) => item.id !== deleted.id);
      queryClient.setQueryData(listKey, remaining);
      queryClient.removeQueries({
        queryKey: ["conversation-messages", deleted.id],
        exact: true,
      });
      queryClient.removeQueries({
        queryKey: ["conversation-workflow-runs", deleted.id],
        exact: true,
      });
      if (selectedConversation?.id === deleted.id) {
        setStreamNotice(undefined);
        const next = remaining[0];
        setSearchParams(
          next
            ? { employee_id: deleted.employee_id, conversation_id: next.id }
            : { employee_id: deleted.employee_id },
          { replace: true },
        );
      }
      setDeleteNotice(`会话“${deleted.title}”已删除`);
      await queryClient.invalidateQueries({ queryKey: listKey });
    },
  });

  const sendMutation = useMutation({
    mutationFn: async (content: string) => {
      if (!selectedConversation) throw new Error("请先创建会话");
      return sendConversationMessage(selectedConversation.id, {
        message_id: crypto.randomUUID(),
        content,
      });
    },
    onSuccess: (turn) => {
      if (!selectedConversation) return;
      setDraft("");
      queryClient.setQueryData<ConversationMessage[]>(
        ["conversation-messages", selectedConversation.id],
        (current) => mergeAcceptedTurn(current, turn.user_message, turn.assistant_message),
      );
    },
  });
  const stopMutation = useMutation({
    mutationFn: async () => {
      if (!selectedConversation) throw new Error("当前没有可停止的会话");
      return stopConversationGeneration(selectedConversation.id);
    },
  });
  const retryMutation = useMutation({
    mutationFn: (messageId: string) => retryConversationMessage(messageId),
    onSuccess: (turn) => {
      if (!selectedConversation) return;
      queryClient.setQueryData<ConversationMessage[]>(
        ["conversation-messages", selectedConversation.id],
        (current) => replaceMessage(current, turn.assistant_message),
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
    conversations,
    createMutation,
    deleteMutation,
    deleteNotice,
    draft,
    employees,
    messages,
    operationError:
      deleteMutation.error ??
      createMutation.error ??
      sendMutation.error ??
      stopMutation.error ??
      retryMutation.error,
    retryMutation,
    runsByMessageId,
    selectedConversation,
    selectedEmployee,
    selectConversation,
    selectEmployee: (employeeId: string) => setSearchParams({ employee_id: employeeId }),
    sendDraft,
    sendMutation,
    setDraft,
    stopMutation,
    streamNotice,
    workflowsById,
    openWorkflowRun: (runId: string) => navigate(`/workflows?run_id=${runId}`),
  };
}

export type ChatPageController = ReturnType<typeof useChatPageController>;
