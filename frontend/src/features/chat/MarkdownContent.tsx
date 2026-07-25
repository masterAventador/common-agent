import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

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
        {content}
      </Markdown>
    </div>
  );
}
