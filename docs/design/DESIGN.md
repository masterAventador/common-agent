---
version: 1.0
name: PowerAI-design-system
description: A high-end, business-grade design system for PowerAI Studio — an enterprise AI middle-platform (数智化中台) for the power & energy industry. Paper-calm Notion foundation, near-black neutral brand, hairline borders, restrained "electric" accent. Deliberately not "obviously AI."
language: Simplified Chinese (zh-CN)
brand-color: "#191919"
accent: "#4DA3FF (electric blue) · #0EA5A4 (electric teal)"
---

# PowerAI — Design System

A brand + UI design language for **PowerAI Studio**, an enterprise "AI middle-platform" giving operations teams one workspace for AI chat, digital employees (agents), team spaces, workflow orchestration, a tool/skill library, a knowledge base, and platform administration. Positioned for **vertical enterprise scenarios in the power & energy industry (电力与能源)**.

**Design intent:** 70% Notion-style clean whitespace + 20% enterprise-SaaS order + 10% restrained "electric" AI accent. The brief: *high-end, business-grade, brand-forward — not "obviously AI."* Lean on a calm off-white foundation, near-black neutral brand color, generous whitespace and hairline borders; use color only to communicate state, never to decorate.

---

## 1. Visual Theme & Atmosphere

The look is **paper-calm**: warm off-white planes, warm near-black ink, 1px hairline borders, and almost no shadow. It reads as a serious operational tool, not a consumer AI toy. Boundaries are drawn with lines, not depth. Color is a signal, not decoration. There are no gradients, no photography, no textures, no glassmorphism in the product chrome — the only "texture" is the subtle warmth of the grays.

---

## 2. Color System

Neutral-first. The page is a warm off-white; content sits on pure-white cards; ink is a **warm near-black, never pure `#000`**. The **primary brand color is neutral black `#191919`** — primary buttons are black, not blue.

### Neutrals & surfaces
| Token | Hex | Use |
|---|---|---|
| `--bg-app` | `#FAFAFA` | page canvas (warm off-white) |
| `--bg-container` | `#FFFFFF` | cards, panels, popovers |
| `--bg-hover` | `#F5F5F2` | row / menu hover (one step darker) |
| `--bg-active` | `#F1F1EF` | selected fill |
| `--border` | `#EDEDE9` | default hairline |
| `--border-strong` | `#E0E0DB` | emphasis hairline |
| `--border-focus` | `#B8B8B2` | input focus (no glow ring) |

### Ink (text)
| Token | Hex | Use |
|---|---|---|
| `--text-heading` | `#191919` | headings |
| `--text-body` | `#37352F` | body |
| `--text-secondary` | `#787774` | secondary |
| `--text-tertiary` | `#A8A8A5` | meta / placeholder |

### Brand & status (use only to signal state)
| Token | Hex | Meaning |
|---|---|---|
| `--primary` | `#191919` | core actions (neutral black) · hover `#333333` · active `#000000` |
| `--info` | `#2563EB` | links, info |
| `--electric` (teal) | `#0EA5A4` | AI-running / processing accent (sparingly) |
| electric blue | `#4DA3FF` | primary logo spark accent |
| `--success` | `#1F8A4C` | success, enabled |
| `--warning` | `#C46A17` | warning, pending |
| `--error` | `#D64545` | error, destructive |

### The tag palette — signature element
A **Notion-style 10-color palette** (charcoal, silver, brown, gold, orange, green, blue, purple, pink, red), each a **low-saturation tint background + deep readable text**. Powers tags, status badges (with a 6px status dot), small icon-container badges, and deterministic avatar backgrounds. Color identifies category; it never floods an area.

```
charcoal  bg #EFEFEE  text #4A4A47      gold    bg #FBF3D9  text #9A7B1E
silver    bg #F1F1F0  text #787774      orange  bg #FFF1E5  text #E57B2D
brown     bg #F3EBE4  text #8A5A2B      green   bg #E6F5EC  text #2C8754
blue      bg #E8F0FB  text #2467C8      purple  bg #F2ECFA  text #8853C1
pink      bg #FBEAF3  text #D1479B      red     bg #FBEAEA  text #C63939
```

---

## 3. Typography

- **UI face:** `Inter` (CJK falls back to PingFang SC / Microsoft YaHei).
- **Mono face:** `Geist Mono` / `JetBrains Mono` — code, IDs, tokens, model names, numbers.
- **Base:** 14px, line-height 1.57.

| Role | Size / weight |
|---|---|
| Auth display | 30px / 700 |
| Page title | 20px / 600 |
| Card title | 15–16px / 600 |
| Body | 14px / 400 |
| Secondary · meta | 12–13px |

Casing: Chinese needs none. The one Latin convention is short **uppercase eyebrow labels** with letter-spacing for section dividers (e.g. HISTORY / 历史对话). English elsewhere is sentence case — no Title Case Marketing Speak.

---

## 4. Spacing & Layout

- **4px-based scale:** 4 / 8 / 12 / 16 / 20 / 24 / 32.
- Page padding **24px**; default card padding **20px**.
- **Sidebar fixed 220px**; header / footer rows **64px**.
- Reading & chat content capped at a centered **56rem (896px)** column.
- Lists use a responsive card grid: `repeat(auto-fill, minmax(280px, 1fr))`, 16px gap.

---

## 5. Corners, Borders & Shadow

- **Radii:** 4px tags · 8px menu items / small buttons · 10px default controls · **12px cards** · 16px chat composer · full-round avatars & capsule badges.
- **Borders over shadow:** boundaries are **1px hairlines** (`--border`), not depth.
- **Shadows are tiny and rare:** `--shadow-xs 0 1px 2px rgba(0,0,0,.04)` at rest, `--shadow-sm 0 4px 12px rgba(0,0,0,.06)` on hover / popovers. A card at rest usually has **no shadow — just a border**.

---

## 6. Interaction States

- **Hover:** one-step-darker warm surface (`--bg-hover`) for rows / menu items; cards gain a stronger border + `xs→sm` shadow; primary buttons darken `#191919 → #333333`.
- **Selected / active:** `--bg-active` fill + heading-color text + medium weight.
- **Press:** primary deepens to `#000000`.
- **Focus:** input border moves to `--border-focus` — no heavy glow ring.

---

## 7. Motion

Quiet and quick. `transition: background/color 0.15s` on interactive surfaces, `0.2s` default, easing `cubic-bezier(0.4, 0, 0.2, 1)`. **No bounces, no decorative loops.** Animations are functional only: a spinning loader while a stream runs (teal "处理中"), workflow-node pulse/shake, edge-flow transitions. Transparency/blur used sparingly (e.g. canvas edge labels `rgba(255,255,255,0.92)`); the chrome itself is opaque — no glassmorphism.

---

## 8. Iconography

- **Primary system: Lucide** (`lucide-react`), consistent **22px, stroke-width 1.75** for nav, 12–16px inline. Thin even strokes match the calm aesthetic. Common glyphs: `MessageSquare, Bot, Workflow, Database, BookOpen, FolderOpen, Activity, History, Trash2, Pencil, Plus, Send, ChevronDown/Up, PanelLeftClose/Open, LogOut, IdCard, Loader2, Inbox`.
- **Logo — the PowerAI mark:** a near-black rounded app tile holding a white **power load-curve waveform** ending in a small **electric-blue (`#4DA3FF`) spark node** — an energy-sector motif (load curves), deliberately *not* a robot/AI cliché. Monochrome + one accent. Self-animates once on open (tile scales in, waveform draws left→right, spark pops); resting state is the finished logo so reduced-motion / print still show it.
- **Emoji & unicode:** **never** used as UI iconography. The only decorative non-Latin glyphs are `·` (meta separator) and `×` (tag close).

---

## 9. Content & Voice

Ships in **Simplified Chinese** (`lang="zh-CN"`). Copy is quiet competence — short, concrete, never hype.

- **Voice:** professional but warm; addresses the user as **你**; product speaks first-person on welcome (*"你好，我是 PowerAI"*). No exclamation marks, no marketing adjectives, **no emoji anywhere**.
- **Tone:** calm, capable, operational — says what a thing does and when to use it. Instructions favor the imperative (*创建第一个数字员工*).
- **Domain vocabulary (use exactly):** 对话 = Chat · 数字员工 = Digital Employee · 团队空间 = Team Space · 工作流 = Workflow · 工具箱 = Toolbox · 技能库 = Skill Library · 知识库 = Knowledge Base · 模型管理 = Model Management · 用户/角色管理 = User/Role Management. States: 启用/停用 · 运行中 · 待处理 · 草稿 · 审核中.
- **Microcopy patterns:**
  - Page header = **title + one-line subtitle**.
  - Empty state = **title + one sentence + one primary action**.
  - Input affordances spelled out inline (composer: *"输入消息，Enter 发送，Shift+Enter 换行"*).
  - Buttons are verbs (*登录、创建数字员工*); confirmations terse (*"确认删除？"*).

---

## 10. Cards (canonical component)

White fill · 1px `--border` hairline · **12px radius** · 20px padding · **no shadow at rest**. On hover the border strengthens and a soft `sm` shadow appears. Clickable cards show a pointer and the same hover treatment.

---

## Quick reference

```
brand/ink   #191919  (primary, never pure black)
body        #37352F   secondary #787774   tertiary #A8A8A5
canvas      #FAFAFA   card #FFFFFF   hover #F5F5F2   active #F1F1EF
border      #EDEDE9  (1px hairline — the primary boundary)
accent      #4DA3FF electric blue · #0EA5A4 electric teal (state only)
type        Inter (UI) · Geist Mono (code/IDs)   base 14px/1.57
radius      cards 12 · controls 10 · buttons 8 · tags 4 · avatars full
shadow      xs 0 1px 2px rgba(0,0,0,.04) · sm 0 4px 12px rgba(0,0,0,.06)
spacing     4 / 8 / 12 / 16 / 20 / 24 / 32   sidebar 220 · rows 64 · reading 896
motion      0.15–0.2s cubic-bezier(0.4,0,0.2,1) · functional only, no bounce
```
