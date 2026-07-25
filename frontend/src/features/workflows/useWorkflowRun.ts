import { useMutation, useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  fetchWorkflowRun,
  startWorkflowRun,
  stopWorkflowRun,
  subscribeToWorkflowRunEvents,
  type WorkflowRun,
  type WorkflowRunEvent,
} from "../../api/workflowRuns";

const statusOrder: Record<WorkflowRun["status"], number> = {
  pending: 0,
  running: 1,
  completed: 2,
  failed: 2,
  stopped: 2,
};

export function isWorkflowRunActive(run: WorkflowRun | undefined): boolean {
  return Boolean(run && ["pending", "running"].includes(run.status));
}

function mergeWorkflowRun(
  current: WorkflowRun | undefined,
  next: WorkflowRun,
): WorkflowRun {
  if (!current || current.id !== next.id) return next;
  const currentUpdatedAt = Date.parse(current.updated_at);
  const nextUpdatedAt = Date.parse(next.updated_at);
  if (
    nextUpdatedAt < currentUpdatedAt ||
    (nextUpdatedAt === currentUpdatedAt && statusOrder[next.status] < statusOrder[current.status])
  ) {
    return current;
  }
  return next;
}

export interface WorkflowRunController {
  input: string;
  setInput: (value: string) => void;
  run: WorkflowRun | undefined;
  streamNotice: string | undefined;
  restoreError: unknown;
  startError: unknown;
  stopError: unknown;
  starting: boolean;
  stopping: boolean;
  start: () => void;
  stop: () => void;
  clear: () => void;
}

export function useWorkflowRun(
  workflowId: string | null,
  dirty: boolean,
): WorkflowRunController {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedRunId = searchParams.get("run_id");
  const [inputDraft, setInputDraft] = useState<{ runId?: string; value: string }>({ value: "" });
  const [localRun, setLocalRun] = useState<WorkflowRun>();
  const [streamNotice, setStreamNotice] = useState<string>();
  const lastSequence = useRef(0);
  const subscription = useRef<{ close: () => void } | undefined>(undefined);

  const restoredRun = useQuery({
    queryKey: ["workflow-run", requestedRunId],
    queryFn: () => fetchWorkflowRun(requestedRunId ?? ""),
    enabled: Boolean(requestedRunId && requestedRunId !== localRun?.id),
    retry: false,
  });
  const run = requestedRunId
    ? localRun?.id === requestedRunId
      ? localRun
      : restoredRun.data
    : localRun;
  const input = inputDraft.runId === run?.id ? inputDraft.value : (run?.input ?? inputDraft.value);

  const setRunId = useCallback(
    (runId?: string) => {
      const next = new URLSearchParams(searchParams);
      if (runId) next.set("run_id", runId);
      else next.delete("run_id");
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const startMutation = useMutation({
    mutationFn: async () => {
      if (!workflowId || dirty) throw new Error("请先保存工作流");
      const content = input.trim();
      if (!content) throw new Error("请输入工作流运行内容");
      return startWorkflowRun(workflowId, {
        run_id: crypto.randomUUID(),
        input: content,
      });
    },
    onSuccess: (started) => {
      subscription.current?.close();
      lastSequence.current = 0;
      setStreamNotice(undefined);
      setLocalRun(started);
      setInputDraft({ runId: started.id, value: started.input });
      setRunId(started.id);
    },
  });

  const stopMutation = useMutation({
    mutationFn: async () => {
      if (!run || !isWorkflowRunActive(run)) throw new Error("当前没有可停止的工作流运行");
      return stopWorkflowRun(run.id);
    },
  });

  const activeRunId = isWorkflowRunActive(run) ? run?.id : undefined;
  useEffect(() => {
    if (!activeRunId) return;
    const runId = activeRunId;
    const workflowRunSubscription = subscribeToWorkflowRunEvents(runId, {
      afterSequence: lastSequence.current,
      onEvent: (event: WorkflowRunEvent) => {
        if (
          event.run_id !== runId ||
          event.workflow_id !== event.run.workflow_id ||
          event.sequence <= lastSequence.current
        ) {
          return;
        }
        lastSequence.current = event.sequence;
        setStreamNotice(undefined);
        setLocalRun((current) => mergeWorkflowRun(current, event.run));
      },
      onError: () => {
        void fetchWorkflowRun(runId)
          .then((summary) => {
            setLocalRun((current) => mergeWorkflowRun(current, summary));
            setStreamNotice("事件连接已中断，已同步权威运行摘要");
          })
          .catch(() => setStreamNotice("事件连接已中断，运行摘要恢复失败"));
      },
    });
    subscription.current = workflowRunSubscription;
    return () => {
      workflowRunSubscription.close();
      if (subscription.current === workflowRunSubscription) subscription.current = undefined;
    };
  }, [activeRunId]);

  const clear = useCallback(() => {
    subscription.current?.close();
    subscription.current = undefined;
    lastSequence.current = 0;
    setLocalRun(undefined);
    setInputDraft({ value: "" });
    setStreamNotice(undefined);
    startMutation.reset();
    stopMutation.reset();
    setRunId(undefined);
  }, [setRunId, startMutation, stopMutation]);

  return {
    input,
    setInput: (value) => setInputDraft({ runId: run?.id, value }),
    run,
    streamNotice,
    restoreError: restoredRun.error,
    startError: startMutation.error,
    stopError: stopMutation.error,
    starting: startMutation.isPending,
    stopping: stopMutation.isPending,
    start: () => startMutation.mutate(),
    stop: () => stopMutation.mutate(),
    clear,
  };
}
