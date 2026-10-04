import { getMarketGraph, getPolicyGraph, getSocialGraph } from '../../../lib/api'
import type { GraphResponse } from '../../../lib/types'
import type { GraphProjectionDefinition } from './contract'
import { informationTopologyClient } from '../../../features/information-topology'
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
  const common = {
    start_date: filters.startDate,
    end_date: filters.endDate,
    limit: filters.limit,
  }
  if (definition.graphKind === 'policy') {
    return getPolicyGraph({ ...common, state: filters.state, policy_type: filters.policyType })
  }
  if (definition.graphKind === 'social') {
    return getSocialGraph({ ...common, platform: filters.platform, topic: filters.topic })
  }
  return getMarketGraph({
    ...common,
    state: filters.state,
    game: filters.game,
    view: definition.marketView,
    topic_scope: definition.topicScope,
  })
}
