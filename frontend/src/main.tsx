import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./app/App";
import "./styles/index.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("缺少前端根节点");
}

createRoot(root).render(
  <StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#315efb",
          borderRadius: 10,
          colorBgLayout: "#f5f7fb",
        },
      }}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </StrictMode>,
);
