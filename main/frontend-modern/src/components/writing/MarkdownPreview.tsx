import { Fragment } from 'react'

export type MarkdownPreviewProps = {
  markdown: string
}

function renderInline(text: string, keyPrefix: string) {
  const parts = text.split(/(`[^`]+`|\[[^\]]+\]\([^)]+\))/g)
  return parts.filter(Boolean).map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code key={`${keyPrefix}-code-${index}`} className="writing-inline-code">
          {part.slice(1, -1)}
        </code>
      )
    }
    const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
    if (linkMatch) {
      return (
        <a key={`${keyPrefix}-link-${index}`} href={linkMatch[2]} target="_blank" rel="noreferrer">
          {linkMatch[1]}
        </a>
      )
    }
    return <Fragment key={`${keyPrefix}-text-${index}`}>{part}</Fragment>
  })
}

function renderBlock(line: string, index: number) {
  if (line.startsWith('### ')) return <h3 key={index}>{renderInline(line.slice(4), `h3-${index}`)}</h3>
  if (line.startsWith('## ')) return <h2 key={index}>{renderInline(line.slice(3), `h2-${index}`)}</h2>
  if (line.startsWith('# ')) return <h1 key={index}>{renderInline(line.slice(2), `h1-${index}`)}</h1>
  if (line.startsWith('> ')) return <blockquote key={index}>{renderInline(line.slice(2), `quote-${index}`)}</blockquote>
  if (line.startsWith('- ')) {
    return (
      <ul key={index}>
        <li>{renderInline(line.slice(2), `li-${index}`)}</li>
      </ul>
    )
  }
  return <p key={index}>{renderInline(line, `p-${index}`)}</p>
}

export default function MarkdownPreview({ markdown }: MarkdownPreviewProps) {
  const normalized = String(markdown || '').replace(/\r\n/g, '\n')
  const lines = normalized.split('\n')
  const blocks = []
  let inCodeFence = false
  let codeBuffer: string[] = []

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]
    if (line.startsWith('```')) {
      if (inCodeFence) {
        blocks.push(
          <pre key={`code-${index}`} className="writing-code-block">
            <code>{codeBuffer.join('\n')}</code>
          </pre>,
        )
        codeBuffer = []
        inCodeFence = false
      } else {
        inCodeFence = true
      }
      continue
    }
    if (inCodeFence) {
      codeBuffer.push(line)
      continue
    }
    if (!line.trim()) {
      blocks.push(<div key={`space-${index}`} className="writing-preview-spacer" />)
      continue
    }
    blocks.push(renderBlock(line, index))
  }

  if (codeBuffer.length) {
    blocks.push(
      <pre key="code-tail" className="writing-code-block">
        <code>{codeBuffer.join('\n')}</code>
      </pre>,
    )
  }

  return <section className="writing-preview">{blocks}</section>
}
