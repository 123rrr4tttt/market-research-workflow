import { useMemo } from 'react'

type GraphBusinessNode = Record<string, unknown>

function normalizeValue(value: unknown) {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function cardFields(node: GraphBusinessNode) {
  const list: Array<[string, string]> = [
    ['类型', String(node.type || '-')],
    ['ID', String(node.id || '-')],
    ['标题', String(node.title || '')],
    ['名称', String(node.name || node.canonical_name || '')],
    ['州', String(node.state || '')],
    ['平台', String(node.platform || '')],
    ['游戏', String(node.game || '')],
    ['政策类型', String(node.policy_type || '')],
    ['状态', String(node.status || '')],
    ['日期', String(node.publish_date || node.effective_date || node.date || '')],
  ]
  return list.filter(([, value]) => value && value !== '-')
}

function parseNodeTags(node: GraphBusinessNode) {
  const tagKeys = ['key_points', 'keywords', 'topics', 'states', 'platforms']
  const tags: string[] = []
  tagKeys.forEach((key) => {
    const raw = node[key]
    if (Array.isArray(raw)) {
      raw.forEach((item) => {
        const text = normalizeValue(item).trim()
        if (text) tags.push(text)
      })
    }
  })
  return Array.from(new Set(tags)).slice(0, 20)
}

function extraPrimitiveFields(node: GraphBusinessNode) {
  const ignored = new Set([
    'id', 'type', 'title', 'name', 'text', 'canonical_name', 'state', 'platform', 'game', 'policy_type', 'status',
    'publish_date', 'effective_date', 'date', 'key_points', 'keywords', 'topics', 'states', 'platforms',
    'summary', 'content', 'extracted_data',
  ])
  return Object.entries(node)
    .filter(([key, value]) => !ignored.has(key) && (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'))
    .slice(0, 12)
}

export default function GraphBusinessCardSections({ node }: { node: GraphBusinessNode }) {
  const tags = parseNodeTags(node)
  const extraFields = extraPrimitiveFields(node)
  const text = normalizeValue(node.text).trim()
  const summary = normalizeValue(node.summary).trim()
  const content = normalizeValue(node.content).trim()
  const extractedDataText = useMemo(() => {
    const raw = node.extracted_data
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return ''
    try {
      return JSON.stringify(raw, null, 2)
    } catch {
      return ''
    }
  }, [node])
  const fullText = content || text

  return (
    <>
      <div className="gv2-node-grid">
        {cardFields(node).map(([k, v]) => (
          <div key={`${k}-${v}`} className="gv2-node-grid-item">
            <label>{k}</label>
            <strong>{v}</strong>
          </div>
        ))}
      </div>
      {tags.length ? (
        <div className="gv2-node-tags">
          {tags.map((tag) => <span key={tag}>{tag}</span>)}
        </div>
      ) : null}
      {extraFields.length ? (
        <div className="gv2-node-extra">
          {extraFields.map(([k, v]) => (
            <div key={k}>
              <label>{k}</label>
              <span>{String(v)}</span>
            </div>
          ))}
        </div>
      ) : null}
      {(summary || fullText || extractedDataText) ? (
        <div className="gv2-node-context">
          <strong>完整内容</strong>
          {summary ? (
            <div className="gv2-node-block">
              <label>摘要</label>
              <pre className="gv2-node-content-pre">{summary}</pre>
            </div>
          ) : null}
          {fullText ? (
            <div className="gv2-node-block">
              <label>正文</label>
              <pre className="gv2-node-content-pre gv2-node-content-pre-full">{fullText}</pre>
            </div>
          ) : null}
          {extractedDataText ? (
            <details className="gv2-node-json">
              <summary>结构化数据 (JSON)</summary>
              <pre className="gv2-node-content-pre gv2-node-content-pre-json">{extractedDataText}</pre>
            </details>
          ) : null}
        </div>
      ) : null}
    </>
  )
}
