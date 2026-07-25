import type { ThemeConfig } from "antd";

export const designTheme: ThemeConfig = {
  token: {
    colorPrimary: "#1C1B17",
    colorPrimaryHover: "#3B3930",
    colorPrimaryActive: "#000000",
    // 原型的强调色是青绿而非蓝
    colorInfo: "#117067",
    colorSuccess: "#117067",
    colorWarning: "#C46A17",
    colorError: "#C2413A",
    colorBgLayout: "#F5F2EB",
    colorBgContainer: "#FBFAF5",
    colorBgElevated: "#FBFAF5",
    controlItemBgActive: "#EDE7D8",
    controlItemBgActiveHover: "#E5DFD0",
    colorBorder: "#E5DFD0",
    colorBorderSecondary: "#E5DFD0",
    colorText: "#3B3930",
    colorTextHeading: "#1C1B17",
    colorTextSecondary: "#837C6B",
    colorTextTertiary: "#A59C87",
    // 原型控件统一 42px 高、9px 圆角
    controlHeight: 42,
    borderRadius: 9,
    borderRadiusLG: 12,
    borderRadiusSM: 8,
    fontFamily:
      'Inter, "PingFang SC", "Microsoft YaHei", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    fontSize: 14,
    lineHeight: 1.57,
    boxShadow: "0 1px 2px rgba(0, 0, 0, 0.04)",
    boxShadowSecondary: "0 4px 12px rgba(0, 0, 0, 0.06)",
    controlOutline: "transparent",
    motionDurationFast: "0.15s",
    motionDurationMid: "0.2s",
  },
  components: {
    Button: {
      borderRadius: 8,
      primaryShadow: "none",
      defaultShadow: "none",
    },
    Card: {
      borderRadiusLG: 12,
      boxShadow: "none",
      boxShadowTertiary: "none",
    },
    Input: {
      activeBorderColor: "#A59C87",
      activeShadow: "none",
      hoverBorderColor: "#A59C87",
    },
    Menu: {
      itemBg: "transparent",
      itemColor: "#787774",
      itemHoverBg: "#F0ECE1",
      itemHoverColor: "#1C1B17",
      itemSelectedBg: "#EDE7D8",
      itemSelectedColor: "#1C1B17",
      itemBorderRadius: 8,
    },
    Select: {
      activeBorderColor: "#A59C87",
      activeOutlineColor: "transparent",
      hoverBorderColor: "#A59C87",
      optionSelectedBg: "#EDE7D8",
      optionSelectedColor: "#1C1B17",
      optionActiveBg: "#F0ECE1",
    },
    Table: {
      headerBg: "#F5F2EB",
      headerColor: "#837C6B",
      rowHoverBg: "#F0ECE1",
    },
    Modal: {
      borderRadiusLG: 16,
    },
  },
};
