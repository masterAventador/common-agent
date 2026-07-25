import { render, screen, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toast } from "./toast";
import { ToastHost } from "./ToastHost";

describe("toast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    act(() => {
      vi.runOnlyPendingTimers();
    });
    vi.useRealTimers();
  });

  it("在页面顶部展示成功提示并在停留时间后自动消失", () => {
    render(<ToastHost />);

    act(() => {
      toast.success("模型调用成功");
    });

    const region = screen.getByRole("status");
    expect(region).toHaveTextContent("模型调用成功");

    act(() => {
      vi.advanceTimersByTime(3200);
    });
    expect(screen.queryByText("模型调用成功")).not.toBeInTheDocument();
  });

  it("失败提示使用 alert 语义以便读屏立即播报", () => {
    render(<ToastHost />);

    act(() => {
      toast.error("模型调用失败");
    });

    expect(screen.getByRole("alert")).toHaveTextContent("模型调用失败");
  });

  it("同时多条时按先后堆叠展示", () => {
    render(<ToastHost />);

    act(() => {
      toast.success("第一条");
      toast.error("第二条");
    });

    expect(screen.getByText("第一条")).toBeInTheDocument();
    expect(screen.getByText("第二条")).toBeInTheDocument();
  });

  it("没有挂载宿主时调用不抛错", () => {
    expect(() => toast.info("无宿主")).not.toThrow();
  });
});
