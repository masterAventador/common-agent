import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Divider, Empty, Skeleton, Typography } from "antd";
import { History } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import {
  deleteConversation,
  fetchConversations,
  type ConversationHistoryItem,
} from "../../api/conversations";
import { getErrorMessage } from "../../api/errors";
import { flattenCursorPages, nextPageCursor } from "../../api/pagination";
import { ResourceDeleteButton } from "../../components/ResourceDeleteButton";
import { getResourceDeletionErrorMessage } from "../../components/resourceDeletion";

const HISTORY_PAGE_SIZE = 10;

export function ConversationHistory({ readOnly = false }: { readOnly?: boolean }) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const history = useInfiniteQuery({
    queryKey: ["conversations", "history"],
    queryFn: ({ pageParam }) =>
      fetchConversations(undefined, { limit: HISTORY_PAGE_SIZE, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: nextPageCursor,
  });
  const items = flattenCursorPages(history.data);
  const selectedConversationId = new URLSearchParams(location.search).get("conversation_id");
  const deletion = useMutation({
    mutationFn: (conversation: ConversationHistoryItem) => deleteConversation(conversation.id),
    onSuccess: async (_, conversation) => {
      queryClient.removeQueries({ queryKey: ["conversation", conversation.id], exact: true });
      queryClient.removeQueries({
        queryKey: ["conversation-messages", conversation.id],
        exact: true,
      });
      queryClient.removeQueries({
        queryKey: ["conversation-workflow-runs", conversation.id],
        exact: true,
      });
      if (selectedConversationId === conversation.id) navigate("/chat");
      await queryClient.resetQueries({ queryKey: ["conversations"] });
    },
  });

  return (
    <section className="app-conversation-history" role="region" aria-label="历史会话">
      <Divider />
      <div className="app-history-heading">
        <History aria-hidden="true" size={15} />
        <Typography.Text strong>历史会话</Typography.Text>
      </div>
      {history.isPending ? (
        <Skeleton active paragraph={{ rows: 4 }} title={false} />
      ) : history.isError ? (
        <Alert
          type="error"
          showIcon
          title="历史会话加载失败"
          description={getErrorMessage(history.error)}
          action={<Button onClick={() => void history.refetch()}>重试</Button>}
        />
      ) : items.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无历史会话" />
      ) : (
        <div className="app-history-list">
          {items.map((conversation) => (
            <div
              key={conversation.id}
              className={`app-history-item ${
                selectedConversationId === conversation.id ? "is-active" : ""
              }`}
            >
              <Link
                to={conversationHref(conversation)}
                aria-label={`打开会话 ${conversation.title}`}
                className="app-history-link"
              >
                <Typography.Text ellipsis>{conversation.title}</Typography.Text>
                <Typography.Text type="secondary" ellipsis>
                  {conversationAttribution(conversation)}
                </Typography.Text>
              </Link>
              <ResourceDeleteButton
                resourceKind="会话"
                resourceName={conversation.title}
                impact="消息、引用及工作流运行将永久删除。"
                compact
                size="small"
                disabled={readOnly || deletion.isPending}
                loading={deletion.isPending && deletion.variables?.id === conversation.id}
                onConfirm={() => deletion.mutateAsync(conversation)}
              />
            </div>
          ))}
          {history.hasNextPage ? (
            <Button
              block
              size="small"
              loading={history.isFetchingNextPage}
              onClick={() => void history.fetchNextPage()}
            >
              加载更多历史会话
            </Button>
          ) : null}
        </div>
      )}
      {deletion.isError ? (
        <Alert
          type="error"
          showIcon
          title="会话删除失败"
          description={getResourceDeletionErrorMessage(deletion.error)}
        />
      ) : (
        deletion.isSuccess && `会话“${deletion.variables.title}”已删除`
      )}
    </section>
  );
}

function conversationHref(conversation: ConversationHistoryItem): string {
  const params = new URLSearchParams({ conversation_id: conversation.id });
  if (conversation.source === "employee" && conversation.employee_id) {
    params.set("employee_id", conversation.employee_id);
  }
  return `/chat?${params}`;
}

function conversationAttribution(conversation: ConversationHistoryItem): string {
  if (conversation.source === "generic") return "通用 AI";
  return conversation.employee_name ?? "数字员工不可用";
}
