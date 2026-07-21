import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./app/App";
import { AppProviders } from "./app/AppProviders";
import "@xyflow/react/dist/style.css";
import "./styles/index.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("缺少前端根节点");
}

createRoot(root).render(
  <StrictMode>
    <AppProviders>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </AppProviders>
  </StrictMode>,
);
