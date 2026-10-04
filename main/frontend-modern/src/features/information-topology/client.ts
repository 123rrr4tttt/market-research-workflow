import { httpGet, httpPost } from '../../lib/api/client'
import type {
  BoundRef,
  ElementRef,
  MappingPreview,
  TopologyPatchBatchRequest,
  TopologyPatchResult,
  TopologyProfileDescription,
  TopologyReadResult,
  TopologyRef,
  TopologyRelation,
  TopologyList,
  TopologyImportResult,
  TopologyExportResult,
  CurrentTopologyItem,
} from './types'

// Relative API paths intentionally use the shared transport: project headers,
// envelope handling, credentials, and the configured API base stay centralized.
const ROOT = '/api/v1/information-topology'

export const informationTopologyClient = {
  describeProfiles() {
    return httpGet<TopologyList<TopologyProfileDescription>>(`${ROOT}/profiles`)
  },
  listTopologies() {
    return httpGet<TopologyList<CurrentTopologyItem>>(`${ROOT}/topologies`)
  },
  resolve(refs: ElementRef[]) {
    return httpPost<TopologyList<BoundRef>>(`${ROOT}/resolve`, { refs })
  },
  readTopology(topologyRef: TopologyRef, filters: Record<string, unknown> = {}) {
    return httpPost<TopologyReadResult>(`${ROOT}/topologies/read`, { topology_ref: topologyRef, filters })
  },
  findRelations(ref: BoundRef, relationTypes?: string[], direction?: 'incoming' | 'outgoing' | 'both') {
    return httpPost<TopologyList<TopologyRelation>>(`${ROOT}/relations/find`, {
      ref,
      relation_types: relationTypes ?? [],
      direction: direction ?? 'both',
    })
  },
  previewMapping(mappingRef: string, inputRefs: TopologyRef[]) {
    return httpPost<MappingPreview>(`${ROOT}/mappings/preview`, { mapping_ref: mappingRef, input_refs: inputRefs })
  },
  applyPatch(request: TopologyPatchBatchRequest) {
    return httpPost<TopologyPatchResult>(`${ROOT}/patches`, request)
  },
  importStructure(moduleId: string, source: Record<string, unknown>) {
    return httpPost<TopologyImportResult>(`${ROOT}/imports`, { module_id: moduleId, source })
  },
  exportStructure(target: TopologyRef, format: string) {
    return httpPost<TopologyExportResult>(`${ROOT}/exports`, { target, format })
  },
}
