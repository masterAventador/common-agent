import { describe, expect, it } from "vitest";

import { ApiClientError } from "../api/errors";
import { getResourceDeletionErrorMessage } from "./resourceDeletion";

describe("resource deletion error presentation", () => {
  it.each([
    ["conversation_busy", "当前会话仍在生成回复，请先停止生成并等待状态收敛后再删除。"],
    [
      "employee_in_use_by_conversations",
      "该数字员工仍被会话引用，请先在 AI 会话页删除相关会话。",
    ],
    [
      "employee_in_use_by_workflows",
      "该数字员工仍被工作流 AI 对话节点引用，请先修改或删除相关工作流。",
    ],
    [
      "knowledge_base_in_use_by_employees",
      "该知识库仍被数字员工绑定，请先在数字员工页解除绑定。",
    ],
    [
      "knowledge_base_in_use_by_workflows",
      "该知识库仍被工作流节点引用，请先修改或删除相关工作流。",
    ],
    [
      "workflow_in_use_by_employees",
      "该工作流仍在数字员工允许列表中，请先在数字员工页解除授权。",
    ],
    ["workflow_has_active_runs", "该工作流仍有活跃运行，请等待运行完成或停止后再重试。"],
    [
      "knowledge_base_delete_result_unknown",
      "知识库删除结果暂时无法确认，请先刷新列表核对；资源仍存在时再手动删除。",
    ],
  ])("maps %s to an actionable instruction", (code, expected) => {
    expect(
      getResourceDeletionErrorMessage(new ApiClientError("provider text", code, "request", false)),
    ).toBe(expected);
  });

  it("keeps a stable server message for an unknown deletion error", () => {
    expect(
      getResourceDeletionErrorMessage(
        new ApiClientError("稳定服务错误", "future_delete_error", "request", false),
      ),
    ).toBe("稳定服务错误");
  });
});
