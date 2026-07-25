import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BrandLogo } from "../components/BrandLogo";
import { designTheme } from "./designSystem";

describe("统一设计基线", () => {
  it("使用 DESIGN.md 规定的中性色与控件尺度", () => {
    expect(designTheme.token).toMatchObject({
      // 逐条对齐原型实测样式表 docs/design/prototype-computed.css
      colorPrimary: "#1C1B17",
      colorBgLayout: "#F5F2EB",
      colorBgContainer: "#FBFAF5",
      colorBorder: "#E5DFD0",
      colorText: "#3B3930",
      colorTextHeading: "#1C1B17",
      // 原型强调色是青绿而非蓝
      colorInfo: "#117067",
      controlHeight: 42,
      borderRadius: 9,
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
