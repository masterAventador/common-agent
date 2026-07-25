import { Alert, Button, Empty, Flex, Select, Skeleton, Space, Typography } from "antd";
import { RefreshCw } from "lucide-react";

import { getErrorMessage } from "../../api/errors";
import { ChatWorkspace } from "./ChatWorkspace";
import { GENERIC_CHAT_VALUE, useChatPageController } from "./useChatPageController";

const { Title } = Typography;

export function ChatPage({ readOnly = false }: { readOnly?: boolean }) {
  const controller = useChatPageController();
  const { employeeItems, employees, modelConfigurations, selectedEmployee } = controller;

  if (
    modelConfigurations.isPending ||
    controller.contextModelConfiguration.isFetching ||
    (Boolean(controller.selectedConversationId) && controller.selectedConversationQuery.isPending) ||
    (Boolean(controller.selectedEmployeeId) && controller.selectedEmployeeQuery.isPending)
  ) {
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
  if (controller.contextModelConfiguration.isError) {
    return (
      <section className="chat-page">
        <Alert
          type="error"
          showIcon
          title="当前会话模型加载失败"
          description={getErrorMessage(controller.contextModelConfiguration.error)}
          action={
            <Button
              icon={<RefreshCw aria-hidden="true" size={16} />}
              onClick={() => void controller.contextModelConfiguration.refetch()}
            >
              重试加载
            </Button>
          }
        />
      </section>
    );
  }
  if (controller.selectedConversationQuery.isError || controller.selectedEmployeeQuery.isError) {
    const employeeUnavailable = controller.selectedEmployeeQuery.isError;
    return (
      <section className="chat-page">
        <Alert
          type="error"
          showIcon
          title={employeeUnavailable ? "会话关联的数字员工不可用" : "历史会话加载失败"}
          description={getErrorMessage(
            employeeUnavailable
              ? controller.selectedEmployeeQuery.error
              : controller.selectedConversationQuery.error,
          )}
          action={
            <Button onClick={() => controller.selectEmployee(GENERIC_CHAT_VALUE)}>
              返回通用 AI
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
          description={getErrorMessage(controller.operationError)}
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
