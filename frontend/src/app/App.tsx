import {
  ApartmentOutlined,
  CommentOutlined,
  DatabaseOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Button, Layout, Menu, Space, Tag, Typography } from "antd";
import { lazy, Suspense, type ReactNode } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { SystemStatus } from "../components/SystemStatus";
import { AuthGate } from "../features/auth/AuthProvider";
import { useAuth } from "../features/auth/authContext";

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

const entries = [
  {
    path: "/chat",
    label: "AI 会话",
    icon: <CommentOutlined />,
  },
  {
    path: "/employees",
    label: "数字员工",
    icon: <TeamOutlined />,
  },
  {
    path: "/knowledge-bases",
    label: "知识库",
    icon: <DatabaseOutlined />,
  },
  {
    path: "/workflows",
    label: "工作流",
    icon: <ApartmentOutlined />,
  },
] as const;

function menuItems(): Array<{ key: string; icon: ReactNode; label: ReactNode }> {
  return entries.map((entry) => ({
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

  return (
    <Layout className="app-layout">
      <Sider className="app-sider" width={232} theme="light">
        <div className="brand-block">
          <span className="brand-mark">CA</span>
          <div>
            <Typography.Text strong>Common Agent</Typography.Text>
            <Typography.Text className="brand-subtitle">AI 中台</Typography.Text>
          </div>
        </div>
        <Menu mode="inline" selectedKeys={[location.pathname]} items={menuItems()} />
      </Sider>
      <Layout>
        <Header className="app-header">
          <div>
            <Typography.Text strong>通用 Agent 中台</Typography.Text>
            <Typography.Text type="secondary" className="header-description">
              本机开发环境
            </Typography.Text>
          </div>
          <Space size={8}>
            <SystemStatus />
            <Tag color="processing">{auth.session?.email}</Tag>
            <Button size="small" loading={auth.busy} onClick={() => void auth.logout()}>
              退出登录
            </Button>
          </Space>
        </Header>
        <Content className="app-content">
          <Suspense fallback={<section className="entry-shell">页面加载中…</section>}>
            <Routes>
              <Route path="/" element={<Navigate to="/chat" replace />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/knowledge-bases" element={<KnowledgeBasesPage />} />
              <Route path="/employees" element={<EmployeesPage />} />
              <Route path="/workflows" element={<WorkflowsPage />} />
              <Route path="*" element={<Navigate to="/chat" replace />} />
            </Routes>
          </Suspense>
        </Content>
      </Layout>
    </Layout>
  );
}
