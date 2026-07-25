# PowerAI 主设计稿（Atlas 象牙白）

## 文件说明
- `index.html` —— 主设计稿源码。**直接双击打开即可**，无需构建、无需安装依赖。
- `ecg-logo.js` —— 品牌 logo（脉冲波形动画），被 index.html 引用，需与 index.html 放在同一目录。
- `DESIGN.md` —— 设计规范（颜色、字体、间距、圆角、交互态、文案语气等）。
- `PowerAI Atlas.html` —— 离线单文件版：所有资源已内联进一个文件，方便发给别人或存档。

## 技术栈
纯原生 HTML + CSS + JavaScript，**零第三方库、零前端框架**。
字体从 Google Fonts CDN 引入（Inter / Newsreader / JetBrains Mono），离线单文件版已内联。

## 包含的页面
登录、对话（流式）、数字员工、团队空间、工作流（列表页 + 蓝图式画布，节点可拖拽/连线/传参）、
工具箱、技能库、知识库（含文档详情：左预览 + 右切片列表）、模型管理、用户与角色管理。

## 修改建议
改样式看 `index.html` 顶部的 `:root` 变量块（颜色、圆角、间距集中在这里）。
