import { CheckCircleOutlined, CloseCircleOutlined, SyncOutlined } from "@ant-design/icons";
import { Space, Tag, Tooltip } from "antd";
import { useQuery } from "@tanstack/react-query";

import { fetchSystemStatus } from "../api/system";

export function SystemStatus() {
  const status = useQuery({
    queryKey: ["system", "status"],
    queryFn: fetchSystemStatus,
    refetchInterval: 30_000,
  });

  if (status.isPending) {
    return (
      <Tag icon={<SyncOutlined spin />} color="processing">
        后端检查中
      </Tag>
    );
  }

  if (status.isError) {
    return (
      <Tooltip title="请确认本机 FastAPI 已启动，或稍后重试">
        <Tag icon={<CloseCircleOutlined />} color="error">
          后端不可用
        </Tag>
      </Tooltip>
    );
  }

  if (status.data.integration_mode === "demo") {
    return (
      <Space size={4} wrap>
        <Tooltip title={`API ${status.data.version} · 固定适配器，不代表真实外部服务`}>
          <Tag icon={<CheckCircleOutlined />} color="warning">
            演示模式
          </Tag>
        </Tooltip>
        <Tag color="warning">模型演示</Tag>
        <Tag color="warning">知识库演示</Tag>
      </Space>
    );
  }

  const knowledge = status.data.knowledge;
  const knowledgeTag =
    knowledge.availability === "available" ? (
      <Tooltip title={`RAGFlow ${knowledge.version ?? "版本未知"}`}>
        <Tag icon={<CheckCircleOutlined />} color="success">
          RAGFlow 正常
        </Tag>
      </Tooltip>
    ) : knowledge.availability === "not_configured" ? (
      <Tooltip title="请检查后端 RAGFlow 配置">
        <Tag icon={<CloseCircleOutlined />} color="warning">
          RAGFlow 未配置
        </Tag>
      </Tooltip>
    ) : (
      <Tooltip title={`知识库状态检查失败 · ${knowledge.error_code ?? "unknown"}`}>
        <Tag icon={<CloseCircleOutlined />} color="error">
          RAGFlow 不可用
        </Tag>
      </Tooltip>
    );

  return (
    <Space size={4} wrap>
      <Tooltip title={`API ${status.data.version}`}>
        <Tag icon={<CheckCircleOutlined />} color="success">
          后端正常
        </Tag>
      </Tooltip>
      <Tooltip title="百炼配置已装配；实时可用性以每次模型请求结果为准">
        <Tag color="processing">百炼已配置</Tag>
      </Tooltip>
      {knowledgeTag}
    </Space>
  );
}
