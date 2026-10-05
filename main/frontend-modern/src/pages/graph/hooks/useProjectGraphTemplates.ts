import { queryOptions, useQuery } from '@tanstack/react-query'
import { listWorkflowGraphTemplates } from '../../../lib/api'
import { getProjectKey } from '../../../lib/api/client'
import { queryKeys } from '../../../lib/queryKeys'
import { asTemplateRecord, type GraphTemplateRecord } from '../realizer/workflowTemplate'

export function projectGraphTemplatesQueryOptions(projectKey: string) {
  return queryOptions({
    queryKey: queryKeys.graph.templates(projectKey),
    queryFn: async ({ signal }) => {
      // The API client binds requests to the active project at dispatch time.
      signal.throwIfAborted()
      if (getProjectKey() !== projectKey) throw new Error('Graph template project changed before loading')
      const response = await listWorkflowGraphTemplates()
      signal.throwIfAborted()
      if (getProjectKey() !== projectKey) throw new Error('Graph template project changed while loading')
      return (response.items || [])
        .map(asTemplateRecord)
        .filter((item): item is GraphTemplateRecord => Boolean(item))
    },
    retry: false,
  })
}

export function useProjectGraphTemplates(projectKey: string, enabled = true) {
  return useQuery({
    ...projectGraphTemplatesQueryOptions(projectKey),
    enabled: enabled && Boolean(projectKey),
  })
}
