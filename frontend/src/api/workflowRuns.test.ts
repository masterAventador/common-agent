import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import {
  fetchConversationWorkflowRuns,
  fetchWorkflowRun,
  parseWorkflowRunEvent,
  parseWorkflowRunResponse,
  startWorkflowRun,
  stopWorkflowRun,
  subscribeToWorkflowRunEvents,
} from "./workflowRuns";

vi.mock("./client", () => ({
  apiBaseUrl: "http://127.0.0.1:18200/api/v1",
  getTenantId: () => "10000000-0000-4000-8000-000000000001",
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const run = {
  id: "a69b7bd1-7d4e-44f2-8c70-9ecfc38dad08",
  workflow_id: "9a2f8cb8-7f5f-41f8-b101-9ed76f40d9c6",
  trigger: "manual" as const,
  status: "running" as const,
  input: "请执行工作流",
  output: "",
  current_node_id: "chat",
  completed_node_ids: ["start"],
  failed_node_id: null,
  error_code: null,
  origin: null,
  ai_targets: [
    {
      node_id: "chat",
      target_type: "model" as const,
      target_id: "67b23894-27bd-49dd-a023-d926905e7ea1",
      target_name: "通用模型",
      model_configuration_id: "67b23894-27bd-49dd-a023-d926905e7ea1",
      model_identifier: "qwen-plus",
    },
  ],
  created_at: "2026-07-20T06:00:00Z",
  started_at: "2026-07-20T06:00:00Z",
  finished_at: null,
  updated_at: "2026-07-20T06:00:01Z",
};

const event = {
  schema_version: "1" as const,
  sequence: 3,
  run_id: run.id,
  workflow_id: run.workflow_id,
  type: "workflow.node.started" as const,
  node_id: "chat",
  run,
  occurred_at: "2026-07-20T06:00:01Z",
};

class FakeEventSource {
  static latest: FakeEventSource | undefined;
  readonly listeners = new Map<string, Array<(event: MessageEvent<string>) => void>>();
  readonly close = vi.fn();
  onerror: ((event: Event) => void) | null = null;

  constructor(
    readonly url: string,
    readonly eventSourceInit?: EventSourceInit,
  ) {
    FakeEventSource.latest = this;
  }

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  emit(type: string, payload: unknown) {
    for (const listener of this.listeners.get(type) ?? []) {
      listener(new MessageEvent(type, { data: JSON.stringify(payload) }));
    }
  }
}

describe("workflow run API and SSE boundary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    FakeEventSource.latest = undefined;
    vi.stubGlobal("EventSource", FakeEventSource);
  });

  it("accepts generated run and event snapshots and rejects protocol drift", () => {
    const employeeRun = {
      ...run,
      trigger: "employee" as const,
      origin: {
        employee_id: "52a34887-e32a-4709-aa32-6835502a8bc8",
        conversation_id: "4feb17bd-684e-4160-a2a0-ca8ac91a6817",
        assistant_message_id: "baeed6a2-d8cb-49ac-8999-393cf2153161",
      },
    };
    expect(parseWorkflowRunResponse(run)).toEqual(run);
    expect(parseWorkflowRunResponse(employeeRun)).toEqual(employeeRun);
    expect(parseWorkflowRunEvent(event)).toEqual(event);

    expect(() => parseWorkflowRunResponse({ ...run, private_context: "secret" })).toThrow();
    expect(() => parseWorkflowRunResponse({ ...run, status: "unknown" })).toThrow();
    expect(() => parseWorkflowRunResponse({ ...run, origin: employeeRun.origin })).toThrow();
    expect(() => parseWorkflowRunResponse({ ...employeeRun, origin: null })).toThrow();
    expect(() =>
      parseWorkflowRunResponse({
        ...employeeRun,
        origin: { ...employeeRun.origin, employee_id: "not-a-uuid" },
      }),
    ).toThrow();
    expect(() =>
      parseWorkflowRunResponse({
        ...employeeRun,
        origin: {
          employee_id: employeeRun.origin.employee_id,
          conversation_id: employeeRun.origin.conversation_id,
        },
      }),
    ).toThrow();
    expect(() =>
      parseWorkflowRunResponse({
        ...employeeRun,
        origin: { ...employeeRun.origin, private_context: "secret" },
      }),
    ).toThrow();
    expect(() => parseWorkflowRunEvent({ ...event, schema_version: "2" })).toThrow();
    expect(() =>
      parseWorkflowRunEvent({
        ...event,
        run: { ...run, id: "3c092b48-b158-4b11-a224-e5691ec5dc29" },
      }),
    ).toThrow();
    expect(() =>
      parseWorkflowRunEvent({ ...event, run: { ...run, completed_node_ids: [""] } }),
    ).toThrow();
  });

  it("uses only the formal start, conversation list, summary, and stop endpoints", async () => {
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce({ data: run })
      .mockResolvedValueOnce({ data: { run_id: run.id } });
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: { items: [run], next_cursor: null } })
      .mockResolvedValueOnce({ data: run });

    await expect(
      startWorkflowRun(run.workflow_id, { run_id: run.id, input: run.input }),
    ).resolves.toEqual(run);
    await expect(fetchConversationWorkflowRuns("4feb17bd-684e-4160-a2a0-ca8ac91a6817"))
      .resolves.toEqual({ items: [run], next_cursor: null });
    await expect(fetchWorkflowRun(run.id)).resolves.toEqual(run);
    await expect(stopWorkflowRun(run.id)).resolves.toEqual({ run_id: run.id });

    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      `/workflows/${run.workflow_id}/runs`,
      { run_id: run.id, input: run.input },
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(1, "/workflow-runs", {
      params: { conversation_id: "4feb17bd-684e-4160-a2a0-ca8ac91a6817" },
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(2, `/workflow-runs/${run.id}`);
    expect(apiClient.post).toHaveBeenNthCalledWith(2, `/workflow-runs/${run.id}/stop`);
  });

  it("parses every named SSE event, reports malformed payloads, and closes explicitly", () => {
    const onEvent = vi.fn();
    const onError = vi.fn();
    const subscription = subscribeToWorkflowRunEvents(run.id, {
      afterSequence: 2,
      onEvent,
      onError,
    });
    const source = FakeEventSource.latest;
    expect(source?.url).toBe(
      `http://127.0.0.1:18200/api/v1/workflow-runs/${run.id}/events?after_sequence=2&tenant_id=10000000-0000-4000-8000-000000000001`,
    );
    expect(source?.eventSourceInit).toEqual({ withCredentials: true });

    source?.emit("workflow.node.started", event);
    source?.emit("workflow.run.completed", { ...event, schema_version: "2" });

    expect(onEvent).toHaveBeenCalledWith(event);
    expect(onError).toHaveBeenCalledTimes(1);
    subscription.close();
    expect(source?.close).toHaveBeenCalledTimes(1);
  });
});
