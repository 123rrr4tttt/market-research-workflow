import { apiClient, unwrapEnvelope } from '../../lib/api/client'
import { endpoints } from '../../lib/api/endpoints'

export type CellRecord = Record<string, unknown>
export type CellEnvironment = {
  contract_version: string
  project_key: string
  package: (CellRecord & { package_id: string; package_version: string }) | null
  definition: {
    cell_id: string
    version: string
    owner: string
    core_binding_ref: string
    core_mode: string
    conceptual_rule_refs: string[]
    skill_contents: (CellRecord & { skill_id: string })[]
    tool_refs: string[]
    facility_refs: string[]
    readback_refs: string[]
    relations: (CellRecord & { relation_id: string })[]
    operation: CellRecord & {
      inputs: CellRecord
      outputs: CellRecord
      authority_ref: string
      stop_ref: string
      failure_refs: string[]
      effect_refs: string[]
    }
  }
  skills: (CellRecord & { skill_id: string; relative_path: string })[]
  tools: (CellRecord & { name: string; description_for_model: string })[]
  declared_tool_names: string[]
  facilities: (CellRecord & { binding_id: string; readback_semantics: string })[]
}
export type CellSnapshot = { environment: CellEnvironment; environment_digest: string }
export type CellEntry = { id: string; title: string; caption?: string; data: CellRecord }
export type CellSection = { id: string; number: string; title: string; en: string; layer: number; entries: CellEntry[] }

export async function readCell(projectKey: string, packageIdentity: string, signal: AbortSignal): Promise<CellSnapshot> {
  const [package_id, package_version] = packageIdentity ? JSON.parse(packageIdentity) as [string, string] : []
  const { data } = await apiClient.get(endpoints.agentCell.structure, { params: { package_id, package_version }, signal })
  const snapshot = unwrapEnvelope<CellSnapshot>(data)
  if (snapshot.environment.project_key !== projectKey) throw new Error('项目已切换，请刷新胞腔')
  return snapshot
}

// These are presentation slices of the host descriptor, not new registrations.
export function cellSections(environment: CellEnvironment): CellSection[] {
  const d = environment.definition
  const op = d.operation
  const refs = (values: string[], key: string): CellEntry[] => values.map((ref) => ({ id: ref, title: ref, data: { [key]: ref } }))
  const rows: Omit<CellSection, 'number'>[] = [
    { id: 'rules', title: '概念规定', en: 'CONCEPT', layer: 0, entries: refs(d.conceptual_rule_refs, 'rule_ref') },
    { id: 'identity', title: '身份与组成', en: 'IDENTITY', layer: 0, entries: [{
      id: d.cell_id, title: d.cell_id, caption: environment.package ? '已激活注册包' : '基础环境',
      data: { cell_id: d.cell_id, version: d.version, owner: d.owner, package: environment.package },
    }] },
    { id: 'expression', title: '开放表达', en: 'EXPRESSION', layer: 0, entries: [
      { id: 'inputs', title: '输入合同', data: op.inputs },
      { id: 'outputs', title: '成果合同', data: op.outputs },
    ] },
    { id: 'lifecycle', title: '生命周期', en: 'LIFECYCLE', layer: 0, entries: [
      { id: 'authority', title: op.authority_ref, caption: 'Authority', data: { authority_ref: op.authority_ref } },
      { id: 'stop', title: op.stop_ref, caption: 'Stop', data: { stop_ref: op.stop_ref } },
      ...refs(op.failure_refs, 'failure_ref'),
      ...refs(op.effect_refs, 'effect_ref'),
    ] },
    { id: 'skills', title: 'Skills', en: 'METHOD', layer: 1, entries: environment.skills.map((s) => ({
      id: s.skill_id, title: s.skill_id, caption: s.relative_path,
      data: { ...d.skill_contents.find((item) => item.skill_id === s.skill_id), ...s },
    })) },
    { id: 'tools', title: 'Tools', en: 'CAPABILITY', layer: 1, entries: environment.tools.map((t) => ({
      id: t.name, title: t.name, caption: environment.declared_tool_names.includes(t.name) ? '胞腔声明引用' : '宿主注册', data: t,
    })) },
    { id: 'facilities', title: '设施', en: 'FACILITY', layer: 1, entries: environment.facilities.map((f) => ({
      id: f.binding_id, title: f.binding_id, caption: f.readback_semantics, data: f,
    })) },
    { id: 'relations', title: '关系', en: 'RELATION', layer: 2, entries: d.relations.map((r) => ({
      id: r.relation_id, title: r.relation_id, caption: `${r.source_ref} → ${r.target_ref}`, data: r,
    })) },
    { id: 'readbacks', title: '读回', en: 'READBACK', layer: 2, entries: d.readback_refs.map((ref) => ({
      id: ref, title: ref, data: environment.facilities.find((f) => f.binding_id === ref) ?? { readback_ref: ref },
    })) },
  ]
  return rows.map((row, i) => ({ ...row, number: String(i + 1).padStart(2, '0') }))
}

export function cellFailure(error: unknown): { message: string; packages: [string, string][] } {
  const response = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
  const envelope = (response?.detail ?? response) as { error?: { message?: string; details?: { activated?: unknown } } } | undefined
  const candidates = envelope?.error?.details?.activated
  return {
    message: envelope?.error?.message ?? (error instanceof Error ? error.message : '胞腔信息暂不可用'),
    packages: Array.isArray(candidates) ? candidates.filter((p): p is [string, string] =>
      Array.isArray(p) && p.length === 2 && p.every((item) => typeof item === 'string')) : [],
  }
}
