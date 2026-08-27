import type { ErrorInfo, ReactElement, ReactNode } from 'react'
import { Component } from 'react'
import Markdown from 'react-markdown'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'

const SAFE_ELEMENTS = [
  'a',
  'blockquote',
  'br',
  'code',
  'del',
  'em',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'hr',
  'img',
  'li',
  'ol',
  'p',
  'pre',
  'strong',
  'table',
  'tbody',
  'td',
  'th',
  'thead',
  'tr',
  'ul',
] as const

const SANITIZE_SCHEMA = {
  attributes: {
    code: [['className', /^language-[A-Za-z0-9_-]+$/]],
    img: ['alt'],
  },
  protocols: {},
  tagNames: [...SAFE_ELEMENTS],
}

class MarkdownErrorBoundary extends Component<
  { children: ReactNode; fallback: ReactElement },
  { failed: boolean }
> {
  state = { failed: false }

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true }
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // 安全回退由 render 完成；不把原始渲染异常写入浏览器日志。
  }

  render(): ReactNode {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

function DisabledLink({ children }: { children?: ReactNode }): ReactElement {
  return <span className="safe-markdown__disabled-link">{children}</span>
}

function DisabledImage({ alt }: { alt?: string }): ReactElement {
  return <span className="safe-markdown__disabled-image">{alt ? `图片已禁用：${alt}` : '图片已禁用'}</span>
}

/**
 * 白名单 Markdown：不解析原始 HTML，不提供可点击链接，也不创建会加载外部资源的 img。
 */
export function SafeMarkdown({ className, content }: { className?: string; content: string }): ReactElement | null {
  if (!content) return null
  const classes = ['safe-markdown', className].filter(Boolean).join(' ')
  return (
    <MarkdownErrorBoundary
      fallback={<pre className={`${classes} safe-markdown--fallback`}>{content}</pre>}
      key={content}
    >
      <div className={classes}>
        <Markdown
          allowedElements={[...SAFE_ELEMENTS]}
          components={{
            a: ({ children }) => <DisabledLink>{children}</DisabledLink>,
            img: ({ alt }) => <DisabledImage alt={alt} />,
          }}
          rehypePlugins={[[rehypeSanitize, SANITIZE_SCHEMA]]}
          remarkPlugins={[remarkGfm]}
          skipHtml
          unwrapDisallowed
          urlTransform={() => ''}
        >
          {content}
        </Markdown>
      </div>
    </MarkdownErrorBoundary>
  )
}
