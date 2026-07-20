import {
  ApartmentOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import { ReactFlowProvider } from "@xyflow/react";
import { Alert, Button, Flex, Skeleton, Space, Tag, Typography } from "antd";

import { getErrorMessage } from "../../api/errors";
import { WorkflowCanvas } from "./WorkflowCanvas";
import { WorkflowInspector } from "./WorkflowInspector";
import { WorkflowSidebar } from "./WorkflowSidebar";
import { useWorkflowDesigner } from "./useWorkflowDesigner";

const { Paragraph, Title } = Typography;

export function WorkflowsPage() {
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
            disabled={controller.activeRun}
            onClick={controller.createDraft}
          >
            新建工作流
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            aria-label="保存工作流"
            loading={controller.saveMutation.isPending}
            disabled={controller.activeRun}
            onClick={controller.save}
          >
            校验并保存
          </Button>
        </Space>
      </Flex>

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
          workflows={workflows.data}
          state={state}
          editingLocked={controller.activeRun}
          onSelectWorkflow={controller.selectWorkflow}
          dispatch={controller.dispatch}
        />
        <ReactFlowProvider>
          <WorkflowCanvas
            state={state}
            run={controller.visibleRun}
            editingLocked={controller.activeRun}
            dispatch={controller.dispatch}
          />
        </ReactFlowProvider>
        <WorkflowInspector
          state={state}
          knowledgeBases={controller.knowledgeBases.data ?? []}
          knowledgeLoading={controller.knowledgeBases.isPending}
          knowledgeError={controller.knowledgeError}
          editingLocked={controller.activeRun}
          runController={controller.runController}
          dispatch={controller.dispatch}
        />
      </div>
    </section>
  );
}
