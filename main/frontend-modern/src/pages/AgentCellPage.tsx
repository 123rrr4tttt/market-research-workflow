import { useMemo, useState, type CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowDownLeft, ArrowUpRight, ChevronDown, Circle, Layers3, Pause, Play, RefreshCw, Search, X } from 'lucide-react'
import { cellFailure, cellSections, readCell, type CellEntry, type CellSection } from './agent-cell/model'
import './agent-cell/agent-cell.css'

const LAYERS = [
  { name: '概念规定', en: 'BOUNDARY', radius: 255, width: 62, start: -42, color: '#222d29' },
  { name: '能力中介', en: 'MEDIATION', radius: 184, width: 61, start: -66, color: '#d2ec83' },
  { name: '关系与读回', en: 'RELATIONS', radius: 113, width: 39, start: -35, color: '#c8dbdf' },
]
const point = (radius: number, degrees: number) => {
  const radians = (degrees - 90) * Math.PI / 180
  return [320 + radius * Math.cos(radians), 320 + radius * Math.sin(radians)]
}
function arc(radius: number, start: number, end: number) {
  const [x1, y1] = point(radius, start)
  const [x2, y2] = point(radius, end)
  return `M ${x1} ${y1} A ${radius} ${radius} 0 ${end - start > 180 ? 1 : 0} 1 ${x2} ${y2}`
}

function CellRing({ sections, selected, onSelect, layered, paused }: {
  sections: CellSection[]; selected: string; onSelect: (id: string) => void; layered: boolean; paused: boolean
}) {
  return <svg className={`cell-ring ${layered ? 'is-layered' : ''} ${paused ? 'is-paused' : ''}`} viewBox="0 0 640 660" role="group" aria-label="胞腔分层圆环">
    <g className="cell-ring__grid" aria-hidden="true">
      <path d="M 320 12 V 628 M 12 320 H 628" />
      <circle cx="320" cy="320" r="303" />
      {Array.from({ length: 72 }, (_, i) => {
        const [x1, y1] = point(i % 6 === 0 ? 291 : 296, i * 5)
        const [x2, y2] = point(301, i * 5)
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} />
      })}
    </g>
    {LAYERS.map((layer, layerIndex) => {
      const rows = sections.filter((s) => s.layer === layerIndex)
      return <g key={layer.name} className={`cell-ring__layer cell-ring__layer--${layerIndex}`}>
        <circle className="cell-ring__orbit" cx="320" cy="320" r={layer.radius + layer.width / 2 + 7} />
        {rows.map((section, i) => {
          const start = layer.start + i * 360 / rows.length
          const end = start + 360 / rows.length - 5
          const [x, y] = point(layer.radius, (start + end) / 2)
          const active = selected === section.id
          return <g key={section.id} role="button" tabIndex={0} aria-label={`${section.number} ${section.title}，${section.entries.length} 项`} aria-pressed={active}
            className={`cell-ring__segment ${active ? 'is-selected' : ''} ${layerIndex === 0 ? 'is-dark' : ''}`}
            onClick={() => onSelect(section.id)} onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(section.id) }
            }}>
            <title>{`${section.title} / ${section.entries.length} 项`}</title>
            <path d={arc(layer.radius, start, end)} fill="none" stroke={active ? '#e64e35' : layer.color} strokeWidth={layer.width} />
            <text x={x} y={y - 3} className="cell-ring__number">{section.number}<tspan className="cell-ring__count" dx="5">/{section.entries.length}</tspan></text>
            <text x={x} y={y + 15} className="cell-ring__label">{section.title}</text>
          </g>
        })}
      </g>
    })}
    <g role="button" tabIndex={0} aria-label="00 原生 Core" aria-pressed={selected === 'core'} className={`cell-ring__core ${selected === 'core' ? 'is-selected' : ''}`}
      onClick={() => onSelect('core')} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect('core') } }}>
      <circle cx="320" cy="320" r="64" />
      <text x="320" y="306" className="cell-ring__core-label">00 / NATIVE</text>
      <text x="320" y="336" className="cell-ring__core-title">Core</text>
    </g>
    <text className="cell-ring__axis-label" x="320" y="652">AGENT MACRO / STRUCTURAL PROJECTION</text>
  </svg>
}

function Entry({ entry, open, onToggle }: { entry: CellEntry; open: boolean; onToggle: () => void }) {
  return <article className={`cell-entry ${open ? 'is-open' : ''}`}>
    <button type="button" className="cell-entry__toggle" aria-expanded={open} onClick={onToggle}>
      <span><strong>{entry.title}</strong>{entry.caption && <small>{entry.caption}</small>}</span><ChevronDown size={16} />
    </button>
    {open && <div className="cell-entry__body">
      {typeof entry.data.description_for_model === 'string' && <p>{entry.data.description_for_model}</p>}
      <dl>{Object.entries(entry.data).filter(([key]) => key !== 'description_for_model').map(([key, value]) => <div key={key}>
        <dt>{key}</dt><dd>{typeof value === 'object' && value !== null
          ? <pre>{JSON.stringify(value, null, 2)}</pre>
          : String(value ?? '—')}</dd>
      </div>)}</dl>
    </div>}
  </article>
}

export default function AgentCellPage({ projectKey }: { projectKey: string }) {
  const [packageIdentity, setPackageIdentity] = useState('')
  const [packageChoices, setPackageChoices] = useState<[string, string][]>([])
  const [selected, setSelected] = useState('tools')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [layered, setLayered] = useState(false)
  const [paused, setPaused] = useState(false)
  const query = useQuery({ queryKey: ['agent-cell', projectKey, packageIdentity], queryFn: ({ signal }) => readCell(projectKey, packageIdentity, signal), staleTime: 30_000, retry: false })
  const environment = query.data?.environment
  const sections = useMemo(() => environment ? cellSections(environment) : [], [environment])
  const select = (id: string) => { setSelected(id); setExpanded(null); setSearch('') }
  const coreSection: CellSection | undefined = environment ? {
    id: 'core', number: '00', title: '原生 Core', en: 'NATIVE CORE', layer: 3,
    entries: [{ id: environment.definition.core_binding_ref, title: environment.definition.core_binding_ref, caption: environment.definition.core_mode,
      data: { core_binding_ref: environment.definition.core_binding_ref, core_mode: environment.definition.core_mode, entrypoint_ref: environment.definition.operation.entrypoint_ref } }],
  } : undefined
  const section = selected === 'core' ? coreSection : sections.find((s) => s.id === selected)
  const entries = section?.entries.filter((item) => `${item.title} ${item.caption ?? ''} ${JSON.stringify(item.data)}`.toLowerCase().includes(search.toLowerCase())) ?? []
  const failure = cellFailure(query.error)

  return <main className="cell-atlas" data-testid="agent-cell-page">
    <header className="cell-atlas__heading">
      <div className="cell-atlas__title"><span className="cell-atlas__edition">MRW / AGENT MACRO</span><h1>胞腔<span>CELL ATLAS</span></h1></div>
      <div className="cell-atlas__context"><span>PROJECT / {projectKey}</span><strong>{environment?.definition.cell_id ?? 'REGISTRATION INDEX'}</strong>
        <span>{environment ? (environment.package ? `${environment.package.package_id} @ ${environment.package.package_version}` : '基础环境 / BASE') : '结构读回'}<i />只读</span>
      </div>
      <ArrowDownLeft className="cell-atlas__heading-arrow" size={50} strokeWidth={1.2} aria-hidden="true" />
    </header>

    <div className="cell-atlas__toolbar">
      <div className="cell-atlas__modes" role="group" aria-label="结构视角">
        <button type="button" aria-pressed={!layered} onClick={() => setLayered(false)}><Circle size={15} />整体</button>
        <button type="button" aria-pressed={layered} onClick={() => setLayered(true)}><Layers3 size={16} />分层</button>
      </div>
      {packageChoices.length > 0 && <select className="cell-atlas__package-select" aria-label="当前注册包" value={packageIdentity} onChange={(e) => { setPackageIdentity(e.target.value); setExpanded(null) }}>
        <option value="">自动选择</option>{packageChoices.map((p) => <option key={JSON.stringify(p)} value={JSON.stringify(p)}>{p[0]} @ {p[1]}</option>)}
      </select>}
      <div className="cell-atlas__actions">
        <span className="cell-atlas__state">{query.isFetching ? '读取中' : query.isError ? '读回失败' : '结构快照'}</span>
        <button type="button" className="cell-icon-button" aria-label={paused ? '播放结构动画' : '暂停结构动画'} title={paused ? '播放结构动画' : '暂停结构动画'} onClick={() => setPaused(!paused)}>{paused ? <Play size={17} /> : <Pause size={17} />}</button>
        <button type="button" className="cell-icon-button" aria-label="刷新胞腔" title="刷新胞腔" disabled={query.isFetching} onClick={() => { void query.refetch() }}><RefreshCw size={17} className={query.isFetching ? 'cell-spin' : ''} /></button>
      </div>
    </div>

    {query.isError ? <section className="cell-atlas__notice" role="alert"><span className="cell-atlas__notice-number">!</span><h2>{failure.packages.length ? '选择注册包' : '胞腔暂不可用'}</h2><p>{failure.message}</p>
      {failure.packages.length > 0 && <label>注册包<select aria-label="注册包" value={packageIdentity} onChange={(e) => { setPackageChoices(failure.packages); setPackageIdentity(e.target.value) }}><option value="">请选择</option>{failure.packages.map((p) => <option key={JSON.stringify(p)} value={JSON.stringify(p)}>{p[0]} @ {p[1]}</option>)}</select></label>}
      {packageIdentity && <button type="button" onClick={() => setPackageIdentity('')}>返回默认选择</button>}
    </section> : !environment ? <section className="cell-atlas__notice" role="status"><span className="cell-atlas__notice-number">◎</span><h2>正在读取胞腔</h2><p>{projectKey}</p></section> : <>
      <div className="cell-atlas__body">
        <section className="cell-atlas__visual" aria-label="胞腔结构">
          <div className="cell-atlas__figure-meta"><span>FIG. 01</span><span>{String(sections.length).padStart(2, '0')} SECTIONS / 03 LAYERS</span></div>
          <CellRing sections={sections} selected={selected} onSelect={select} layered={layered} paused={paused} />
          <div className="cell-atlas__legend">{LAYERS.map((layer, i) => <span key={layer.name}><i style={{ background: layer.color }} />{String(i + 1).padStart(2, '0')} {layer.name}</span>)}</div>
        </section>
        <aside className="cell-atlas__inspector" aria-label="注册内容">
          <div className="cell-atlas__inspector-heading"><span>{section?.en}</span><ArrowUpRight size={24} strokeWidth={1.2} /></div>
          <div className="cell-atlas__section-title"><span>{section?.number}</span><h2>{section?.title}</h2><small>{section?.entries.length ?? 0} 项</small></div>
          <label className="cell-atlas__search"><Search size={17} /><input aria-label="检索当前分区" placeholder="检索名称、引用与内容" value={search} onChange={(e) => setSearch(e.target.value)} />{search && <button type="button" aria-label="清除检索" onClick={() => setSearch('')}><X size={14} /></button>}</label>
          <div className="cell-atlas__entries" key={selected}>
            {entries.length ? entries.map((entry) => <Entry key={entry.id} entry={entry} open={expanded === entry.id} onToggle={() => setExpanded(expanded === entry.id ? null : entry.id)} />)
              : <p className="cell-atlas__empty">{search ? '没有匹配的内容' : '本环境未声明此类条目'}</p>}
          </div>
          <div className="cell-atlas__inspector-foot">{environment.package ? 'ACTIVATED PACKAGE' : 'HOST BASE ENVIRONMENT'}<span>REGISTRY READBACK</span></div>
        </aside>
      </div>
      <nav className="cell-atlas__index" aria-label="胞腔分区索引">{sections.map((s) => <button type="button" key={s.id} aria-pressed={selected === s.id} onClick={() => select(s.id)} style={{ '--layer-color': LAYERS[s.layer].color } as CSSProperties}>
        <span>{s.number}</span><strong>{s.title}</strong><small>{s.entries.length}</small>
      </button>)}</nav>
      <footer className="cell-atlas__footer"><span>注册与结构快照 · 执行状态由原生宿主读回</span><span title={query.data?.environment_digest}>REV / {query.data?.environment_digest.slice(0, 12)}</span></footer>
    </>}
  </main>
}
