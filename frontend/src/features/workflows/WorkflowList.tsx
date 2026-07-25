import { Button, Empty, Flex, Input, Space, Typography } from "antd";
import { ChevronRight, Plus, Workflow as WorkflowIcon } from "lucide-react";

import type { Workflow } from "../../api/workflows";

const { Paragraph, Title } = Typography;

/** 工作流列表页：与设计稿一致的行式列表，点击某一行才进入画布设计器。 */
export function WorkflowList({
  workflows,
  search,
  readOnly,
  hasMore,
  loadingMore,
  onSearch,
  onLoadMore,
  onSelect,
  onCreate,
}: {
  workflows: Workflow[];
  search: string;
  readOnly: boolean;
  hasMore: boolean;
  loadingMore: boolean;
  onSearch: (value: string) => void;
  onLoadMore: () => void;
  onSelect: (workflow: Workflow) => void;
  onCreate: () => void;
}) {
  return (
    <>
      <Flex justify="space-between" align="flex-start" gap={24} className="workflows-heading">
        <div>
          <Space align="center">
            <Title level={2}>工作流</Title>
          </Space>
          <Paragraph type="secondary">
            可视化编排多步骤自动化任务，点击某个工作流进入画布编辑。
          </Paragraph>
        </div>
        <Button
          type="primary"
          icon={<Plus aria-hidden="true" size={16} />}
          aria-label="新建工作流"
          disabled={readOnly}
          onClick={onCreate}
        >
          新建工作流
        </Button>
      </Flex>

      <Input.Search
        aria-label="搜索工作流"
        allowClear
        value={search}
        placeholder="搜索工作流"
        className="workflow-list-search"
        onChange={(event) => onSearch(event.target.value)}
      />

      <div className="workflow-rows">
        {workflows.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有已保存工作流" />
        ) : (
          workflows.map((workflow) => (
            <button
              type="button"
              key={workflow.id}
              className="workflow-row"
              aria-label={`选择工作流 ${workflow.name}`}
              onClick={() => onSelect(workflow)}
            >
              <span className="workflow-row-icon" aria-hidden="true">
                <WorkflowIcon size={20} strokeWidth={1.7} />
              </span>
              <span className="workflow-row-main">
                <span className="workflow-row-name">{workflow.name}</span>
                <span className="workflow-row-desc">{workflow.description || "暂无描述"}</span>
              </span>
              <span className="workflow-row-meta">
                <span>
                  {workflow.nodes.length} 个节点 · {workflow.edges.length} 条连线
                </span>
                <span className="workflow-row-sub">
                  更新于 {new Date(workflow.updated_at).toLocaleDateString()}
                </span>
              </span>
              <ChevronRight aria-hidden="true" className="workflow-row-go" size={18} />
            </button>
          ))
        )}
      </div>
      {hasMore && (
        <Button block loading={loadingMore} onClick={onLoadMore}>
          加载更多工作流
        </Button>
      )}
    </>
  );
}
