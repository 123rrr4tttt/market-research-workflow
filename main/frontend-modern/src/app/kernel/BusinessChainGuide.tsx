import { BookOpen, GitBranch, ShieldCheck } from 'lucide-react'
import { useMemo } from 'react'
import { translate, useAppLocale } from '../platform/i18n'
import { BUSINESS_CHAIN_GUIDE, projectBusinessChainGraph, type GuideLocale } from './businessChainGuideData'

const KIND_CLASS = {
  input: 'is-input',
  transform: 'is-transform',
  effect: 'is-effect',
  evidence: 'is-evidence',
  projection: 'is-projection',
  root: 'is-root',
  chain: 'is-chain',
} as const

export default function BusinessChainGuide() {
  const locale = useAppLocale() as GuideLocale
  const graph = useMemo(() => projectBusinessChainGraph(locale), [locale])
  const labels = locale === 'zh-CN'
    ? { legend: '节点含义', authority: '权威边界', route: '实际入口', operator: '执行者/端口', artifact: '产生与读回', uiRoute: '相关页面' }
    : { legend: 'Node legend', authority: 'Authority boundary', route: 'Live entry', operator: 'Operator / port', artifact: 'Artifacts & readback', uiRoute: 'Related pages' }
  const nodeWidth = (kind: keyof typeof KIND_CLASS) => kind === 'root' ? 168 : kind === 'chain' ? 188 : 142

  return (
    <section className="business-chain-guide business-chain-guide--page" aria-label={BUSINESS_CHAIN_GUIDE.title[locale]}>
      <div className="business-chain-guide__header">
        <div className="business-chain-guide__heading">
          <BookOpen size={17} aria-hidden="true" />
          <div>
            <h2>{BUSINESS_CHAIN_GUIDE.title[locale]}</h2>
            <p>{BUSINESS_CHAIN_GUIDE.subtitle[locale]}</p>
          </div>
        </div>
      </div>

      <div className="business-chain-guide__entries">
        {BUSINESS_CHAIN_GUIDE.chains.map((chain) => (
          <article key={chain.id} className="business-chain-guide__entry">
            <h3><GitBranch size={16} aria-hidden="true" />{chain.label[locale]}</h3>
            <p>{chain.summary[locale]}</p>
            <dl>
              <div><dt>{labels.artifact}</dt><dd>{chain.artifact[locale]}</dd></div>
              <div><dt>{labels.uiRoute}</dt><dd>{chain.uiRoute[locale]}</dd></div>
            </dl>
            <details className="business-chain-guide__technical">
              <summary>{translate(locale, 'shell.admin.guide.details')}</summary>
              <dl>
                <div><dt>{labels.route}</dt><dd>{chain.route}</dd></div>
                <div><dt>{labels.authority}</dt><dd><ShieldCheck size={14} aria-hidden="true" />{chain.authority[locale]}</dd></div>
                <div><dt>{labels.operator}</dt><dd>{chain.operator[locale]}</dd></div>
              </dl>
            </details>
          </article>
        ))}
      </div>

      <details className="business-chain-guide__map">
          <summary>{translate(locale, 'shell.admin.guide.graph')}</summary>
          <div className="business-chain-guide__graph-wrap">
            <svg className="business-chain-guide__graph" viewBox={`0 0 ${graph.width} ${graph.height}`} role="img" aria-label={BUSINESS_CHAIN_GUIDE.title[locale]}>
              {graph.edges.map((edge) => {
                const source = graph.nodes.find((node) => node.id === edge.source)
                const target = graph.nodes.find((node) => node.id === edge.target)
                if (!source || !target) return null
                return <line key={edge.id} className="business-chain-guide__edge" x1={source.x + nodeWidth(source.kind)} y1={source.y + 20} x2={target.x} y2={target.y + 20} />
              })}
              {graph.nodes.map((node) => (
                <g key={node.id} className={`business-chain-guide__node ${KIND_CLASS[node.kind]}`}>
                  <rect x={node.x} y={node.y} width={nodeWidth(node.kind)} height="40" rx="4" />
                  <text x={node.x + 12} y={node.y + 18}>{node.label}</text>
                  <text className="business-chain-guide__node-detail" x={node.x + 12} y={node.y + 32}>{node.kind === 'root' ? node.detail.slice(0, 28) : node.detail.slice(0, 22)}</text>
                </g>
              ))}
            </svg>
          </div>
          <div className="business-chain-guide__legend" aria-label={labels.legend}>
            {[['is-input', '入口'], ['is-transform', '变换'], ['is-effect', '效果'], ['is-evidence', '证据'], ['is-projection', '投影']].map(([kind, label]) => (
              <span key={kind}><i className={`business-chain-guide__swatch ${kind}`} />{locale === 'zh-CN' ? label : kind.replace('is-', '')}</span>
            ))}
          </div>
      </details>
    </section>
  )
}
