import { DeleteOutlined } from "@ant-design/icons";
import { Button, Modal, Typography, type ButtonProps } from "antd";
import { useState, type ReactNode } from "react";

export function ResourceDeleteButton({
  resourceKind,
  resourceName,
  impact,
  onConfirm,
  disabled,
  loading,
  size,
  compact = false,
}: {
  resourceKind: string;
  resourceName: string;
  impact: ReactNode;
  onConfirm: () => Promise<unknown>;
  disabled?: boolean;
  loading?: boolean;
  size?: ButtonProps["size"];
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const accessibleName = `删除${resourceKind} ${resourceName}`;
  const confirmAccessibleName = `确认删除${resourceKind} ${resourceName}`;

  const confirmDeletion = async () => {
    setConfirming(true);
    try {
      await onConfirm();
    } catch {
      // Mutation state renders the stable, actionable error after the dialog closes.
    } finally {
      setConfirming(false);
      setOpen(false);
    }
  };

  return (
    <>
      <Button
        danger
        type={compact ? "text" : "default"}
        size={size}
        icon={<DeleteOutlined />}
        aria-label={accessibleName}
        title={accessibleName}
        disabled={disabled}
        loading={loading}
        onClick={() => setOpen(true)}
      >
        {compact ? null : "删除"}
      </Button>
      <Modal
        title={`删除${resourceKind}“${resourceName}”？`}
        open={open}
        okText="确认删除"
        cancelText="取消"
        okButtonProps={{ danger: true, "aria-label": confirmAccessibleName }}
        cancelButtonProps={{ autoFocus: true, disabled: confirming }}
        confirmLoading={confirming}
        closable={!confirming}
        keyboard={!confirming}
        mask={{ closable: !confirming }}
        onOk={() => void confirmDeletion()}
        onCancel={() => setOpen(false)}
        destroyOnHidden
      >
        <div>
          <Typography.Paragraph>{impact}</Typography.Paragraph>
          <Typography.Text type="danger">此操作不可恢复。</Typography.Text>
        </div>
      </Modal>
    </>
  );
}
