import { QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { useState, type PropsWithChildren } from "react";

import { createQueryClient } from "../api/queryClient";
import { ToastHost } from "../components/ToastHost";
import { AuthProvider } from "../features/auth/AuthProvider";
import { designTheme } from "./designSystem";

export function AppProviders({ children }: PropsWithChildren) {
  const [queryClient] = useState(createQueryClient);

  return (
    <ConfigProvider locale={zhCN} theme={designTheme}>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
        <ToastHost />
      </QueryClientProvider>
    </ConfigProvider>
  );
}
