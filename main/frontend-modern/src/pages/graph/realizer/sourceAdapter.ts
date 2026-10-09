import { getMarketGraph, getPolicyGraph, getSocialGraph, listAdminMaterials } from '../../../lib/api'
import type { AdminMaterialItem, GraphResponse } from '../../../lib/types'
import type { GraphProjectionDefinition } from './contract'
import { informationTopologyClient } from '../../../features/information-topology'
import { normalizeMaterialGraph, projectAdminMaterials } from './materialGraph'
import {
  hasProjectRetrievalSemantics,
  projectInformationTopologies,
  type TopologyProjectionFilter,
} from './topologyProjection'

export type GraphProjectionFilters = {
  startDate: string
  endDate: string
  state: string
  policyType: string
  platform: string
  topic: string
  game: string
  limit: number
}

/** Maps a project projection definition and its filters to the canonical graph shape. */
export async function readGraphProjection(
  projectKey: string,
  definition: GraphProjectionDefinition,
  filters: GraphProjectionFilters,
  topologyFilter?: TopologyProjectionFilter,
): Promise<GraphResponse> {
  const projectTopologies = await informationTopologyClient.listTopologies()
  if (hasProjectRetrievalSemantics(projectTopologies.items)) {
    return projectInformationTopologies(
      projectTopologies.items.filter((item) => item.profile_id.startsWith('retrieval.domain.')),
      topologyFilter,
    )
  }
  const materialItems: AdminMaterialItem[] = []
  const materialLimit = Math.max(1, Math.min(filters.limit, 2000))
  for (let page = 1; materialItems.length < materialLimit; page += 1) {
    const remaining = materialLimit - materialItems.length
    const response = await listAdminMaterials({
      page,
      page_size: Math.min(100, remaining),
      sort_by: 'created_at',
      sort_order: 'desc',
    })
    materialItems.push(...response.items)
    if (!response.items.length || materialItems.length >= response.total) break
  }
  const materialGraph = projectAdminMaterials(materialItems, projectKey)
  const common = {
    start_date: filters.startDate,
    end_date: filters.endDate,
    limit: filters.limit,
  }
  const domainGraph = definition.graphKind === 'policy'
    ? await getPolicyGraph({ ...common, state: filters.state, policy_type: filters.policyType })
    : definition.graphKind === 'social'
      ? await getSocialGraph({ ...common, platform: filters.platform, topic: filters.topic })
      : await getMarketGraph({
        ...common,
        state: filters.state,
        game: filters.game,
        view: definition.marketView,
        topic_scope: definition.topicScope,
      })
  return normalizeMaterialGraph({
    ...domainGraph,
    nodes: [...materialGraph.nodes, ...domainGraph.nodes],
    source_kind: materialGraph.nodes.length ? 'admin_materials' : domainGraph.source_kind,
  })
}
