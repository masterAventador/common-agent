import { Alert, Button, Empty, Flex, Select, Skeleton, Space, Typography } from "antd";
import { MessageSquare, RefreshCw } from "lucide-react";

import { getErrorMessage } from "../../api/errors";
import { getResourceDeletionErrorMessage } from "../../components/resourceDeletion";
import { ChatWorkspace } from "./ChatWorkspace";
import { GENERIC_CHAT_VALUE, useChatPageController } from "./useChatPageController";

const { Title } = Typography;

export function ChatPage({ readOnly = false }: { readOnly?: boolean }) {
  const controller = useChatPageController();
  const { employeeItems, employees, modelConfigurations, selectedEmployee } = controller;

  if (modelConfigurations.isPending) {
    return (
      <section className="chat-page" aria-label="AI 会话加载中">
        <Skeleton active paragraph={{ rows: 10 }} />
      </section>
    );
  }
  if (modelConfigurations.isError) {
    return (
      <section className="chat-page">
        <Alert
          type="error"
          showIcon
          title="模型配置加载失败"
          description={getErrorMessage(modelConfigurations.error)}
          action={
            <Button
              icon={<RefreshCw aria-hidden="true" size={16} />}
              onClick={() => void modelConfigurations.refetch()}
            >
              重试加载
            </Button>
          }
        />
      </section>
    );
  }
  if (!controller.modelConfigurationItems.length) {
    return (
      <section className="chat-page">
        <Empty description="还没有已启用的模型，请先到模型管理中创建并启用模型" />
      </section>
    );
  }

  return (
    <section className="chat-page">
      <Flex justify="space-between" align="center" gap={24} className="chat-page-heading">
        <div>
          <Space align="center">
            <MessageSquare aria-hidden="true" className="chat-title-icon" size={22} strokeWidth={1.75} />
            <Title level={2}>AI 会话</Title>
          </Space>
          <Typography.Paragraph type="secondary">
            可直接使用通用 AI，也可选择数字员工并自动检索其绑定的知识库。
          </Typography.Paragraph>
        </div>
        <Select
          aria-label="选择数字员工"
          value={selectedEmployee?.id ?? GENERIC_CHAT_VALUE}
          showSearch
          filterOption={false}
          searchValue={controller.employeeSearch}
          options={[
            { value: GENERIC_CHAT_VALUE, label: "通用 AI" },
            ...employeeItems.map((employee) => ({
              value: employee.id,
              label: employee.name,
            })),
          ]}
          onSearch={controller.setEmployeeSearch}
          onPopupScroll={(event) => {
            const target = event.currentTarget;
            if (
              employees.hasNextPage &&
              !employees.isFetchingNextPage &&
              target.scrollTop + target.clientHeight >= target.scrollHeight - 16
            ) {
              void employees.fetchNextPage();
            }
          }}
          onChange={controller.selectEmployee}
          className="chat-employee-select"
        />
      </Flex>

      {employees.isError && (
        <Alert
          type="warning"
          showIcon
          title="数字员工加载失败，通用 AI 仍可使用"
          description={getErrorMessage(employees.error)}
          action={<Button onClick={() => void employees.refetch()}>重试加载</Button>}
          className="chat-inline-alert"
        />
      )}

      {controller.operationError && (
        <Alert
          type="error"
          showIcon
          closable
          title="会话操作失败"
          description={
            controller.deleteMutation.isError
              ? getResourceDeletionErrorMessage(controller.deleteMutation.error)
              : getErrorMessage(controller.operationError)
          }
          className="chat-inline-alert"
        />
      )}
      {controller.deleteNotice && (
        <Alert
          type="success"
          showIcon
          closable
          title={controller.deleteNotice}
          className="chat-inline-alert"
        />
      )}
      {controller.streamNotice && (
        <Alert
          type="warning"
          showIcon
          title={controller.streamNotice}
          className="chat-inline-alert"
        />
      )}
      <ChatWorkspace controller={controller} employee={selectedEmployee} readOnly={readOnly} />
    </section>
  );
}
