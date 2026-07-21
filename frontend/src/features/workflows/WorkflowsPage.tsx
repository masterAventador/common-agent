import { ReloadOutlined } from "@ant-design/icons";
import { ReactFlowProvider } from "@xyflow/react";
import { Alert, Button, Skeleton } from "antd";
import { getErrorMessage } from "../../api/errors";
import { getResourceDeletionErrorMessage } from "../../components/resourceDeletion";
import { WorkflowCanvas } from "./WorkflowCanvas";
import { WorkflowInspector } from "./WorkflowInspector";
import { WorkflowPageHeader } from "./WorkflowPageHeader";
import { WorkflowSidebar } from "./WorkflowSidebar";
import { useWorkflowDesigner } from "./useWorkflowDesigner";

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
      <WorkflowPageHeader controller={controller} readOnly={readOnly} />

      {controller.deleteNotice && (
        <Alert
          type="success"
          showIcon
          closable
          title={controller.deleteNotice}
          className="workflows-alert"
        />
      )}

      {controller.deleteMutation.isError && (
        <Alert
          type="error"
          showIcon
          closable
          title="工作流删除失败"
          description={getResourceDeletionErrorMessage(controller.deleteMutation.error)}
          className="workflows-alert"
          onClose={() => controller.deleteMutation.reset()}
        />
      )}

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
          workflows={controller.workflowItems}
          state={state}
          editingLocked={controller.activeRun || readOnly}
          search={controller.workflowSearch}
          onSearch={controller.setWorkflowSearch}
          hasMore={Boolean(workflows.hasNextPage)}
          loadingMore={workflows.isFetchingNextPage}
          onLoadMore={() => void workflows.fetchNextPage()}
          onSelectWorkflow={controller.selectWorkflow}
          dispatch={controller.dispatch}
        />
        <ReactFlowProvider>
          <WorkflowCanvas
            state={state}
            run={controller.visibleRun}
            editingLocked={controller.activeRun || readOnly}
            dispatch={controller.dispatch}
          />
        </ReactFlowProvider>
        <WorkflowInspector
          state={state}
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
      </div>
    </section>
  );
}
