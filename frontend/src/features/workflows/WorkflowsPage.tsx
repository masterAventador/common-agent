import { Alert, Button, Skeleton } from "antd";
import { RefreshCw } from "lucide-react";
import { lazy, Suspense } from "react";
import { getErrorMessage } from "../../api/errors";
import { WorkflowList } from "./WorkflowList";
import { WorkflowPageHeader } from "./WorkflowPageHeader";
import { WorkflowSidebar } from "./WorkflowSidebar";
import { useWorkflowDesigner } from "./useWorkflowDesigner";
const WorkflowCanvasSurface = lazy(async () => {
  const module = await import("./WorkflowCanvasSurface");
  return { default: module.WorkflowCanvasSurface };
});
const WorkflowInspector = lazy(async () => {
  const module = await import("./WorkflowInspector");
  return { default: module.WorkflowInspector };
});
export function WorkflowsPage({ readOnly = false }: { readOnly?: boolean }) {
  const controller = useWorkflowDesigner();
  const { workflows, state } = controller;
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
              icon={<RefreshCw aria-hidden="true" size={16} />}
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
  if (!controller.designerOpen) {
    return (
      <section className="workflows-page is-list">
        <WorkflowList
          workflows={controller.workflowItems}
          search={controller.workflowSearch}
          readOnly={readOnly}
          hasMore={Boolean(workflows.hasNextPage)}
          loadingMore={workflows.isFetchingNextPage}
          onSearch={controller.setWorkflowSearch}
          onLoadMore={() => void workflows.fetchNextPage()}
          onSelect={controller.selectWorkflow}
          onCreate={controller.createDraft}
        />
      </section>
    );
  }
  return (
    <section className="workflows-page">
      <WorkflowPageHeader controller={controller} readOnly={readOnly} />

      {(controller.localValidationMessage || controller.saveMutation.isError) && (
        <Alert
          type="error"
          showIcon
          title="工作流保存失败"
          description={
            controller.localValidationMessage ??
            getErrorMessage(controller.saveMutation.error ?? new Error("保存失败"))
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
                      onClick={() =>
                        controller.dispatch({ type: "node_selected", nodeId: issue.node_id })
                      }
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
        <WorkflowSidebar
          state={state}
          editingLocked={controller.activeRun || readOnly}
          dispatch={controller.dispatch}
        />
        <Suspense fallback={<Skeleton.Node active />}>
          <WorkflowCanvasSurface
            state={state}
            run={controller.visibleRun}
            editingLocked={controller.activeRun || readOnly}
            dispatch={controller.dispatch}
          />
        </Suspense>
        <Suspense fallback={<Skeleton active paragraph={{ rows: 8 }} />}>
          <WorkflowInspector
            state={state}
            employees={controller.employeeItems}
            models={controller.modelItems}
            targetLoading={controller.employees.isPending || controller.models.isPending}
            targetError={controller.targetError}
            onTargetPopupScroll={(event) => {
              const target = event.currentTarget;
              if (target.scrollTop + target.clientHeight < target.scrollHeight - 16) return;
              if (
                controller.employees.hasNextPage &&
                !controller.employees.isFetchingNextPage
              ) {
                void controller.employees.fetchNextPage();
              }
              if (controller.models.hasNextPage && !controller.models.isFetchingNextPage) {
                void controller.models.fetchNextPage();
              }
            }}
            knowledgeBases={controller.knowledgeItems}
            knowledgeLoading={controller.knowledgeBases.isPending}
            knowledgeError={controller.knowledgeError}
            knowledgeSearch={controller.knowledgeSearch}
            onKnowledgeSearch={controller.setKnowledgeSearch}
            onKnowledgePopupScroll={(event) => {
              const target = event.currentTarget;
              if (
                controller.knowledgeBases.hasNextPage &&
                !controller.knowledgeBases.isFetchingNextPage &&
                target.scrollTop + target.clientHeight >= target.scrollHeight - 16
              ) {
                void controller.knowledgeBases.fetchNextPage();
              }
            }}
            editingLocked={controller.activeRun || readOnly}
            readOnly={readOnly}
            runController={controller.runController}
            dispatch={controller.dispatch}
          />
        </Suspense>
      </div>
    </section>
  );
}
