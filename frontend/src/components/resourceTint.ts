/**
 * 资源卡片图标 tile 的配色。
 *
 * 设计稿里每个数字员工的图标 tile 颜色不同（见 docs/design/prototype/index.html 的 AGENTS，
 * bg/fg 是逐条手挑的）。平台的员工数据没有配色字段，这里按稳定 key 轮换同一组色调，
 * 保证同一个资源每次渲染颜色一致，不同资源之间又有区分度。
 */
export interface ResourceTint {
  background: string;
  color: string;
}

export const RESOURCE_TINTS: readonly ResourceTint[] = [
  { background: "#e8ecff", color: "#2e48f0" },
  { background: "#e6f6ee", color: "#1f8a4c" },
  { background: "#fdf1e3", color: "#c46a17" },
  { background: "#f2ecfa", color: "#8853c1" },
  { background: "#fbeaf3", color: "#d1479b" },
  { background: "#e6f0ec", color: "#117067" },
];

export function resourceTint(key: string): ResourceTint {
  let hash = 0;
  for (const character of key) {
    hash = (hash * 31 + (character.codePointAt(0) ?? 0)) % 1_000_003;
  }
  return RESOURCE_TINTS[hash % RESOURCE_TINTS.length];
}
