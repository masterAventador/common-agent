import { CheckCircleOutlined, CloseCircleOutlined, SyncOutlined } from "@ant-design/icons";
import { Tag, Tooltip } from "antd";
import { useQuery } from "@tanstack/react-query";

import { fetchHealth } from "../api/system";

export function SystemStatus() {
  const health = useQuery({
    queryKey: ["system", "health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  });

  if (health.isPending) {
    return (
      <Tag icon={<SyncOutlined spin />} color="processing">
        后端检查中
      </Tag>
    );
  }

  if (health.isError) {
    return (
      <Tooltip title="请确认本机 FastAPI 已启动，或稍后重试">
        <Tag icon={<CloseCircleOutlined />} color="error">
          后端不可用
        </Tag>
      </Tooltip>
    );
  }

  if (health.data.integration_mode === "demo") {
    return (
      <Tooltip title={`API ${health.data.version} · 固定适配器，不代表真实外部服务`}>
        <Tag icon={<CheckCircleOutlined />} color="warning">
          演示模式
        </Tag>
      </Tooltip>
    );
  }

  return (
    <Tooltip title={`API ${health.data.version}`}>
      <Tag icon={<CheckCircleOutlined />} color="success">
        后端正常
      </Tag>
    </Tooltip>
  );
}
