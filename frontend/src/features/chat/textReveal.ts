import { useEffect, useState } from "react";

/**
 * 流式文字的匀速呈现。
 *
 * 模型的增量是一阵一阵到的：一次 SSE 可能带来几十个字，中间又空一拍，直接渲染就会一卡一卡。
 * 这里把已到达的文字放进缓冲，再按帧匀速吐出来，看上去像连续打字。
 *
 * 速度随积压量自适应：积压越多吐得越快，保证不会追不上模型；同时设下限避免拖沓、设上限
 * 避免又变回瞬间刷屏。
 */
const CATCH_UP_SECONDS = 0.32;
export const MIN_REVEAL_CHARS_PER_SECOND = 45;
export const MAX_REVEAL_CHARS_PER_SECOND = 900;

export function nextRevealLength({
  revealed,
  target,
  elapsedMs,
}: {
  revealed: number;
  target: number;
  elapsedMs: number;
}): number {
  // 内容被重置（重试会清空正文）时直接跟上，不能停在旧长度
  if (target <= revealed) return target;
  if (elapsedMs <= 0) return revealed;

  const backlog = target - revealed;
  const perSecond = Math.min(
    MAX_REVEAL_CHARS_PER_SECOND,
    Math.max(MIN_REVEAL_CHARS_PER_SECOND, backlog / CATCH_UP_SECONDS),
  );
  const advance = Math.max(1, Math.round((perSecond * elapsedMs) / 1000));
  return Math.min(target, revealed + advance);
}

/**
 * 回复还在长的时候是否继续贴底跟随。
 *
 * 读者往上翻去看前面的内容时就不该再把他拽回底部；留一段容差，避免刚长出来的一两行
 * 就被判定成"读者主动离开了底部"。
 */
const FOLLOW_BOTTOM_TOLERANCE_PX = 120;

export function shouldFollowBottom(view: {
  scrollHeight: number;
  scrollTop: number;
  clientHeight: number;
}): boolean {
  return view.scrollHeight - view.scrollTop - view.clientHeight <= FOLLOW_BOTTOM_TOLERANCE_PX;
}

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

/**
 * 生成过程中按帧吐字，生成结束或用户要求减少动效时直接给全文。
 *
 * 已吐出的长度只在动画帧里推进：帧回调里用函数式更新拿到上一次的值，值没变时 React 自己
 * 会跳过重绘。目标突然变短说明这条回复被重置了（重试会清空正文），此时从头再吐一遍。
 */
export function useRevealedText(target: string, streaming: boolean): string {
  const [revealed, setRevealed] = useState(target.length);
  const animate = streaming && !prefersReducedMotion();

  useEffect(() => {
    if (!animate) return;
    let frame = 0;
    let previous = performance.now();
    const step = (now: number) => {
      const elapsedMs = now - previous;
      previous = now;
      setRevealed((current) =>
        nextRevealLength({
          revealed: current > target.length ? 0 : current,
          target: target.length,
          elapsedMs,
        }),
      );
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [animate, target]);

  return animate ? target.slice(0, Math.min(revealed, target.length)) : target;
}
