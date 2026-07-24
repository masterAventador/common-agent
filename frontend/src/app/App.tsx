import {
  Alert,
  Button,
  Form,
  Input,
  Layout,
  Menu,
  Modal,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import {
  Bot,
  Boxes,
  Database,
  LogOut,
  MessageSquare,
  PanelsTopLeft,
  ShieldCheck,
  UserPlus,
  Workflow,
} from "lucide-react";
import { lazy, Suspense, useState, type ReactNode } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { BrandLogo } from "../components/BrandLogo";
import { getErrorMessage } from "../api/errors";
import {
  provisionTenantMember,
  type ProvisionedTenantMember,
  type ProvisionTenantMemberInput,
} from "../api/tenants";
import { AuthGate } from "../features/auth/AuthProvider";
import { useAuth } from "../features/auth/authContext";
import { ConversationHistory } from "../features/chat/ConversationHistory";

const { Content, Header, Sider } = Layout;
const KnowledgeBasesPage = lazy(async () => {
  const module = await import("../features/knowledge-bases/KnowledgeBasesPage");
  return { default: module.KnowledgeBasesPage };
});
const EmployeesPage = lazy(async () => {
  const module = await import("../features/employees/EmployeesPage");
  return { default: module.EmployeesPage };
});
const ChatPage = lazy(async () => {
  const module = await import("../features/chat/ChatPage");
  return { default: module.ChatPage };
});
const WorkflowsPage = lazy(async () => {
  const module = await import("../features/workflows/WorkflowsPage");
  return { default: module.WorkflowsPage };
});
const AuditEventsPage = lazy(async () => {
  const module = await import("../features/audit/AuditEventsPage");
  return { default: module.AuditEventsPage };
});
const ModelConfigurationsPage = lazy(async () => {
  const module = await import(
    "../features/model-configurations/ModelConfigurationsPage"
  );
  return { default: module.ModelConfigurationsPage };
});
const ToolsPage = lazy(() => import("../features/tools/ToolsPage"));

const entries = [
  {
    path: "/chat",
    label: "AI 会话",
    icon: <MessageSquare aria-hidden="true" size={18} strokeWidth={1.75} />,
  },
  {
    path: "/employees",
    label: "数字员工",
    icon: <Bot aria-hidden="true" size={18} strokeWidth={1.75} />,
  },
  {
    path: "/knowledge-bases",
    label: "知识库",
    icon: <Database aria-hidden="true" size={18} strokeWidth={1.75} />,
  },
  {
    path: "/workflows",
    label: "工作流",
    icon: <Workflow aria-hidden="true" size={18} strokeWidth={1.75} />,
  },
  {
    path: "/tools",
    label: "工具与 MCP",
    icon: <PanelsTopLeft aria-hidden="true" size={18} strokeWidth={1.75} />,
  },
  {
    path: "/model-configurations",
    label: "模型管理",
    icon: <Boxes aria-hidden="true" size={18} strokeWidth={1.75} />,
  },
  {
    path: "/audit-events",
    label: "审计与安全事件",
    icon: <ShieldCheck aria-hidden="true" size={18} strokeWidth={1.75} />,
    ownerOnly: true,
  },
] as const;

function menuItems(owner: boolean): Array<{ key: string; icon: ReactNode; label: ReactNode }> {
  return entries.filter((entry) => !("ownerOnly" in entry) || owner).map((entry) => ({
    key: entry.path,
    icon: entry.icon,
    label: <Link to={entry.path}>{entry.label}</Link>,
  }));
}

export function App() {
  return (
    <AuthGate>
      <AuthenticatedApp />
    </AuthGate>
  );
}

function AuthenticatedApp() {
  const location = useLocation();
  const auth = useAuth();
  const [workspaceModalOpen, setWorkspaceModalOpen] = useState(false);
  const [workspaceForm] = Form.useForm<{ name: string }>();
  const [memberModalOpen, setMemberModalOpen] = useState(false);
  const [memberForm] = Form.useForm<ProvisionTenantMemberInput>();
  const [memberBusy, setMemberBusy] = useState(false);
  const [memberError, setMemberError] = useState<string>();
  const [provisionedMember, setProvisionedMember] =
    useState<ProvisionedTenantMember>();
  const selectedTenant = auth.tenants.find(
    (tenant) => tenant.id === auth.selectedTenantId,
  );
  const roleLabels = { owner: "所有者", editor: "编辑者", viewer: "访客" } as const;
  const currentEntry = entries.find((entry) => entry.path === location.pathname);
  const isOwner = selectedTenant?.role === "owner";
  const isViewer = selectedTenant?.role === "viewer";

  const submitWorkspace = async ({ name }: { name: string }) => {
    if (await auth.createWorkspace(name)) {
      workspaceForm.resetFields();
      setWorkspaceModalOpen(false);
    }
  };

  const submitMember = async (input: ProvisionTenantMemberInput) => {
    if (!selectedTenant) return;
    setMemberBusy(true);
    setMemberError(undefined);
    try {
      const provisioned = await provisionTenantMember(selectedTenant.id, input);
      memberForm.resetFields();
      setMemberModalOpen(false);
      setProvisionedMember(provisioned);
    } catch (error) {
      setMemberError(getErrorMessage(error));
    } finally {
      setMemberBusy(false);
    }
  };

  return (
    <Layout className="app-layout">
      <Sider className="app-sider" width={232} theme="light">
        <Link to="/chat" className="brand-block" aria-label="Common Agent 首页">
          <span className="brand-logo-tile">
            <BrandLogo size={28} />
          </span>
          <div className="brand-copy">
            <Typography.Text strong>Common Agent</Typography.Text>
            <Typography.Text className="brand-subtitle">AI 中台</Typography.Text>
          </div>
        </Link>
        <nav aria-label="主导航" className="app-navigation">
          <Menu
            mode="inline"
            selectedKeys={[location.pathname]}
            items={menuItems(isOwner)}
          />
        </nav>
        <ConversationHistory readOnly={isViewer} />
      </Sider>
      <Layout>
        <Header className="app-header">
          <div className="app-header-context">
            <Typography.Text className="header-description">WORKSPACE</Typography.Text>
            <Typography.Text strong>{currentEntry?.label ?? "Common Agent"}</Typography.Text>
          </div>
          <Space size={8} wrap className="app-header-actions">
            <Select
              aria-label="当前工作区"
              value={auth.selectedTenantId ?? undefined}
              options={auth.tenants.map((tenant) => ({
                value: tenant.id,
                label: `${tenant.name} · ${roleLabels[tenant.role]}`,
              }))}
              onChange={auth.selectTenant}
              popupMatchSelectWidth={false}
            />
            {selectedTenant ? (
              <Tag color={selectedTenant.role === "viewer" ? "default" : "blue"}>
                {roleLabels[selectedTenant.role]}
              </Tag>
            ) : null}
            {isOwner ? (
              <>
                <Button
                  size="small"
                  icon={<UserPlus aria-hidden="true" size={15} />}
                  onClick={() => setMemberModalOpen(true)}
                >
                  添加成员
                </Button>
                <Button
                  size="small"
                  icon={<PanelsTopLeft aria-hidden="true" size={15} />}
                  onClick={() => setWorkspaceModalOpen(true)}
                >
                  新建工作区
                </Button>
              </>
            ) : null}
            <Tag color="processing">{auth.session?.email}</Tag>
            <Button
              size="small"
              icon={<LogOut aria-hidden="true" size={15} />}
              loading={auth.busy}
              onClick={() => void auth.logout()}
            >
              退出登录
            </Button>
          </Space>
        </Header>
        <Content className="app-content">
          {isViewer ? (
            <Alert
              type="info"
              showIcon
              title="当前工作区为只读模式"
              className="tenant-readonly-alert"
            />
          ) : null}
          <Suspense fallback={<section className="entry-shell">页面加载中…</section>}>
            <Routes>
              <Route path="/" element={<Navigate to="/chat" replace />} />
              <Route path="/chat" element={<ChatPage readOnly={isViewer} />} />
              <Route
                path="/knowledge-bases"
                element={<KnowledgeBasesPage readOnly={isViewer} />}
              />
              <Route
                path="/employees"
                element={<EmployeesPage readOnly={isViewer} />}
              />
              <Route
                path="/workflows"
                element={<WorkflowsPage readOnly={isViewer} />}
              />
              <Route
                path="/model-configurations"
                element={
                  <ModelConfigurationsPage readOnly={isViewer} />
                }
              />
              <Route
                path="/tools"
                element={<ToolsPage readOnly={isViewer} />}
              />
              <Route
                path="/audit-events"
                element={
                  isOwner ? (
                    <AuditEventsPage />
                  ) : (
                    <Navigate to="/chat" replace />
                  )
                }
              />
              <Route path="*" element={<Navigate to="/chat" replace />} />
            </Routes>
          </Suspense>
        </Content>
      </Layout>
      <Modal
        open={workspaceModalOpen}
        title="新建工作区"
        okText="创建"
        cancelText="取消"
        confirmLoading={auth.busy}
        onCancel={() => setWorkspaceModalOpen(false)}
        onOk={() => workspaceForm.submit()}
        destroyOnHidden
      >
        <Form form={workspaceForm} layout="vertical" onFinish={submitWorkspace}>
          <Form.Item
            label="工作区名称"
            name="name"
            rules={[{ required: true, whitespace: true, max: 100 }]}
          >
            <Input autoFocus />
          </Form.Item>
          {auth.error ? <Alert type="error" showIcon title={auth.error} /> : null}
        </Form>
      </Modal>
      <Modal
        open={memberModalOpen}
        title="添加工作区成员"
        okText="创建账号"
        cancelText="取消"
        confirmLoading={memberBusy}
        onCancel={() => {
          setMemberModalOpen(false);
          setMemberError(undefined);
          memberForm.resetFields();
        }}
        onOk={() => memberForm.submit()}
        destroyOnHidden
      >
        <Form<ProvisionTenantMemberInput>
          form={memberForm}
          layout="vertical"
          initialValues={{ role: "viewer" }}
          onFinish={submitMember}
        >
          <Form.Item label="邮箱" name="email" rules={[{ required: true, type: "email" }]}>
            <Input autoComplete="username" />
          </Form.Item>
          <Form.Item
            label="初始密码"
            name="password"
            rules={[{ required: true, min: 8, max: 128 }]}
            extra="至少 8 个字符；成员首次登录后可用恢复码重置。"
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item label="角色" name="role" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "editor", label: "编辑者：可查看并修改业务资源" },
                { value: "viewer", label: "访客：仅可查看" },
              ]}
            />
          </Form.Item>
          {memberError ? <Alert type="error" showIcon title={memberError} /> : null}
        </Form>
      </Modal>
      <Modal
        open={Boolean(provisionedMember)}
        title="成员账号已创建"
        closable={false}
        mask={{ closable: false }}
        footer={
          <Button type="primary" onClick={() => setProvisionedMember(undefined)}>
            我已保存
          </Button>
        }
      >
        <Alert
          type="warning"
          showIcon
          title="请通过安全渠道把初始密码和恢复码交给成员；恢复码只显示一次。"
        />
        <Typography.Paragraph copyable>
          {provisionedMember?.email}
        </Typography.Paragraph>
        <pre className="auth-recovery-codes">
          {provisionedMember?.recovery_codes.join("\n")}
        </pre>
      </Modal>
    </Layout>
  );
}
