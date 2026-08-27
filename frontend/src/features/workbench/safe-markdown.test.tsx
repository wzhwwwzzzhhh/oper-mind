import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SafeMarkdown } from './SafeMarkdown'

describe('SafeMarkdown', () => {
  it('渲染白名单排版，同时禁用 HTML、链接导航与图片加载', () => {
    render(
      <SafeMarkdown
        content={`# 调查结论

- **事实**一
- 事实二

| 项目 | 状态 |
| --- | --- |
| 索引 | 缺失 |

\`inline_code\`

[危险链接](javascript:alert('x'))

![远程追踪图](https://tracker.example/pixel.png)

<script>window.__unsafe = true</script>

<img src="https://tracker.example/raw.png" onerror="window.__unsafe = true">`}
      />,
    )

    expect(screen.getByRole('heading', { name: '调查结论' })).toBeInTheDocument()
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('inline_code')).toBeInTheDocument()
    expect(screen.getByText('危险链接')).toBeInTheDocument()
    expect(screen.getByText('图片已禁用：远程追踪图')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(document.querySelector('img')).toBeNull()
    expect(document.querySelector('script')).toBeNull()
    expect(document.body.innerHTML).not.toContain('onerror')
    expect(document.body.innerHTML).not.toContain('tracker.example')
  })

  it('空回答不创建多余容器', () => {
    const { container } = render(<SafeMarkdown content="" />)

    expect(container).toBeEmptyDOMElement()
  })
})
