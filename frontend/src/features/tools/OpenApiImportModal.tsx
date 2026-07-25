import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Flex,
  Input,
  Modal,
  Row,
  Space,
  Tag,
  Typography,
} from "antd";
import { useMemo, useState } from "react";

import { getErrorMessage } from "../../api/errors";
import {
  importManagedMcpOpenApi,
  parseManagedMcpCapabilityInput,
  previewManagedMcpOpenApi,
  type ManagedMcpCapabilityInput,
  type ManagedMcpOpenApiDraft,
  type ManagedMcpOpenApiPreview,
  type ManagedMcpSource,
} from "../../api/tools";

const { Paragraph, Text } = Typography;
const MAX_FILE_BYTES = 5 * 1024 * 1024;

type EditableDraft = Omit<ManagedMcpOpenApiDraft, "input_schema" | "parameter_bindings"> & {
  selected: boolean;
  inputSchemaText: string;
  parameterBindingsText: string;
};

function editableDraft(
  draft: ManagedMcpOpenApiDraft,
  existingNames: Set<string>,
): EditableDraft {
  return {
    ...draft,
    selected: !existingNames.has(draft.remote_name),
    inputSchemaText: JSON.stringify(draft.input_schema, null, 2),
    parameterBindingsText: JSON.stringify(draft.parameter_bindings, null, 2),
  };
}

function importInput(draft: EditableDraft): ManagedMcpCapabilityInput {
  let inputSchema: unknown;
  let parameterBindings: unknown;
  try {
    inputSchema = JSON.parse(draft.inputSchemaText) as unknown;
    parameterBindings = JSON.parse(draft.parameterBindingsText) as unknown;
  } catch {
    throw new Error(`${draft.operation_key} 的 JSON 编辑内容格式不合法`);
  }
  try {
    return parseManagedMcpCapabilityInput({
      remote_name: draft.remote_name,
      display_name: draft.display_name,
      description: draft.description,
      input_schema: inputSchema,
      method: draft.method,
      path_template: draft.path_template,
      parameter_bindings: parameterBindings,
      timeout_seconds: Number(draft.timeout_seconds),
      response_json_pointer: draft.response_json_pointer || null,
      enabled: draft.enabled,
    });
  } catch {
    throw new Error(`${draft.operation_key} 仍有未补全或不合法的能力字段`);
  }
}

export function OpenApiImportModal({
  source,
  open,
  onClose,
  onImported,
}: {
  source?: ManagedMcpSource;
  open: boolean;
  onClose: () => void;
  onImported: (count: number) => Promise<void> | void;
}) {
  const [file, setFile] = useState<File>();
  const [preview, setPreview] = useState<ManagedMcpOpenApiPreview>();
  const [drafts, setDrafts] = useState<EditableDraft[]>([]);
  const [pendingAction, setPendingAction] = useState<"preview" | "import">();
  const [error, setError] = useState<string>();
  const busy = pendingAction !== undefined;

  const selectedCount = useMemo(
    () => drafts.filter((draft) => draft.selected).length,
    [drafts],
  );

  const chooseFile = (nextFile?: File) => {
    setError(undefined);
    setPreview(undefined);
    setDrafts([]);
    if (!nextFile) {
      setFile(undefined);
      return;
    }
    if (!/\.(?:json|ya?ml)$/i.test(nextFile.name)) {
      setFile(undefined);
      setError("请选择 .json、.yaml 或 .yml 格式的 OpenAPI 文件");
      return;
    }
    if (nextFile.size > MAX_FILE_BYTES) {
      setFile(undefined);
      setError("OpenAPI 文件不能超过 5 MiB");
      return;
    }
    setFile(nextFile);
  };

  const patchDraft = (index: number, patch: Partial<EditableDraft>) => {
    setDrafts((current) =>
      current.map((draft, draftIndex) =>
        draftIndex === index ? { ...draft, ...patch } : draft,
      ),
    );
  };

  const runPrimaryAction = async () => {
    if (!source) return;
    setPendingAction(preview ? "import" : "preview");
    setError(undefined);
    try {
      if (!preview) {
        if (!file) throw new Error("请先选择 OpenAPI 文件");
        const result = await previewManagedMcpOpenApi(source.id, file);
        const existingNames = new Set(result.existing_remote_names);
        setPreview(result);
        setDrafts(result.drafts.map((draft) => editableDraft(draft, existingNames)));
      } else {
        const selected = drafts.filter((draft) => draft.selected);
        if (!selected.length) throw new Error("请至少选择一项接口能力");
        const imported = await importManagedMcpOpenApi(
          source.id,
          selected.map(importInput),
        );
        await onImported(imported.length);
        onClose();
      }
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setPendingAction(undefined);
    }
  };

  const existingNames = useMemo(
    () => new Set(preview?.existing_remote_names ?? []),
    [preview?.existing_remote_names],
  );

  return (
    <Modal
      open={open}
      width={980}
      title={`导入 OpenAPI · ${source?.name ?? ""}`}
      okText={preview ? "导入选中能力" : "解析文件"}
      cancelText="取消"
      confirmLoading={pendingAction === "import"}
      okButtonProps={{
        disabled: busy || (preview ? selectedCount === 0 : !file),
      }}
      onCancel={onClose}
      onOk={() => void runPrimaryAction()}
      mask={{ closable: !busy }}
      destroyOnHidden
    >
      <Space orientation="vertical" size={16} className="tools-full-width">
        <Alert
          type="info"
          showIcon
          title="只支持 OpenAPI 3.0/3.1 JSON 或 YAML；外部引用、循环引用和 YAML 别名会被拒绝。"
          description="来源 Base URL 和鉴权沿用当前托管 MCP。预览不会写入数据，最终只原子导入勾选项。"
        />
        <Input
          type="file"
          aria-label="选择 OpenAPI 文件"
          accept=".json,.yaml,.yml,application/json,application/yaml,text/yaml"
          disabled={busy}
          onChange={(event) => chooseFile(event.currentTarget.files?.[0])}
        />
        {preview ? (
          <>
            <Flex justify="space-between" align="center" gap={12} wrap>
              <div>
                <Text strong>{preview.title}</Text>
                {preview.version ? <Text type="secondary"> · {preview.version}</Text> : null}
              </div>
              <Tag color="blue">已解析 {drafts.length} 项接口</Tag>
            </Flex>
            <Paragraph type="secondary" className="tools-openapi-hint">
              已存在的 MCP 名称默认不选中。预览提示需在导入前补全，服务端会再次校验全部选中项。
            </Paragraph>
            <div className="tools-openapi-drafts">
              <Space orientation="vertical" size={12} className="tools-full-width">
                {drafts.map((draft, index) => {
                  const exists = existingNames.has(draft.remote_name);
                  return (
                    <Card
                      key={draft.operation_key}
                      size="small"
                      title={
                        <Checkbox
                          checked={draft.selected}
                          aria-label={`选择 ${draft.display_name}`}
                          onChange={(event) =>
                            patchDraft(index, { selected: event.target.checked })
                          }
                        >
                          {draft.display_name}
                        </Checkbox>
                      }
                      extra={
                        <Space>
                          <Tag>{draft.operation_key}</Tag>
                          {exists ? <Tag color="warning">名称已存在</Tag> : null}
                        </Space>
                      }
                    >
                      <Space orientation="vertical" size={10} className="tools-full-width">
                        {draft.issues.length ? (
                          <Alert type="warning" showIcon title={draft.issues.join("；")} />
                        ) : null}
                        <Row gutter={12}>
                          <Col span={12}>
                            <Text type="secondary">MCP 工具名称</Text>
                            <Input
                              aria-label={`MCP 工具名称 ${draft.operation_key}`}
                              value={draft.remote_name}
                              maxLength={128}
                              onChange={(event) =>
                                patchDraft(index, { remote_name: event.target.value })
                              }
                            />
                          </Col>
                          <Col span={12}>
                            <Text type="secondary">显示名称</Text>
                            <Input
                              aria-label={`显示名称 ${draft.operation_key}`}
                              value={draft.display_name}
                              maxLength={128}
                              onChange={(event) =>
                                patchDraft(index, { display_name: event.target.value })
                              }
                            />
                          </Col>
                        </Row>
                        <div>
                          <Text type="secondary">能力说明</Text>
                          <Input.TextArea
                            aria-label={`能力说明 ${draft.operation_key}`}
                            value={draft.description}
                            rows={2}
                            maxLength={1_000}
                            onChange={(event) =>
                              patchDraft(index, { description: event.target.value })
                            }
                          />
                        </div>
                        <Row gutter={12}>
                          <Col span={12}>
                            <Text type="secondary">输入 Schema JSON</Text>
                            <Input.TextArea
                              aria-label={`输入 Schema ${draft.operation_key}`}
                              value={draft.inputSchemaText}
                              rows={9}
                              className="tools-json-editor"
                              onChange={(event) =>
                                patchDraft(index, { inputSchemaText: event.target.value })
                              }
                            />
                          </Col>
                          <Col span={12}>
                            <Text type="secondary">参数映射 JSON</Text>
                            <Input.TextArea
                              aria-label={`参数映射 ${draft.operation_key}`}
                              value={draft.parameterBindingsText}
                              rows={9}
                              className="tools-json-editor"
                              onChange={(event) =>
                                patchDraft(index, {
                                  parameterBindingsText: event.target.value,
                                })
                              }
                            />
                          </Col>
                        </Row>
                        <Row gutter={12}>
                          <Col span={12}>
                            <Text type="secondary">响应 JSON Pointer</Text>
                            <Input
                              aria-label={`响应 JSON Pointer ${draft.operation_key}`}
                              value={draft.response_json_pointer ?? ""}
                              placeholder="可选，例如 /data"
                              onChange={(event) =>
                                patchDraft(index, {
                                  response_json_pointer: event.target.value || null,
                                })
                              }
                            />
                          </Col>
                          <Col span={12}>
                            <Text type="secondary">超时（秒）</Text>
                            <Input
                              type="number"
                              aria-label={`超时 ${draft.operation_key}`}
                              min={1}
                              max={300}
                              value={draft.timeout_seconds}
                              onChange={(event) =>
                                patchDraft(index, {
                                  timeout_seconds: Number(event.target.value),
                                })
                              }
                            />
                          </Col>
                        </Row>
                      </Space>
                    </Card>
                  );
                })}
              </Space>
            </div>
          </>
        ) : (
          <Text type="secondary">请选择从 Apifox 等工具导出的 OpenAPI 文件，再解析预览。</Text>
        )}
        {error ? <Alert type="error" showIcon title={error} /> : null}
        {preview ? (
          <Button onClick={() => chooseFile(undefined)} disabled={busy}>
            清空预览并重新选择
          </Button>
        ) : null}
      </Space>
    </Modal>
  );
}

