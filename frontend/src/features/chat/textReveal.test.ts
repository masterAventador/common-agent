import { describe, expect, it } from "vitest";

import {
  MAX_REVEAL_CHARS_PER_SECOND,
  MIN_REVEAL_CHARS_PER_SECOND,
  nextRevealLength,
  shouldFollowBottom,
} from "./textReveal";

const frame = 16;

describe("nextRevealLength", () => {
  it("never runs past the text that actually arrived", () => {
    expect(nextRevealLength({ revealed: 8, target: 10, elapsedMs: 5_000 })).toBe(10);
  });

  it("stays put when everything is already shown", () => {
    expect(nextRevealLength({ revealed: 10, target: 10, elapsedMs: frame })).toBe(10);
  });

  it("snaps back when the reply is reset, for example on retry", () => {
    expect(nextRevealLength({ revealed: 120, target: 0, elapsedMs: frame })).toBe(0);
  });

  it("does not advance without elapsed time", () => {
    expect(nextRevealLength({ revealed: 0, target: 500, elapsedMs: 0 })).toBe(0);
  });

  it("always moves at least one character while text is pending", () => {
    // 单帧 16ms 下即使按最低速度也不足 1 字, 但画面不能停住不动
    expect(nextRevealLength({ revealed: 0, target: 1, elapsedMs: 1 })).toBe(1);
  });

  it("speeds up as the backlog grows so it never falls behind", () => {
    const small = nextRevealLength({ revealed: 0, target: 40, elapsedMs: frame });
    const large = nextRevealLength({ revealed: 0, target: 4_000, elapsedMs: frame });
    expect(large).toBeGreaterThan(small);
  });

  it("keeps a readable floor and a hard ceiling on speed", () => {
    const oneSecond = 1_000;
    const slow = nextRevealLength({ revealed: 0, target: 10_000_000, elapsedMs: oneSecond });
    expect(slow - 0).toBeLessThanOrEqual(MAX_REVEAL_CHARS_PER_SECOND);

    const trickle = nextRevealLength({ revealed: 0, target: 5, elapsedMs: oneSecond });
    // 只差 5 个字时一秒内必须补完, 不能被下限拖成慢放
    expect(trickle).toBe(5);
    expect(MIN_REVEAL_CHARS_PER_SECOND).toBeGreaterThan(0);
  });

  it("clears a normal burst well within a second", () => {
    // 一次 SSE 通常带来几十个字, 单帧就该吃掉可观的一部分而不是一个字一个字挪
    const advanced = nextRevealLength({ revealed: 0, target: 60, elapsedMs: frame });
    expect(advanced).toBeGreaterThanOrEqual(2);
  });
});

describe("shouldFollowBottom", () => {
  it("follows while the reader is parked at the bottom", () => {
    expect(shouldFollowBottom({ scrollHeight: 2_000, scrollTop: 1_400, clientHeight: 600 })).toBe(
      true,
    );
  });

  it("keeps following through small gaps left by a growing reply", () => {
    expect(shouldFollowBottom({ scrollHeight: 2_060, scrollTop: 1_400, clientHeight: 600 })).toBe(
      true,
    );
  });

  it("lets go once the reader scrolls up to read something earlier", () => {
    expect(shouldFollowBottom({ scrollHeight: 4_000, scrollTop: 400, clientHeight: 600 })).toBe(
      false,
    );
  });
});
