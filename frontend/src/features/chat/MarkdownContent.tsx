import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * 补上模型漏写的标题空格。
 *
 * CommonMark 要求 `#` 后必须有空格才算标题，而中文模型经常直接写「##标题」，
 * 不补就会把整行当正文、把 `##` 原样显示给用户。只处理行首连续 1-6 个 `#` 紧跟
 * 非空白的情况，行内的 `#标签` 和代码块里的 `#!/bin/sh` 都不受影响。
 */
function normalizeHeadings(content: string): string {
  let inFence = false;
  return content
    .split("\n")
    .map((line) => {
      if (/^\s*(```|~~~)/.test(line)) {
        inFence = !inFence;
        return line;
      }
      if (inFence) return line;
      return line.replace(/^(#{1,6})(?=[^#\s])/, "$1 ");
    })
    .join("\n");
}

/**
 * 渲染模型输出的 Markdown。
 *
 * 模型输出是不可信输入：这里不接 rehype-raw，react-markdown 默认也不渲染原始 HTML，
 * 因此回复里出现 <script>/<img onerror> 只会当纯文本显示。链接强制新窗口打开并断开
 * referrer 与 opener。
 */
export function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="markdown-body">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
        }}
      >
        {normalizeHeadings(content)}
      </Markdown>
    </div>
  );
}
