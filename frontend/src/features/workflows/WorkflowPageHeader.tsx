import { ApartmentOutlined, PlusOutlined, SaveOutlined } from "@ant-design/icons";
import { Button, Flex, Space, Tag, Typography } from "antd";

import { ResourceDeleteButton } from "../../components/ResourceDeleteButton";
import type { useWorkflowDesigner } from "./useWorkflowDesigner";

const { Paragraph, Title } = Typography;

export function WorkflowPageHeader({
  controller,
}: {
  controller: ReturnType<typeof useWorkflowDesigner>;
}) {
  const { state } = controller;
  return (
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
        <ResourceDeleteButton
          resourceKind="工作流"
          resourceName={state.name || "未命名工作流"}
          impact="工作流定义、节点、连线和已终止运行记录都会被永久删除。"
          disabled={!state.workflowId || controller.activeRun || controller.deleteMutation.isPending}
          loading={controller.deleteMutation.isPending}
          onConfirm={controller.deleteSelectedWorkflow}
        />
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
  );
}
