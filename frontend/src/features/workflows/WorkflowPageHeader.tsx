import { Button, Flex, Space, Tag, Typography } from "antd";
import { ArrowLeft, Save } from "lucide-react";

import { ResourceDeleteButton } from "../../components/ResourceDeleteButton";
import type { useWorkflowDesigner } from "./useWorkflowDesigner";

const { Paragraph, Title } = Typography;

export function WorkflowPageHeader({
  controller,
  readOnly = false,
}: {
  controller: ReturnType<typeof useWorkflowDesigner>;
  readOnly?: boolean;
}) {
  const { state } = controller;
  return (
    <Flex justify="space-between" align="flex-start" gap={24} className="workflows-heading">
      <Space align="start">
        <Button
          className="workflow-back-button"
          icon={<ArrowLeft aria-hidden="true" size={18} />}
          aria-label="返回工作流列表"
          onClick={controller.closeDesigner}
        />
        <div>
          <Space align="center">
            <Title level={2}>{state.name || "未命名工作流"}</Title>
            {state.dirty ? <Tag color="gold">有未保存修改</Tag> : <Tag>已保存</Tag>}
          </Space>
          <Paragraph type="secondary">
            拖入节点并通过连接点编排流程，保存前由服务端执行最终校验。
          </Paragraph>
        </div>
      </Space>
      <Space>
        <ResourceDeleteButton
          resourceKind="工作流"
          resourceName={state.name || "未命名工作流"}
          impact="工作流定义、节点、连线和已终止运行记录都会被永久删除。"
          disabled={readOnly || !state.workflowId || controller.activeRun || controller.deleteMutation.isPending}
          loading={controller.deleteMutation.isPending}
          onConfirm={controller.deleteSelectedWorkflow}
        />
        <Button
          type="primary"
          icon={<Save aria-hidden="true" size={16} />}
          aria-label="保存工作流"
          loading={controller.saveMutation.isPending}
          disabled={readOnly || controller.activeRun}
          onClick={controller.save}
        >
          校验并保存
        </Button>
      </Space>
    </Flex>
  );
}
