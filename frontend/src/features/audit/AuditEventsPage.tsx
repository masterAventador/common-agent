import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Flex,
  Form,
  Input,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";
import { ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";

import {
  auditActionSchema,
  auditResourceTypeSchema,
  fetchAuditEvents,
  fetchAuditIntegrity,
  fetchAuditPolicy,
  type AuditAction,
  type AuditQuery,
  type AuditScope,
} from "../../api/audit";
import { getErrorMessage } from "../../api/errors";

const { Text, Title } = Typography;

const actionLabels: Record<AuditAction, string> = {
  "auth.register": "首位所有者注册",
  "auth.login": "登录",
  "auth.logout": "退出登录",
  "auth.recovery.reset": "凭据恢复",
  "auth.member.provisioned": "成员账号创建",
  "tenant.created": "工作区创建",
  "employee.created": "数字员工创建",
  "employee.configuration_and_bindings.updated": "数字员工配置与绑定已更新",
  "tool.grants.updated": "工具精确授权已更新",
  "tool.credentials.updated": "MCP 凭据已更新",
  "tool.called": "工具调用",
  "model.configuration.created": "模型配置创建",
  "model.configuration.updated": "模型配置更新",
  "model.configuration.verified": "模型调用验证",
  "knowledge.base.created": "知识库创建",
  "knowledge.document.uploaded": "知识文档上传",
  "knowledge.document.retry_started": "知识文档解析重试",
  "resource.deleted": "资源删除",
  "conversation.reply.started": "会话回复启动",
  "workflow.configuration.updated": "工作流配置更新",
  "workflow.run.started": "工作流运行启动",
  "workflow.run.stopped": "工作流运行停止",
  "security.permission.denied": "权限拒绝",
  "security.request.denied": "安全请求拒绝",
};

type FilterValues = Omit<AuditQuery, "cursor" | "limit">;

export function AuditEventsPage() {
  const [filters, setFilters] = useState<FilterValues>({});
  const scope: AuditScope = filters.scope ?? "tenant";
  const events = useInfiniteQuery({
    queryKey: ["audit-events", filters],
    queryFn: ({ pageParam }) =>
      fetchAuditEvents({ ...filters, cursor: pageParam, limit: 50 }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
  });
  const integrity = useQuery({
    queryKey: ["audit-integrity", scope],
    queryFn: () => fetchAuditIntegrity(scope),
  });
  const policy = useQuery({ queryKey: ["audit-policy"], queryFn: fetchAuditPolicy });
  const items = useMemo(
    () => events.data?.pages.flatMap((page) => page.items) ?? [],
    [events.data],
  );

  return (
    <section className="audit-page">
      <Flex justify="space-between" align="flex-start" gap={24}>
        <div>
          <Space align="center">
            <ShieldCheck aria-hidden="true" size={22} strokeWidth={1.75} />
            <Title level={2}>审计与安全事件</Title>
          </Space>
          <Typography.Paragraph type="secondary">
            只记录固定业务元数据；请求正文、密码、Token 和一次性恢复码不会进入审计事件。
          </Typography.Paragraph>
        </div>
        <Space>
          {integrity.data ? (
            <Tag color={integrity.data.verified ? "success" : "error"}>
              {integrity.data.verified ? "哈希链完整" : "哈希链异常"}
            </Tag>
          ) : null}
          <Button loading={integrity.isFetching} onClick={() => void integrity.refetch()}>
            重新校验
          </Button>
        </Space>
      </Flex>

      {policy.data ? (
        <Alert
          type="info"
          showIcon
          title={`至少保留 ${policy.data.retention_days} 天；单工作区最多 ${policy.data.max_events_per_scope.toLocaleString()} 条；自动删除关闭。`}
        />
      ) : null}
      {!integrity.isPending && integrity.data && !integrity.data.verified ? (
        <Alert type="error" showIcon title="审计链完整性校验失败，请停止敏感操作并调查。" />
      ) : null}

      <Card className="audit-filter-card">
        <Form<FilterValues>
          layout="inline"
          initialValues={{ scope: "tenant" }}
          onFinish={(values) => setFilters(cleanFilters(values))}
        >
          <Form.Item name="scope" label="审计范围">
            <Select
              aria-label="审计范围"
              style={{ minWidth: 160 }}
              options={[
                { value: "tenant", label: "当前工作区事件" },
                { value: "platform", label: "平台安全事件" },
              ]}
            />
          </Form.Item>
          <Form.Item name="actor_user_id" label="操作者">
            <Input aria-label="操作者 ID" placeholder="用户 UUID" allowClear />
          </Form.Item>
          <Form.Item name="action" label="事件">
            <Select
              aria-label="事件类型"
              allowClear
              style={{ minWidth: 180 }}
              options={auditActionSchema.options.map((value) => ({
                value,
                label: actionLabels[value],
              }))}
              popupMatchSelectWidth={false}
            />
          </Form.Item>
          <Form.Item name="resource_type" label="资源类型">
            <Select
              aria-label="资源类型"
              allowClear
              style={{ minWidth: 160 }}
              options={auditResourceTypeSchema.options.map((value) => ({ value, label: value }))}
            />
          </Form.Item>
          <Form.Item name="resource_id" label="资源 ID">
            <Input aria-label="资源 ID" allowClear />
          </Form.Item>
          <Form.Item name="occurred_from" label="开始时间">
            <Input type="datetime-local" aria-label="开始时间" />
          </Form.Item>
          <Form.Item name="occurred_to" label="结束时间">
            <Input type="datetime-local" aria-label="结束时间" />
          </Form.Item>
          <Button type="primary" htmlType="submit">查询</Button>
        </Form>
      </Card>

      {events.isPending ? <Skeleton active paragraph={{ rows: 6 }} /> : null}
      {events.isError ? (
        <Alert
          type="error"
          showIcon
          title="审计事件加载失败"
          description={getErrorMessage(events.error)}
          action={<Button onClick={() => void events.refetch()}>重试</Button>}
        />
      ) : null}
      {!events.isPending && !events.isError && items.length === 0 ? (
        <Card><Text type="secondary">当前筛选条件下没有审计事件。</Text></Card>
      ) : null}
      <div className="audit-event-list">
        {items.map((event) => (
          <Card key={event.event_id} size="small">
            <Flex justify="space-between" gap={16} wrap>
              <Space wrap>
                <Text strong>{`#${event.sequence}`}</Text>
                <Text>{actionLabels[event.action]}</Text>
                <Tag color={outcomeColor(event.outcome)}>{outcomeLabel(event.outcome)}</Tag>
              </Space>
              <Text type="secondary">{new Date(event.occurred_at).toLocaleString()}</Text>
            </Flex>
            <div className="audit-event-metadata">
              <Text type="secondary">操作者</Text>
              <Text code>{event.actor_user_id ?? "平台/匿名"}</Text>
              <Text type="secondary">资源</Text>
              <Text code>{event.resource_id ?? "无"}</Text>
              <Text type="secondary">请求</Text>
              <Text code>{event.request_id}</Text>
              {event.error_code ? <Tag color="error">{event.error_code}</Tag> : null}
            </div>
          </Card>
        ))}
      </div>
      {events.hasNextPage ? (
        <Button
          block
          loading={events.isFetchingNextPage}
          onClick={() => void events.fetchNextPage()}
        >
          加载更早事件
        </Button>
      ) : null}
    </section>
  );
}

function cleanFilters(values: FilterValues): FilterValues {
  const filtered = Object.fromEntries(
    Object.entries(values).filter(([, value]) => value !== undefined && value !== ""),
  ) as FilterValues;
  return {
    ...filtered,
    occurred_from: toIsoDatetime(filtered.occurred_from),
    occurred_to: toIsoDatetime(filtered.occurred_to),
  };
}

function toIsoDatetime(value: string | undefined): string | undefined {
  return value === undefined ? undefined : new Date(value).toISOString();
}

type AuditOutcome = "started" | "succeeded" | "denied" | "failed";

function outcomeColor(outcome: AuditOutcome): string {
  if (outcome === "started") return "processing";
  if (outcome === "succeeded") return "success";
  if (outcome === "denied") return "warning";
  return "error";
}

function outcomeLabel(outcome: AuditOutcome): string {
  if (outcome === "started") return "待核对";
  if (outcome === "succeeded") return "成功";
  if (outcome === "denied") return "已拒绝";
  return "失败";
}
