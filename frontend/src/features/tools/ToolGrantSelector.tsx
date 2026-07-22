import { Alert, Select, Space, Tag, Typography } from "antd";
import { useMemo } from "react";

import type { ToolCatalog, ToolGrantSelection } from "../../api/tools";
import { implicitCapabilityIds } from "./toolGrants";

const { Text } = Typography;

export function ToolGrantSelector({
  catalog,
  value,
  disabled = false,
  onChange,
}: {
  catalog: ToolCatalog;
  value: ToolGrantSelection;
  disabled?: boolean;
  onChange: (selection: ToolGrantSelection) => void;
}) {
  const sourcesById = useMemo(
    () => new Map(catalog.sources.map((source) => [source.id, source])),
    [catalog.sources],
  );
  const implicit = useMemo(
    () => implicitCapabilityIds(catalog, value.collection_ids),
    [catalog, value.collection_ids],
  );
  const finalIds = new Set([...implicit, ...value.capability_ids]);
  const unavailableSelected = value.capability_ids.filter((id) => {
    const capability = catalog.capabilities.find((item) => item.id === id);
    const source = capability ? sourcesById.get(capability.source_id) : undefined;
    return !capability || capability.status !== "active" || source?.status !== "ready";
  });

  return (
    <Space orientation="vertical" size={12} className="tools-full-width">
      <div>
        <Text strong>业务工具集</Text>
        <Select
          aria-label="业务工具集"
          mode="multiple"
          allowClear
          value={value.collection_ids}
          disabled={disabled}
          placeholder="不授权整个工具集"
          options={catalog.collections.map((collection) => ({
            value: collection.id,
            label: collection.name,
            title: collection.name,
          }))}
          onChange={(collectionIds) =>
            onChange({ ...value, collection_ids: collectionIds })
          }
          maxTagCount="responsive"
          className="tools-full-width"
        />
      </div>
      <div>
        <Text strong>单项工具能力</Text>
        <Select
          aria-label="单项工具能力"
          mode="multiple"
          allowClear
          value={value.capability_ids}
          disabled={disabled}
          placeholder="按需追加单项能力"
          options={catalog.capabilities.map((capability) => {
            const source = sourcesById.get(capability.source_id);
            const available = capability.status === "active" && source?.status === "ready";
            const label = `${capability.display_name} · ${source?.name ?? "未知来源"}`;
            return {
              value: capability.id,
              label: available ? label : `${label}（当前不可用）`,
              title: label,
              disabled: !available,
            };
          })}
          onChange={(capabilityIds) =>
            onChange({ ...value, capability_ids: capabilityIds })
          }
          maxTagCount="responsive"
          className="tools-full-width"
        />
      </div>
      <Space wrap>
        <Tag color={finalIds.size ? "blue" : "default"}>最终授权 {finalIds.size} 项</Tag>
        {implicit.size ? <Tag>工具集展开 {implicit.size} 项</Tag> : null}
      </Space>
      {unavailableSelected.length ? (
        <Alert
          type="warning"
          showIcon
          title={`${unavailableSelected.length} 项既有授权当前不可用；取消选择后将明确撤权`}
        />
      ) : null}
      <Text type="secondary">
        工具集只在保存时展开当前可用能力；以后新增能力不会自动授权。
      </Text>
    </Space>
  );
}
