import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BrandLogo } from "../components/BrandLogo";
import { designTheme } from "./designSystem";

describe("统一设计基线", () => {
  it("使用 DESIGN.md 规定的中性色与控件尺度", () => {
    expect(designTheme.token).toMatchObject({
      colorPrimary: "#191919",
      // 暖米纸感基线，取自 PowerAI Atlas 原型实测
      colorBgLayout: "#F5F2EB",
      colorBgContainer: "#FBFAF5",
      colorBorder: "#E2DCCD",
      colorText: "#37352F",
      colorTextHeading: "#191919",
      borderRadius: 10,
      fontSize: 14,
    });
  });

  it("渲染可复用的负荷曲线动效标志且不携带原型品牌名", () => {
    const { container } = render(<BrandLogo size={36} />);

    expect(screen.getByTestId("brand-logo")).toBeInTheDocument();
    expect(container.querySelector("animateTransform")).toHaveAttribute("dur", "2s");
    expect(container).not.toHaveTextContent("PowerAI");
  });
});
