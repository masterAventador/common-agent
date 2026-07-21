import { CommentOutlined, ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Empty, Flex, Select, Skeleton, Space, Typography } from "antd";

import { getErrorMessage } from "../../api/errors";
import { getResourceDeletionErrorMessage } from "../../components/resourceDeletion";
import { ChatWorkspace } from "./ChatWorkspace";
import { useChatPageController } from "./useChatPageController";

const { Title } = Typography;

export function ChatPage({ readOnly = false }: { readOnly?: boolean }) {
  const controller = useChatPageController();
  const { employeeItems, employees, selectedEmployee } = controller;

  if (employees.isPending) {
    return (
      <section className="chat-page" aria-label="AI 会话加载中">
        <Skeleton active paragraph={{ rows: 10 }} />
      </section>
    );
  }
  if (employees.isError) {
    return (
      <section className="chat-page">
        <Alert
          type="error"
          showIcon
          title="数字员工加载失败"
          description={getErrorMessage(employees.error)}
          action={
            <Button icon={<ReloadOutlined />} onClick={() => void employees.refetch()}>
              重试加载
            </Button>
          }
        />
      </section>
    );
  }
  if (!selectedEmployee) {
    return (
      <section className="chat-page">
        <Empty description="还没有可用于会话的数字员工" />
      </section>
    );
  }

  return (
    <section className="chat-page">
      <Flex justify="space-between" align="center" gap={24} className="chat-page-heading">
        <div>
          <Space align="center">
            <CommentOutlined className="chat-title-icon" />
            <Title level={2}>AI 会话</Title>
          </Space>
          <Typography.Paragraph type="secondary">
            选择数字员工持续对话，绑定知识库后每次提问都会自动检索。
          </Typography.Paragraph>
        </div>
        <Select
          aria-label="选择数字员工"
          value={selectedEmployee.id}
          showSearch
          filterOption={false}
          searchValue={controller.employeeSearch}
          options={employeeItems.map((employee) => ({
            value: employee.id,
            label: employee.name,
          }))}
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
