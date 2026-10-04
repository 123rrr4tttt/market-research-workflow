import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { informationTopologyClient } from '../../features/information-topology'
import {
  createTopologyElement,
  createTopologyState,
  defineTopologyCreationContract,
} from '../../features/information-topology'
import type { BoundRef, TopologyElement, TopologyPatchBatchRequest, TopologyPatchOperation, TopologyRef } from '../../features/information-topology'
import { ApiClientError } from '../../lib/api/client'

type Props = { projectKey: string; documentId: number | null; bodyVersion: number | null }
const queryKey = (projectKey: string, documentId: number | null) => ['information-topology', 'report-outline', projectKey, documentId]

const REPORT_CREATION_CONTRACT = defineTopologyCreationContract(
  ['content_name', 'content_order', 'structural_role'],
)

function targetFor(documentId: number | null): TopologyRef {
  return { module_id: 'report', namespace: 'outline', state_id: documentId == null ? 'report' : `writing-${documentId}` }
}

function refKey(ref: BoundRef) {
  return [ref.ref.project_key, ref.ref.module_id, ref.ref.namespace, ref.ref.type_id, ref.ref.local_id].join('\u0000')
}

function makeRef(projectKey: string, localId: string, revision: string): BoundRef {
  return { ref: { project_key: projectKey, module_id: 'report', namespace: 'outline', type_id: 'section', local_id: localId }, observed_revision: revision }
}

function elementWith(element: TopologyElement, title: string, order: number): TopologyElement {
  return {
    ...element,
    attributes: {
      ...element.attributes,
      title,
      order,
      content_name: title,
      content_order: order,
      structural_role: 'member',
    },
  }
}

export default function ReportTopologyPanel(props: Props) {
  return <ReportTopologyPanelInner
    key={`${props.projectKey}:${props.documentId}`}
    {...props}
  />
}

function ReportTopologyPanelInner({ projectKey, documentId, bodyVersion }: Props) {
  const client = useQueryClient()
  const target = targetFor(documentId)
  const key = queryKey(projectKey, documentId)
  const [titles, setTitles] = useState<Record<string, string>>({})
  const [orders, setOrders] = useState<Record<string, number>>({})
  const [referenceText, setReferenceText] = useState<Record<string, string>>({})
  const [pendingReferences, setPendingReferences] = useState<Record<string, Array<{ type: string; module: string; namespace: string; id: string; revision: string }>>>({})
  const [status, setStatus] = useState('')
  const outline = useQuery({
    queryKey: key,
    queryFn: () => informationTopologyClient.readTopology(target),
    enabled: Boolean(projectKey),
    retry: false,
  })
  const sections = useMemo(() => (outline.data?.topology.elements || [])
    .filter((item) => item.ref.ref.type_id === 'section')
    .sort((a, b) => (orders[a.ref.ref.local_id] ?? Number(a.attributes.order)) - (orders[b.ref.ref.local_id] ?? Number(b.attributes.order))), [outline.data, orders])
  const hasChanges = Boolean(titles.__new__?.trim()) || sections.some((section) =>
    (titles[section.ref.ref.local_id] != null && titles[section.ref.ref.local_id] !== String(section.attributes.title || ''))
    || (orders[section.ref.ref.local_id] != null && orders[section.ref.ref.local_id] !== Number(section.attributes.order))
    || Boolean(pendingReferences[section.ref.ref.local_id]?.length),
  )
  const save = useMutation({
    mutationFn: async () => {
      if (!outline.data) {
        const root = createTopologyElement(REPORT_CREATION_CONTRACT, {
          projectKey,
          moduleId: 'report',
          namespace: 'outline',
          typeId: 'outline_root',
          localId: target.state_id,
          observedRevision: '0',
          contentName: target.state_id,
          structuralRole: 'root',
          moduleAttributes: { hidden: true },
        })
        const initial = createTopologyState({
          profileId: 'information_topology.report_outline',
          profileVersion: '1',
          elements: [root],
        })
        const request: TopologyPatchBatchRequest = { state_patches: [{ target, base_revision: null, initial_state: initial }] }
        return informationTopologyClient.applyPatch(request)
      }
      const state = outline.data.topology
      const root = state.elements.find((item) => item.ref.ref.type_id === 'outline_root')
      if (!root) throw new Error('大纲缺少合成根，无法安全保存。')
      const current = sections.map((item, index) => {
        const additions = (pendingReferences[item.ref.ref.local_id] || []).map((reference, position) => ({
          role: 'argument', position: item.endpoints.filter((endpoint) => endpoint.role === 'argument').length + position,
          target: { ref: { project_key: projectKey, module_id: reference.module, namespace: reference.namespace, type_id: reference.type, local_id: reference.id }, observed_revision: reference.revision },
        }))
        return elementWith({ ...item, endpoints: [...item.endpoints, ...additions] }, titles[item.ref.ref.local_id] ?? String(item.attributes.title || ''), orders[item.ref.ref.local_id] ?? index)
      })
      const operations: TopologyPatchOperation[] = current.map((element) => ({ action: 'replace', ref: element.ref, element }))
      const newTitle = (titles.__new__ || '').trim()
      if (newTitle) {
        const localId = `section-${globalThis.crypto?.randomUUID?.() || Date.now()}`
        const ref = makeRef(projectKey, localId, '0')
        const section = createTopologyElement(REPORT_CREATION_CONTRACT, {
          projectKey,
          moduleId: 'report',
          namespace: 'outline',
          typeId: 'section',
          localId,
          observedRevision: '0',
          contentName: newTitle,
          contentOrder: current.length,
          structuralRole: 'member',
          moduleAttributes: {
            title: newTitle,
            order: current.length,
            ...(bodyVersion == null ? {} : { body_version: String(bodyVersion) }),
          },
          endpoints: [{ role: 'parent', target: root.ref }],
        })
        operations.push({ action: 'add', ref, element: section })
      }
      if (!operations.length) return null
      return informationTopologyClient.applyPatch({
        state_patches: [{ target: { ...target, revision: outline.data.revision }, base_revision: outline.data.revision, patch: operations }],
      })
    },
    onSuccess: async () => {
      setTitles({})
      setOrders({})
      setPendingReferences({})
      setReferenceText({})
      setStatus('大纲结构已保存，正在读取持久化版本…')
      await client.invalidateQueries({ queryKey: key })
      try {
        const refreshed = await client.fetchQuery({ queryKey: key, queryFn: () => informationTopologyClient.readTopology(target) })
        setStatus(`大纲已保存并读回（版本 ${refreshed.revision}）。正文未被修改。`)
      } catch {
        setStatus('大纲写入已完成，但刷新读回失败；请手动刷新确认持久化版本。正文未被修改。')
      }
    },
    onError: (error) => {
      const statusCode = error && typeof error === 'object' && 'response' in error
        ? Number((error as { response?: { status?: number } }).response?.status)
        : 0
      const conflictCode = error instanceof ApiClientError && error.code === 'VERSION_CONFLICT'
      setStatus((statusCode === 409 || conflictCode)
        ? '大纲版本冲突：其他编辑已先保存。请刷新后核对再编辑。'
        : `大纲保存失败：${error instanceof Error ? error.message : String(error)}`)
    },
  })

  const readStatus = outline.error && typeof outline.error === 'object' && 'response' in outline.error
    ? Number((outline.error as { response?: { status?: number } }).response?.status)
    : 0
  const isMissing = outline.isError && ((outline.error instanceof ApiClientError && outline.error.code === 'NOT_FOUND') || readStatus === 404)
  const documentIsSaved = documentId != null && bodyVersion != null
  return <section className="writing-topology-panel" aria-label="报告大纲拓扑" data-testid="writing-report-topology">
    <header><div><h2>报告结构</h2><p>大纲与正文分别保存；编辑大纲不会改写正文。</p></div>
      <button type="button" className="button-primary" disabled={!documentIsSaved || save.isPending || outline.isLoading || (!outline.data && !isMissing) || Boolean(outline.data && !hasChanges)} onClick={() => save.mutate()}>
        {save.isPending ? '保存中…' : outline.data ? '保存大纲' : '创建大纲'}
      </button>
    </header>
    {!documentIsSaved && <p role="status">请先保存当前文档，再创建与文档关联的大纲。</p>}
    {outline.isLoading && <p>读取大纲…</p>}
    {outline.isError && !isMissing && <p role="alert">大纲读取失败：{outline.error instanceof Error ? outline.error.message : String(outline.error)}</p>}
    {isMissing && documentIsSaved && <p>尚无此文档的大纲。点击“创建大纲”可建立空结构；正文仍由写作模块持有。</p>}
    {sections.map((section, index) => {
      const id = section.ref.ref.local_id
      const expected = section.attributes.body_version
      const drifted = expected != null && bodyVersion != null && String(expected) !== String(bodyVersion)
      return <div className="writing-topology-panel__section" key={refKey(section.ref)}>
        <label>第 {index + 1} 节标题
          <input aria-label={`第 ${index + 1} 节标题`} value={titles[id] ?? String(section.attributes.title || '')} onChange={(event) => setTitles((current) => ({ ...current, [id]: event.target.value }))} />
        </label>
        {drifted && <p role="status" className="writing-topology-panel__drift">正文版本已从 {String(expected)} 变为 {String(bodyVersion)}；大纲观察位置可能漂移，请人工核对。</p>}
        <div className="writing-topology-panel__refs" aria-label="章节论证与证据引用">
          {section.endpoints.filter((endpoint) => endpoint.role === 'argument').map((endpoint, refIndex) => <span key={`${endpoint.target.ref.local_id}-${refIndex}`}>
            {endpoint.target.ref.type_id}: {endpoint.target.ref.module_id}/{endpoint.target.ref.local_id}@{endpoint.target.observed_revision}
          </span>)}
          {section.endpoints.filter((endpoint) => endpoint.role === 'argument').length === 0 && <span>暂无判断或证据引用</span>}
        </div>
        <label>追加判断/证据/方法引用（类型|模块|命名空间|来源ID|版本）
          <input aria-label={`第 ${index + 1} 节追加引用`} placeholder="evidence|retrieval|default|e-12|3" value={referenceText[id] || ''} onChange={(event) => setReferenceText((current) => ({ ...current, [id]: event.target.value }))} />
        </label>
        <button type="button" className="button-secondary" onClick={() => {
          const [type, module, namespace, refId, revision] = (referenceText[id] || '').split('|').map((part) => part.trim())
          if (!['judgment', 'evidence', 'claim', 'argument', 'method'].includes(type) || !module || !namespace || !refId || !revision) {
            setStatus('引用格式无效。类型须为 judgment、evidence、claim、argument 或 method，并填写模块、命名空间、来源 ID 与版本。')
            return
          }
          setPendingReferences((current) => ({ ...current, [id]: [...(current[id] || []), { type, module, namespace, id: refId, revision }] }))
          setReferenceText((current) => ({ ...current, [id]: '' }))
          setStatus('引用已暂存；保存大纲后写入拓扑。')
        }}>暂存引用</button>
        {pendingReferences[id]?.length ? <p>待保存引用：{pendingReferences[id].length}</p> : null}
        <div className="writing-topology-panel__order">
          <button type="button" className="button-secondary" aria-label={`第 ${index + 1} 节上移`} disabled={index === 0} onClick={() => {
            const reordered = [...sections]; [reordered[index - 1], reordered[index]] = [reordered[index], reordered[index - 1]]
            setOrders(Object.fromEntries(reordered.map((item, position) => [item.ref.ref.local_id, position])))
          }}>上移</button>
          <button type="button" className="button-secondary" aria-label={`第 ${index + 1} 节下移`} disabled={index === sections.length - 1} onClick={() => {
            const reordered = [...sections]; [reordered[index + 1], reordered[index]] = [reordered[index], reordered[index + 1]]
            setOrders(Object.fromEntries(reordered.map((item, position) => [item.ref.ref.local_id, position])))
          }}>下移</button>
        </div>
      </div>
    })}
    {outline.data && <label>新增章节标题
      <input aria-label="新增章节标题" value={titles.__new__ || ''} onChange={(event) => setTitles((current) => ({ ...current, __new__: event.target.value }))} />
    </label>}
    {sections.length === 0 && outline.data && <p>空大纲（合成根不作为显示章节）。</p>}
    {status && <p role="status">{status}</p>}
  </section>
}
