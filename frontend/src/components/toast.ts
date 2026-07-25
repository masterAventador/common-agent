/**
 * 全局轻量提示（toast）的数据源：页面顶部居中浮出、到时自动消失。
 *
 * 用于「操作结果」这类一次性反馈（保存成功、调用失败等），替代会把页面内容顶下去的内嵌
 * Alert。持续性状态仍留在页面里用 Alert 表达，例如「加载失败 + 重试按钮」「保留策略说明」。
 *
 * 为什么不用 antd 的 message：它依赖的 rc-notification 会让工作流路由首屏 JS 增加约 24KB，
 * 直接冲破项目既定的单路由包体门禁（实测 1524463 > 1500000），改成动态 import 也无效，
 * 因为 antd 已在公共 chunk 内。此处自建约 1KB 的等价实现，避免为了一个提示条放宽门禁。
 * 门禁吃紧的根因是工作流页把画布库拖进了首屏，已单独记入路线图跟进。
 */

export type ToastKind = "success" | "error" | "info" | "warning";

export type ToastItem = {
  id: number;
  kind: ToastKind;
  content: string;
};

const DURATION_MS = 3000;
const MAX_VISIBLE = 3;

let nextId = 0;
let items: readonly ToastItem[] = [];
const listeners = new Set<() => void>();

function publish(next: readonly ToastItem[]): void {
  items = next;
  for (const listener of listeners) {
    listener();
  }
}

function push(kind: ToastKind, content: string): void {
  const id = (nextId += 1);
  publish([...items, { id, kind, content }].slice(-MAX_VISIBLE));
  setTimeout(() => publish(items.filter((item) => item.id !== id)), DURATION_MS);
}

/** 供 ToastHost 通过 useSyncExternalStore 订阅。 */
export function subscribeToasts(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getToasts(): readonly ToastItem[] {
  return items;
}

export const toast = {
  success: (content: string): void => push("success", content),
  error: (content: string): void => push("error", content),
  info: (content: string): void => push("info", content),
  warning: (content: string): void => push("warning", content),
};
