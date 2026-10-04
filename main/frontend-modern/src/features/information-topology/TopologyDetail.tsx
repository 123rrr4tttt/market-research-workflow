import type { BoundRef, TopologyElement, TopologyState, TopologyView } from './types'

export type TopologyDetailProps = {
  value: TopologyState | TopologyView
  resolutions?: Array<{ ref: BoundRef; status: 'resolved' | 'stale' | 'unresolvable'; current_revision?: string | null }>
  title?: string
}

function refLabel(ref: BoundRef) {
  const { module_id, type_id, local_id } = ref.ref
  return `${module_id}:${type_id}/${local_id}@${ref.observed_revision}`
}

function refKey(ref: BoundRef) {
  const { project_key, module_id, namespace, type_id, local_id } = ref.ref
  return [project_key, module_id, namespace, type_id, local_id, ref.observed_revision].join('\u0000')
}

function resolutionFor(ref: BoundRef, resolutions: TopologyDetailProps['resolutions']) {
  return resolutions?.find((item) => refKey(item.ref) === refKey(ref))
}

function ReferenceStatus({ reference, status, current_revision }: {
  reference: BoundRef
  status?: 'resolved' | 'stale' | 'unresolvable'
  current_revision?: string | null
}) {
  const resolved = status ?? 'resolved'
  return <span className={`topology-reference topology-reference--${resolved}`} data-status={resolved}>
    {refLabel(reference)}{resolved === 'stale' && current_revision ? ` (current ${current_revision})` : ''}
    {resolved !== 'resolved' && <strong> · {resolved === 'stale' ? '版本已失效' : '引用不可解析'}</strong>}
  </span>
}

function ElementDetail({ element, resolutions }: { element: TopologyElement; resolutions: TopologyDetailProps['resolutions'] }) {
  return <li className="topology-detail__element">
    <div><ReferenceStatus reference={element.ref} status={resolutionFor(element.ref, resolutions)?.status} current_revision={resolutionFor(element.ref, resolutions)?.current_revision} /></div>
    <dl>{Object.entries(element.attributes).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{typeof value === 'string' ? value : JSON.stringify(value)}</dd></div>)}</dl>
    {element.endpoints.length > 0 && <ul aria-label="关系端点">
      {element.endpoints.map((endpoint, index) => <li key={`${endpoint.role}-${endpoint.position ?? 'n'}-${index}`}>
        <span>{endpoint.role}{endpoint.position != null ? ` [${endpoint.position}]` : ''}: </span>
        <ReferenceStatus reference={endpoint.target} status={resolutionFor(endpoint.target, resolutions)?.status} current_revision={resolutionFor(endpoint.target, resolutions)?.current_revision} />
      </li>)}
    </ul>}
  </li>
}

export function TopologyDetail({ value, resolutions = [], title = '结构详情' }: TopologyDetailProps) {
  const isState = 'elements' in value
  const references = isState ? value.elements.map((element) => element.ref) : value.members
  return <section className="topology-detail" aria-label={title}>
    <h2>{title}</h2>
    {isState ? <>
      <p>结构：{value.profile_id} · 版本 {value.profile_version}</p>
      <ul className="topology-detail__elements">{value.elements.map((element) => <ElementDetail key={`${element.ref.ref.module_id}-${element.ref.ref.local_id}`} element={element} resolutions={resolutions} />)}</ul>
    </> : <>
      <p>视图：{value.definition_id} · 版本 {value.definition_version}</p>
      <h3>输入版本</h3>
      <ul>{Object.entries(value.input_revisions).map(([source, revision]) => <li key={source}>{source}: {revision}</li>)}</ul>
      <h3>成员与关系来源</h3>
      <ul>{[...references, ...value.relations].map((ref, index) => {
        const resolution = resolutionFor(ref, resolutions)
        return <li key={`${ref.ref.module_id}-${ref.ref.local_id}-${index}`}><ReferenceStatus reference={ref} status={resolution?.status} current_revision={resolution?.current_revision} /></li>
      })}</ul>
    </>}
  </section>
}
