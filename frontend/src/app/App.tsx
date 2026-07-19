import {
  ApartmentOutlined,
  CommentOutlined,
  DatabaseOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Layout, Menu, Space, Tag, Typography } from "antd";
import { lazy, Suspense, type ReactNode } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { SystemStatus } from "../components/SystemStatus";

const { Content, Header, Sider } = Layout;
const KnowledgeBasesPage = lazy(async () => {
  const module = await import("../features/knowledge-bases/KnowledgeBasesPage");
  return { default: module.KnowledgeBasesPage };
});

const entries = [
  {
    path: "/chat",
    label: "AI 会话",
    icon: <CommentOutlined />,
    description: "与数字员工连续对话，并在绑定知识库后自动检索。",
  },
  {
    path: "/employees",
    label: "数字员工",
    icon: <TeamOutlined />,
    description: "配置数字员工的指令、知识库和允许调用的工作流。",
  },
  {
    path: "/knowledge-bases",
    label: "知识库",
    icon: <DatabaseOutlined />,
    description: "创建 RAGFlow 知识库、上传文档并查看真实解析状态。",
  },
  {
    path: "/workflows",
    label: "工作流",
    icon: <ApartmentOutlined />,
    description: "拖拽节点形成独立流程，并支持手动或数字员工触发。",
  },
] as const;

function EntryShell({ title, description }: { title: string; description: string }) {
  return (
    <section className="entry-shell">
      <Space orientation="vertical" size={12}>
        <Tag color="blue">工程基线</Tag>
        <Typography.Title level={2}>{title}</Typography.Title>
        <Typography.Paragraph type="secondary">{description}</Typography.Paragraph>
        <Typography.Text type="secondary">
          当前页面只验证正式导航和布局入口，业务能力将按开发路线图逐项接入。
        </Typography.Text>
      </Space>
    </section>
  );
}

function menuItems(): Array<{ key: string; icon: ReactNode; label: ReactNode }> {
  return entries.map((entry) => ({
    key: entry.path,
    icon: entry.icon,
    label: <Link to={entry.path}>{entry.label}</Link>,
  }));
}

export function App() {
  const location = useLocation();

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
            <Tag color="processing">无登录 · 本机联调</Tag>
          </Space>
        </Header>
        <Content className="app-content">
          <Suspense fallback={<section className="entry-shell">页面加载中…</section>}>
            <Routes>
              <Route path="/" element={<Navigate to="/chat" replace />} />
              {entries
                .filter((entry) => entry.path !== "/knowledge-bases")
                .map((entry) => (
                  <Route
                    key={entry.path}
                    path={entry.path}
                    element={<EntryShell title={entry.label} description={entry.description} />}
                  />
                ))}
              <Route path="/knowledge-bases" element={<KnowledgeBasesPage />} />
              <Route path="*" element={<Navigate to="/chat" replace />} />
            </Routes>
          </Suspense>
        </Content>
      </Layout>
    </Layout>
  );
}
