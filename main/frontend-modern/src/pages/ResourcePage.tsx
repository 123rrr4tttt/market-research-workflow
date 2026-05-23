import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, LoaderCircle, Play, Radar, RefreshCw, Save, Search } from 'lucide-react'
import {
  bindSiteEntry,
  discoverSiteEntriesAdvanced,
  extractResourcePoolFromDocuments,
  listResourcePoolUrlsWithFilters,
  listSourceLibraryChannels,
  listSourceLibraryItemsGrouped,
  listSourceLibraryItemsWithScope,
  listSiteEntriesWithFilters,
  registerExternalProject,
  refreshSourceLibraryItem,
  recommendSiteEntriesBatch,
  recommendSiteEntry,
  simplifySiteEntries,
  syncSourceLibraryHandlerClusters,
  upsertSourceLibraryItem,
  upsertSiteEntry,
} from '../lib/api'
import { translate, useAppLocale, type MessageKey } from '../app/platform/i18n'
import { queryKeys } from '../lib/queryKeys'
import type {
  ResourcePoolRecommendationItem,
  ResourcePoolRecommendationResponse,
  SourceLibraryItem,
  SourceLibraryScope,
} from '../lib/types'

type ResourcePageProps = {
  projectKey: string
  variant?: 'resource' | 'extract'
}

type ResourceMessageKey = MessageKey

const DEFAULT_EXTERNAL_HINTS_JSON = JSON.stringify({ query_terms: [] }, null, 2)

function formatResourceTemplate(template: string, values: Record<string, string | number | boolean>) {
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key: string) => String(values[key] ?? ''))
}

function splitToList(raw: string) {
  return raw
    .split(/\r?\n|,/)
    .map((v) => v.trim())
    .filter(Boolean)
}

function getItemSiteEntries(item: SourceLibraryItem) {
  const params = item.params && typeof item.params === 'object' ? item.params : {}
  const raw = (params.site_entries ?? params.site_entry_urls) as unknown
  if (Array.isArray(raw)) {
    return raw
      .map((entry) => {
        if (typeof entry === 'string') return entry.trim()
        if (entry && typeof entry === 'object') {
          const row = entry as Record<string, unknown>
          return String(row.site_url || row.url || '').trim()
        }
        return ''
      })
      .filter(Boolean)
  }
  if (typeof raw === 'string' && raw.trim()) return [raw.trim()]
  return []
}

function getItemUrlCount(item: SourceLibraryItem) {
  const maybe = (item as unknown as Record<string, unknown>).url_count
  if (typeof maybe === 'number' && Number.isFinite(maybe)) return maybe
  return getItemSiteEntries(item).length
}

function formatDate(value: string | null | undefined, locale: string) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString(locale)
}

function renderUrlFold(url?: string | null) {
  const raw = String(url || '').trim()
  if (!raw) return '-'
  if (raw.length <= 72) return raw
  const short = raw.slice(0, 48) + '...' + raw.slice(-16)
  return (
    <details>
      <summary title={raw} style={{ cursor: 'pointer' }}>
        {short}
      </summary>
      <div style={{ marginTop: 6, wordBreak: 'break-all' }}>{raw}</div>
    </details>
  )
}

function parseJsonObjectInput(raw: string, invalidObjectMessage: string) {
  const text = raw.trim()
  if (!text) return {}
  const parsed = JSON.parse(text)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(invalidObjectMessage)
  }
  return parsed as Record<string, unknown>
}

function getExternalProjectPlan(item: SourceLibraryItem | null | undefined) {
  const executionPlan = item?.execution_plan
  if (!executionPlan || typeof executionPlan !== 'object') return {}
  const planMeta = (executionPlan as Record<string, unknown>).plan_meta
  if (!planMeta || typeof planMeta !== 'object') return {}
  const externalProject = (planMeta as Record<string, unknown>).external_project
  return externalProject && typeof externalProject === 'object' ? (externalProject as Record<string, unknown>) : {}
}

export function ResourcePage({ projectKey, variant = 'resource' }: ResourcePageProps) {
  const locale = useAppLocale()
  const queryClient = useQueryClient()
  const t = (key: ResourceMessageKey, fallback?: string) => translate(locale, key, fallback)
  const tf = (key: ResourceMessageKey, values: Record<string, string | number | boolean>) =>
    formatResourceTemplate(t(key), values)
  const errorMessage = (error: unknown) => (error instanceof Error ? error.message : t('resourcePage.error.unknown'))

  const [sourceScope, setSourceScope] = useState<SourceLibraryScope>('effective')
  const [handlerSearch, setHandlerSearch] = useState('')
  const [itemForm, setItemForm] = useState({
    item_key: '',
    name: '',
    channel_key: '',
    extends_item_key: '',
    tags: '',
    description: '',
    enabled: true,
    site_entries: '',
  })
  const [itemParamsSnapshot, setItemParamsSnapshot] = useState<Record<string, unknown>>({})
  const [itemExtraSnapshot, setItemExtraSnapshot] = useState<Record<string, unknown>>({})
  const [externalProjectForm, setExternalProjectForm] = useState({
    project_link: '',
    item_key: '',
    name: '',
    description: '',
    tags: '',
    enabled: true,
    hints_json: DEFAULT_EXTERNAL_HINTS_JSON,
  })
  const [externalProjectPreview, setExternalProjectPreview] = useState<Record<string, unknown> | null>(null)

  const [domainFilter, setDomainFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [entryTypeFilter, setEntryTypeFilter] = useState('')

  const [resourceUrlPage, setResourceUrlPage] = useState(1)
  const [resourceSitePage, setResourceSitePage] = useState(1)

  const [newSiteUrl, setNewSiteUrl] = useState('')
  const [newSiteEntryType, setNewSiteEntryType] = useState('domain_root')

  const [actionPending, setActionPending] = useState(false)
  const [actionMessage, setActionMessage] = useState(() => t('resourcePage.status.ready'))
  const [actionError, setActionError] = useState('')

  const [discoverLimitDomains, setDiscoverLimitDomains] = useState('60')
  const [discoverDryRun, setDiscoverDryRun] = useState(false)

  const [recommendSiteUrl, setRecommendSiteUrl] = useState('')
  const [recommendEntryType, setRecommendEntryType] = useState('domain_root')
  const [recommendUseLlm, setRecommendUseLlm] = useState(true)
  const [singleRecommendation, setSingleRecommendation] = useState<ResourcePoolRecommendationResponse | null>(null)
  const [batchRecommendations, setBatchRecommendations] = useState<ResourcePoolRecommendationItem[]>([])
  const [bindingPending, setBindingPending] = useState(false)

  useEffect(() => {
    setResourceUrlPage(1)
    setResourceSitePage(1)
  }, [domainFilter, sourceFilter, entryTypeFilter])

  const sourceItems = useQuery({
    queryKey: queryKeys.sourceLibrary.items(projectKey, sourceScope),
    queryFn: () => listSourceLibraryItemsWithScope(sourceScope),
    enabled: Boolean(projectKey),
  })

  const sourceItemsGrouped = useQuery({
    queryKey: queryKeys.sourceLibrary.itemsGrouped(projectKey, sourceScope),
    queryFn: () => listSourceLibraryItemsGrouped(sourceScope),
    enabled: Boolean(projectKey),
  })

  const sourceChannels = useQuery({
    queryKey: queryKeys.sourceLibrary.channels(projectKey, sourceScope),
    queryFn: () => listSourceLibraryChannels(sourceScope),
    enabled: Boolean(projectKey),
  })

  const resourceUrls = useQuery({
    queryKey: queryKeys.resource.urls(projectKey, domainFilter, sourceFilter, resourceUrlPage),
    queryFn: () =>
      listResourcePoolUrlsWithFilters({
        page: resourceUrlPage,
        pageSize: 24,
        domain: domainFilter,
        source: sourceFilter,
      }),
    enabled: Boolean(projectKey),
  })

  const siteEntries = useQuery({
    queryKey: queryKeys.resource.siteEntries(projectKey, domainFilter, entryTypeFilter, resourceSitePage),
    queryFn: () =>
      listSiteEntriesWithFilters({
        page: resourceSitePage,
        pageSize: 24,
        domain: domainFilter,
        entryType: entryTypeFilter,
      }),
    enabled: Boolean(projectKey),
  })

  const siteEntryMutation = useMutation({
    mutationFn: async () => {
      if (!newSiteUrl.trim()) throw new Error(t('resourcePage.error.missingSiteUrl'))
      return upsertSiteEntry({
        site_url: newSiteUrl.trim(),
        entry_type: newSiteEntryType,
        scope: 'project',
      })
    },
    onSuccess: async () => {
      setNewSiteUrl('')
      setActionMessage(t('resourcePage.message.siteEntryCreated'))
      await queryClient.invalidateQueries({ queryKey: queryKeys.resource.siteEntriesBase(projectKey) })
    },
    onError: (error) => {
      setActionMessage(tf('resourcePage.message.siteEntryCreateFailed', { message: errorMessage(error) }))
    },
  })

  const runAction = async (name: string, fn: () => Promise<unknown>) => {
    setActionPending(true)
    setActionError('')
    setActionMessage(tf('resourcePage.status.running', { action: name }))
    try {
      const result = await fn()
      const payload = result && typeof result === 'object' ? (result as Record<string, unknown>) : {}
      const details = [
        'task_id',
        'item_key',
        'handler_key',
        'handler_count',
        'written',
        'inserted',
        'updated',
        'skipped',
        'added',
        'site_entries_after',
        'errors',
      ]
        .filter((key) => payload[key] !== undefined && payload[key] !== null && payload[key] !== '')
        .map((key) => `${key}=${String(payload[key])}`)
        .join(' | ')

      setActionMessage(
        details
          ? tf('resourcePage.status.completedWithDetails', { action: name, details })
          : tf('resourcePage.status.completed', { action: name }),
      )

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.resource.urlsBase(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.resource.siteEntriesBase(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsBase(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsGroupedBase(projectKey) }),
      ])
    } catch (error) {
      const message = errorMessage(error)
      setActionMessage(tf('resourcePage.status.failed', { action: name }))
      setActionError(tf('resourcePage.status.failedWithMessage', { action: name, message }))
    } finally {
      setActionPending(false)
    }
  }

  const bindOne = async (item: {
    site_url?: string
    entry_type?: string | null
    template?: string | null
    capabilities?: Record<string, unknown>
    source?: string
  }) => {
    if (!item.site_url) throw new Error(t('resourcePage.error.missingBindSiteUrl'))
    return bindSiteEntry({
      site_url: item.site_url,
      entry_type: item.entry_type || 'domain_root',
      template: item.template || null,
      capabilities: item.capabilities || {},
      source: item.source || 'recommended',
      source_ref: { action: 'recommend_bind' },
      scope: 'project',
    })
  }

  const fillItemForm = (item: SourceLibraryItem) => {
    const tags = Array.isArray(item.tags) ? item.tags.filter(Boolean) : []
    const params = item.params && typeof item.params === 'object' ? item.params : {}
    const extra = item.extra && typeof item.extra === 'object' ? item.extra : {}
    const siteEntries = getItemSiteEntries(item)
    setItemForm({
      item_key: item.item_key || '',
      name: item.name || item.item_key || '',
      channel_key: item.channel_key || '',
      extends_item_key: item.extends_item_key || '',
      tags: tags.join('\n'),
      description: item.description || '',
      enabled: item.enabled !== false,
      site_entries: siteEntries.join('\n'),
    })
    setItemParamsSnapshot(params)
    setItemExtraSnapshot(extra)
  }

  const runExternalProjectAction = async (persist: boolean) => {
    const projectLink = externalProjectForm.project_link.trim()
    if (!projectLink) throw new Error(t('resourcePage.error.missingProjectLink'))
    const response = await registerExternalProject({
      project_link: projectLink,
      item_key: externalProjectForm.item_key.trim() || undefined,
      name: externalProjectForm.name.trim() || undefined,
      description: externalProjectForm.description.trim() || undefined,
      tags: splitToList(externalProjectForm.tags),
      enabled: externalProjectForm.enabled,
      persist,
      hints: parseJsonObjectInput(externalProjectForm.hints_json, t('resourcePage.error.hintsJsonObject')),
    })
    const payload = response && typeof response === 'object' ? (response as Record<string, unknown>) : {}
    setExternalProjectPreview(payload)
    const item = payload.item
    if (item && typeof item === 'object') {
      fillItemForm(item as SourceLibraryItem)
    }
    if (persist) {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsBase(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsGroupedBase(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.channelsBase(projectKey) }),
      ])
    }
    const itemPayload = item && typeof item === 'object' ? (item as SourceLibraryItem) : null
    const externalPlan = getExternalProjectPlan(itemPayload)
    const registrationContext =
      payload.registration_context && typeof payload.registration_context === 'object'
        ? (payload.registration_context as Record<string, unknown>)
        : {}
    const endpointCandidates = Array.isArray(registrationContext.endpoint_candidates)
      ? registrationContext.endpoint_candidates.length
      : 0
    return {
      item_key: itemPayload?.item_key || '-',
      persisted: String(Boolean(payload.persisted)),
      execution_mode: String(externalPlan.execution_mode || '-'),
      endpoint_candidates: endpointCandidates,
    }
  }

  const saveSourceItem = async () => {
    const itemKey = itemForm.item_key.trim()
    const name = itemForm.name.trim()
    const channelKey = itemForm.channel_key.trim()
    if (!itemKey || !name || !channelKey) {
      throw new Error(t('resourcePage.error.missingSourceItemRequired'))
    }
    const nextParams = { ...itemParamsSnapshot }
    nextParams.site_entries = itemForm.site_entries
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
    delete (nextParams as Record<string, unknown>).site_entry_urls

    return upsertSourceLibraryItem({
      item_key: itemKey,
      name,
      channel_key: channelKey,
      description: itemForm.description.trim() || undefined,
      params: nextParams,
      tags: splitToList(itemForm.tags),
      extends_item_key: itemForm.extends_item_key.trim() || undefined,
      enabled: itemForm.enabled,
      extra: itemExtraSnapshot || {},
    })
  }

  const syncAndRefreshHandlerItem = async (item: SourceLibraryItem, handlerKey: string) => {
    if (!item?.item_key) throw new Error(t('resourcePage.error.missingItemKey'))
    if (!handlerKey || handlerKey === 'url_routing') throw new Error(t('resourcePage.error.unsupportedHandler'))

    const rawParams = item.params && typeof item.params === 'object' ? { ...item.params } : {}
    rawParams.site_entries = getItemSiteEntries(item)
    delete (rawParams as Record<string, unknown>).site_entry_urls
    const rawExtra = item.extra && typeof item.extra === 'object' ? { ...item.extra } : {}
    rawExtra.creation_handler = ['handler', 'entry_type'].join('.')
    rawExtra.expected_entry_type = handlerKey
    if (rawExtra.auto_maintain == null) rawExtra.auto_maintain = true

    await upsertSourceLibraryItem({
      item_key: item.item_key,
      name: item.name || item.item_key,
      channel_key: item.channel_key || ['handler', 'cluster'].join('.'),
      description: item.description || undefined,
      params: rawParams,
      tags: Array.isArray(item.tags) ? item.tags : [],
      schedule: item.schedule || undefined,
      extends_item_key: item.extends_item_key || undefined,
      enabled: item.enabled !== false,
      extra: rawExtra,
    })

    const refreshed = await refreshSourceLibraryItem(item.item_key, {
      incremental: true,
      max_site_entries: 500,
    })
    return {
      ...refreshed,
      item_key: item.item_key,
      handler_key: handlerKey,
    }
  }

  const handlerBuckets = useMemo(() => {
    const byHandler = sourceItemsGrouped.data?.by_handler || {}
    const keyword = handlerSearch.trim().toLowerCase()
    return Object.keys(byHandler)
      .sort()
      .map((handlerKey) => {
        const list = Array.isArray(byHandler[handlerKey]) ? byHandler[handlerKey] : []
        if (!keyword) return { handlerKey, total: list.length, items: list }
        const filtered = list.filter((item) => {
          const haystack = [handlerKey, item.item_key || '', item.name || '', item.channel_key || ''].join(' ').toLowerCase()
          return haystack.includes(keyword)
        })
        if (String(handlerKey).toLowerCase().includes(keyword)) {
          return { handlerKey, total: list.length, items: list }
        }
        if (!filtered.length) return null
        return { handlerKey, total: list.length, items: filtered }
      })
      .filter(Boolean) as Array<{ handlerKey: string; total: number; items: SourceLibraryItem[] }>
  }, [sourceItemsGrouped.data, handlerSearch])

  const bindAllRecommendations = async () => {
    if (!batchRecommendations.length && !singleRecommendation) {
      setActionError(t('resourcePage.error.noBindableRecommendation'))
      return
    }
    setBindingPending(true)
    setActionError('')
    try {
      const list = batchRecommendations.length
        ? batchRecommendations
        : [
            {
              site_url: recommendSiteUrl.trim(),
              entry_type: singleRecommendation?.entry_type || recommendEntryType,
              template: singleRecommendation?.template || null,
              capabilities: singleRecommendation?.capabilities || {},
              source: singleRecommendation?.source || 'recommended',
            },
          ]
      let success = 0
      let failed = 0
      for (const item of list) {
        try {
          await bindOne(item)
          success += 1
        } catch {
          failed += 1
        }
      }
      setActionMessage(tf('resourcePage.message.bindCompleted', { success, failed }))
      await queryClient.invalidateQueries({ queryKey: queryKeys.resource.siteEntriesBase(projectKey) })
    } catch (error) {
      setActionError(tf('resourcePage.message.bindAllFailed', { message: errorMessage(error) }))
    } finally {
      setBindingPending(false)
    }
  }

  return (
    <div className={`content-stack resource-page resource-page--${variant}`}>
      <section className="panel">
        <div className="panel-header">
          <h2>{t(variant === 'extract' ? 'resourcePage.title.extract' : 'resourcePage.title.resource')}</h2>
          <span className="chip">{variant === 'extract' ? 'extract' : 'resource'}</span>
        </div>
      </section>
      <section className="panel">
        <div className="panel-header">
          <h2>{t('resourcePage.title.resource')}</h2>
          <span className="chip">{tf('resourcePage.meta.project', { projectKey })}</span>
        </div>

        <div className="form-grid cols-4">
          <label>
            <span>{t('resourcePage.field.domain')}</span>
            <input
              value={domainFilter}
              onChange={(e) => setDomainFilter(e.target.value)}
              placeholder={t('resourcePage.placeholder.domain')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.source')}</span>
            <input
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              placeholder={t('resourcePage.placeholder.source')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.entryType')}</span>
            <input
              value={entryTypeFilter}
              onChange={(e) => setEntryTypeFilter(e.target.value)}
              placeholder={t('resourcePage.placeholder.entryType')}
            />
          </label>
          <div className="inline-actions">
            <button
              onClick={() => {
                queryClient.invalidateQueries({ queryKey: queryKeys.resource.urlsBase(projectKey) })
                queryClient.invalidateQueries({ queryKey: queryKeys.resource.siteEntriesBase(projectKey) })
                queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsBase(projectKey) })
                queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsGroupedBase(projectKey) })
                queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.channelsBase(projectKey) })
              }}
            >
              <RefreshCw size={14} />{t('resourcePage.action.refreshList')}
            </button>
          </div>
        </div>

        <div className="action-grid">
          <button disabled={actionPending} onClick={() => runAction(t('resourcePage.actionName.extractUrls'), () => extractResourcePoolFromDocuments(true))}>
            <Play size={16} />{t('resourcePage.action.extractUrls')}
          </button>
          <button
            disabled={actionPending}
            onClick={() =>
              runAction(t('resourcePage.actionName.discoverEntries'), () =>
                discoverSiteEntriesAdvanced({
                  limit_domains: Math.max(1, Number.parseInt(discoverLimitDomains, 10) || 60),
                  dry_run: discoverDryRun,
                  write: !discoverDryRun,
                  async_mode: true,
                }),
              )
            }
          >
            <Radar size={16} />{t('resourcePage.action.discoverEntries')}
          </button>
          <button disabled={actionPending} onClick={() => runAction(t('resourcePage.actionName.simplifyEntries'), () => simplifySiteEntries(false))}>
            <RefreshCw size={16} />{t('resourcePage.action.simplifyEntries')}
          </button>
        </div>

        <div className="form-grid cols-4" style={{ marginTop: 12 }}>
          <label>
            <span>{t('resourcePage.field.limitDomains')}</span>
            <input
              value={discoverLimitDomains}
              onChange={(e) => setDiscoverLimitDomains(e.target.value)}
              placeholder={t('resourcePage.placeholder.limit')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.dryRun')}</span>
            <select value={discoverDryRun ? 'true' : 'false'} onChange={(e) => setDiscoverDryRun(e.target.value === 'true')}>
              <option value="false">false</option>
              <option value="true">true</option>
            </select>
          </label>
        </div>

        <p className="status-line">{actionPending ? <LoaderCircle size={14} className="spinning" /> : <Play size={14} />}{actionMessage}</p>
        {actionError ? <p className="status-line">{tf('resourcePage.status.failureDetail', { message: actionError })}</p> : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{t('resourcePage.section.sourceItems')}</h2>
          <div className="inline-actions">
            <label>
              <span>{t('resourcePage.field.scope')}</span>
              <select value={sourceScope} onChange={(e) => setSourceScope(e.target.value as SourceLibraryScope)}>
                <option value="effective">effective</option>
                <option value="shared">shared</option>
                <option value="project">project</option>
              </select>
            </label>
            <button
              onClick={() => {
                queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsBase(projectKey) })
                queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.itemsGroupedBase(projectKey) })
                queryClient.invalidateQueries({ queryKey: queryKeys.sourceLibrary.channelsBase(projectKey) })
              }}
            >
              <RefreshCw size={14} />{t('resourcePage.action.refreshItems')}
            </button>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('resourcePage.field.itemKey')}</th>
                <th>{t('resourcePage.field.name')}</th>
                <th>{t('resourcePage.field.channelKey')}</th>
                <th>{t('resourcePage.field.scope')}</th>
                <th>{t('resourcePage.field.urlCount')}</th>
                <th>{t('resourcePage.field.enabled')}</th>
                <th>{t('resourcePage.field.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {(sourceItems.data || []).map((item) => (
                <tr key={item.item_key}>
                  <td>{item.item_key || '-'}</td>
                  <td>{item.name || '-'}</td>
                  <td>{item.channel_key || '-'}</td>
                  <td>{item.scope || '-'}</td>
                  <td>{getItemUrlCount(item)}</td>
                  <td>{String(item.enabled !== false)}</td>
                  <td>
                    <button onClick={() => fillItemForm(item)}>{t('resourcePage.action.edit')}</button>
                  </td>
                </tr>
              ))}
              {!sourceItems.data?.length ? (
                <tr>
                  <td colSpan={7} className="empty-cell">
                    {t('resourcePage.empty.items')}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{t('resourcePage.section.sourceItemEditor')}</h2>
          <div className="inline-actions">
            <button disabled={actionPending} onClick={() => void runAction(t('resourcePage.actionName.saveSourceItem'), saveSourceItem)}>
              <Save size={14} />{t('resourcePage.action.save')}
            </button>
          </div>
        </div>
        <div className="form-grid cols-4">
          <label>
            <span>{t('resourcePage.field.itemKey')}</span>
            <input value={itemForm.item_key} onChange={(e) => setItemForm((p) => ({ ...p, item_key: e.target.value }))} placeholder={t('resourcePage.placeholder.itemKey')} />
          </label>
          <label>
            <span>{t('resourcePage.field.name')}</span>
            <input value={itemForm.name} onChange={(e) => setItemForm((p) => ({ ...p, name: e.target.value }))} placeholder={t('resourcePage.placeholder.name')} />
          </label>
          <label>
            <span>{t('resourcePage.field.channelKey')}</span>
            <input
              list="source-channel-options"
              value={itemForm.channel_key}
              onChange={(e) => setItemForm((p) => ({ ...p, channel_key: e.target.value }))}
              placeholder={t('resourcePage.placeholder.channelKey')}
            />
            <datalist id="source-channel-options">
              {(sourceChannels.data || []).map((channel) => (
                <option key={channel.channel_key} value={channel.channel_key} />
              ))}
            </datalist>
          </label>
          <label>
            <span>{t('resourcePage.field.extendsItemKey')}</span>
            <input
              value={itemForm.extends_item_key}
              onChange={(e) => setItemForm((p) => ({ ...p, extends_item_key: e.target.value }))}
              placeholder={t('resourcePage.placeholder.extendsItemKey')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.enabled')}</span>
            <select
              value={itemForm.enabled ? 'true' : 'false'}
              onChange={(e) => setItemForm((p) => ({ ...p, enabled: e.target.value === 'true' }))}
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          </label>
          <label>
            <span>{t('resourcePage.field.tagsMultiline')}</span>
            <textarea
              rows={4}
              value={itemForm.tags}
              onChange={(e) => setItemForm((p) => ({ ...p, tags: e.target.value }))}
              placeholder={t('resourcePage.placeholder.tags')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.description')}</span>
            <textarea
              rows={4}
              value={itemForm.description}
              onChange={(e) => setItemForm((p) => ({ ...p, description: e.target.value }))}
              placeholder={t('resourcePage.placeholder.description')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.siteEntriesMultiline')}</span>
            <textarea
              rows={7}
              value={itemForm.site_entries}
              onChange={(e) => setItemForm((p) => ({ ...p, site_entries: e.target.value }))}
              placeholder={t('resourcePage.placeholder.oneUrlPerLine')}
            />
          </label>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{t('resourcePage.section.externalProject')}</h2>
          <div className="inline-actions">
            <button disabled={actionPending} onClick={() => void runAction(t('resourcePage.actionName.previewExternalProject'), () => runExternalProjectAction(false))}>
              <Search size={14} />{t('resourcePage.action.previewManifest')}
            </button>
            <button disabled={actionPending} onClick={() => void runAction(t('resourcePage.actionName.registerExternalProject'), () => runExternalProjectAction(true))}>
              <Save size={14} />{t('resourcePage.action.registerProject')}
            </button>
          </div>
        </div>
        <div className="form-grid cols-4">
          <label>
            <span>{t('resourcePage.field.projectLink')}</span>
            <input
              value={externalProjectForm.project_link}
              onChange={(e) => setExternalProjectForm((p) => ({ ...p, project_link: e.target.value }))}
              placeholder={t('resourcePage.placeholder.projectLink')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.itemKeyOptional')}</span>
            <input
              value={externalProjectForm.item_key}
              onChange={(e) => setExternalProjectForm((p) => ({ ...p, item_key: e.target.value }))}
              placeholder={t('resourcePage.placeholder.externalItemKey')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.nameOptional')}</span>
            <input
              value={externalProjectForm.name}
              onChange={(e) => setExternalProjectForm((p) => ({ ...p, name: e.target.value }))}
              placeholder={t('resourcePage.placeholder.displayName')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.enabled')}</span>
            <select
              value={externalProjectForm.enabled ? 'true' : 'false'}
              onChange={(e) => setExternalProjectForm((p) => ({ ...p, enabled: e.target.value === 'true' }))}
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          </label>
          <label>
            <span>{t('resourcePage.field.tagsMultiline')}</span>
            <textarea
              rows={4}
              value={externalProjectForm.tags}
              onChange={(e) => setExternalProjectForm((p) => ({ ...p, tags: e.target.value }))}
              placeholder={t('resourcePage.placeholder.tagsExternal')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.description')}</span>
            <textarea
              rows={4}
              value={externalProjectForm.description}
              onChange={(e) => setExternalProjectForm((p) => ({ ...p, description: e.target.value }))}
              placeholder={t('resourcePage.placeholder.optionalDescription')}
            />
          </label>
          <label style={{ gridColumn: ['span', 2].join(' ') }}>
            <span>{t('resourcePage.field.hintsJson')}</span>
            <textarea
              rows={8}
              value={externalProjectForm.hints_json}
              onChange={(e) => setExternalProjectForm((p) => ({ ...p, hints_json: e.target.value }))}
              placeholder={t('resourcePage.placeholder.hintsJson')}
            />
          </label>
        </div>
        {externalProjectPreview ? (
          <div style={{ marginTop: 16 }}>
            {(() => {
              const previewItem = externalProjectPreview.item && typeof externalProjectPreview.item === 'object'
                ? (externalProjectPreview.item as SourceLibraryItem)
                : null
              const externalPlan = getExternalProjectPlan(previewItem)
              const registrationContext =
                externalProjectPreview.registration_context && typeof externalProjectPreview.registration_context === 'object'
                  ? (externalProjectPreview.registration_context as Record<string, unknown>)
                  : {}
              const endpointCandidates = Array.isArray(registrationContext.endpoint_candidates)
                ? (registrationContext.endpoint_candidates as Array<Record<string, unknown>>)
                : []
              const preferredModes = Array.isArray(registrationContext.preferred_execution_modes)
                ? registrationContext.preferred_execution_modes.join(', ')
                : '-'
              return (
                <>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>{t('resourcePage.field.itemKey')}</th>
                          <th>{t('resourcePage.field.name')}</th>
                          <th>{t('resourcePage.field.persisted')}</th>
                          <th>{t('resourcePage.field.executionMode')}</th>
                          <th>{t('resourcePage.field.runnerRef')}</th>
                          <th>{t('resourcePage.field.sourceKind')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td>{previewItem?.item_key || '-'}</td>
                          <td>{previewItem?.name || '-'}</td>
                          <td>{String(Boolean(externalProjectPreview.persisted))}</td>
                          <td>{String(externalPlan.execution_mode || '-')}</td>
                          <td>{renderUrlFold(String(externalPlan.runner_ref || ''))}</td>
                          <td>{String(externalPlan.source_kind || '-')}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <p className="status-line">{tf('resourcePage.status.preferredExecutionModes', { modes: preferredModes })}</p>
                  {endpointCandidates.length ? (
                    <div className="table-wrap" style={{ marginTop: 12 }}>
                      <table>
                        <thead>
                          <tr>
                            <th>{t('resourcePage.field.executionMode')}</th>
                            <th>{t('resourcePage.field.runnerRef')}</th>
                            <th>{t('resourcePage.field.confidence')}</th>
                            <th>{t('resourcePage.field.reason')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {endpointCandidates.map((candidate, idx) => (
                            <tr key={`${candidate.runner_ref || idx}`}>
                              <td>{String(candidate.execution_mode || '-')}</td>
                              <td>{renderUrlFold(String(candidate.runner_ref || ''))}</td>
                              <td>{String(candidate.confidence || '-')}</td>
                              <td>{String(candidate.reason || '-')}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                  <details style={{ marginTop: 12 }}>
                    <summary style={{ cursor: 'pointer' }}>{t('resourcePage.detail.registrationContext')}</summary>
                    <pre style={{ marginTop: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {JSON.stringify(externalProjectPreview, null, 2)}
                    </pre>
                  </details>
                </>
              )
            })()}
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{t('resourcePage.section.handlerClusters')}</h2>
          <div className="inline-actions">
            <label>
              <span>{t('resourcePage.field.search')}</span>
              <input
                value={handlerSearch}
                onChange={(e) => setHandlerSearch(e.target.value)}
                placeholder={t('resourcePage.placeholder.handlerSearch')}
              />
            </label>
            <button
              disabled={actionPending}
              onClick={() =>
                void runAction(t('resourcePage.actionName.syncHandlerClusters'), () =>
                  syncSourceLibraryHandlerClusters({
                    incremental: true,
                    max_site_entries: 500,
                  }),
                )
              }
            >
              <Database size={14} />{t('resourcePage.action.syncHandlerClusters')}
            </button>
            <button onClick={() => void sourceItemsGrouped.refetch()}>
              <RefreshCw size={14} />{t('resourcePage.action.refreshClusters')}
            </button>
          </div>
        </div>
        {handlerBuckets.map((bucket) => (
          <div className="table-wrap" key={bucket.handlerKey} style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th colSpan={5}>
                    <code>{bucket.handlerKey}</code> ({bucket.items.length}/{bucket.total})
                  </th>
                </tr>
                <tr>
                  <th>{t('resourcePage.field.itemKey')}</th>
                  <th>{t('resourcePage.field.name')}</th>
                  <th>{t('resourcePage.field.channelKey')}</th>
                  <th>{t('resourcePage.field.enabled')}</th>
                  <th>{t('resourcePage.field.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {bucket.items.map((item) => (
                  <tr key={`${bucket.handlerKey}-${item.item_key}`}>
                    <td>{item.item_key || '-'}</td>
                    <td>{item.name || '-'}</td>
                    <td>{item.channel_key || '-'}</td>
                    <td>{String(item.enabled !== false)}</td>
                    <td>
                      <div className="inline-actions">
                        <button onClick={() => fillItemForm(item)}>{t('resourcePage.action.locate')}</button>
                        <button
                          disabled={actionPending}
                          onClick={() => void runAction(t('resourcePage.actionName.syncHandlerItem'), () => syncAndRefreshHandlerItem(item, bucket.handlerKey))}
                        >
                          {t('resourcePage.action.syncAndRefresh')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!bucket.items.length ? (
                  <tr>
                    <td colSpan={5} className="empty-cell">
                      {t('resourcePage.empty.noMatches')}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        ))}
        {!handlerBuckets.length ? <p className="status-line"><Search size={14} />{t('resourcePage.empty.handlerClusters')}</p> : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{t('resourcePage.section.recommendationBinding')}</h2>
          <div className="inline-actions">
            <button disabled={actionPending || bindingPending} onClick={bindAllRecommendations}>
              <Database size={14} />{t('resourcePage.action.bindAll')}
            </button>
          </div>
        </div>
        <div className="form-grid cols-4">
          <label>
            <span>{t('resourcePage.field.siteUrl')}</span>
            <input
              value={recommendSiteUrl}
              onChange={(e) => setRecommendSiteUrl(e.target.value)}
              placeholder={t('resourcePage.placeholder.siteUrl')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.entryType')}</span>
            <select value={recommendEntryType} onChange={(e) => setRecommendEntryType(e.target.value)}>
              <option value="domain_root">domain_root</option>
              <option value="rss">rss</option>
              <option value="sitemap">sitemap</option>
              <option value="search_template">search_template</option>
              <option value="official_api">official_api</option>
            </select>
          </label>
          <label>
            <span>{t('resourcePage.field.useLlm')}</span>
            <select value={recommendUseLlm ? 'true' : 'false'} onChange={(e) => setRecommendUseLlm(e.target.value === 'true')}>
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          </label>
          <div className="inline-actions">
            <button
              disabled={actionPending || !recommendSiteUrl.trim()}
              onClick={() =>
                runAction(t('resourcePage.actionName.singleRecommendation'), async () => {
                  const response = await recommendSiteEntry({
                    site_url: recommendSiteUrl.trim(),
                    entry_type: recommendEntryType,
                    use_llm: recommendUseLlm,
                  })
                  setSingleRecommendation(response)
                  return response
                })
              }
            >
              <Play size={14} />{t('resourcePage.action.singleRecommendation')}
            </button>
            <button
              disabled={actionPending || !(siteEntries.data || []).length}
              onClick={() =>
                runAction(t('resourcePage.actionName.batchRecommendation'), async () => {
                  const response = await recommendSiteEntriesBatch({
                    entries: (siteEntries.data || [])
                      .filter((item) => Boolean(item.site_url))
                      .map((item) => ({
                        site_url: String(item.site_url),
                        entry_type: item.entry_type || null,
                        template: null,
                      })),
                    use_llm: recommendUseLlm,
                  })
                  setBatchRecommendations(response.items || [])
                  return { ...response, written: response.count ?? response.items?.length ?? 0 }
                })
              }
            >
              <Radar size={14} />{t('resourcePage.action.batchRecommendation')}
            </button>
          </div>
        </div>
        {singleRecommendation ? (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th>{t('resourcePage.field.mode')}</th>
                  <th>{t('resourcePage.field.entryType')}</th>
                  <th>{t('resourcePage.field.template')}</th>
                  <th>{t('resourcePage.field.source')}</th>
                  <th>{t('resourcePage.field.validated')}</th>
                  <th>{t('resourcePage.field.actions')}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{t('resourcePage.mode.single')}</td>
                  <td>{singleRecommendation.entry_type || '-'}</td>
                  <td>{singleRecommendation.template || '-'}</td>
                  <td>{singleRecommendation.source || '-'}</td>
                  <td>{String(singleRecommendation.validated ?? false)}</td>
                  <td>
                    <button
                      disabled={bindingPending || !recommendSiteUrl.trim()}
                      onClick={() =>
                        runAction(t('resourcePage.actionName.bindSingleRecommendation'), () =>
                          bindOne({
                            site_url: recommendSiteUrl.trim(),
                            entry_type: singleRecommendation.entry_type || recommendEntryType,
                            template: singleRecommendation.template || null,
                            capabilities: singleRecommendation.capabilities || {},
                            source: singleRecommendation.source || 'recommended',
                          }),
                        )
                      }
                    >
                      {t('resourcePage.action.bind')}
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        ) : null}
        {batchRecommendations.length ? (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th>{t('resourcePage.field.siteUrl')}</th>
                  <th>{t('resourcePage.field.entryType')}</th>
                  <th>{t('resourcePage.field.template')}</th>
                  <th>{t('resourcePage.field.source')}</th>
                  <th>{t('resourcePage.field.validated')}</th>
                  <th>{t('resourcePage.field.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {batchRecommendations.map((item, idx) => (
                  <tr key={`${item.site_url || idx}`}>
                    <td>{renderUrlFold(item.site_url)}</td>
                    <td>{item.entry_type || '-'}</td>
                    <td>{item.template || '-'}</td>
                    <td>{item.source || '-'}</td>
                    <td>{String(item.validated ?? false)}</td>
                    <td>
                      <button disabled={bindingPending || !item.site_url} onClick={() => runAction(t('resourcePage.actionName.bindBatchRecommendation'), () => bindOne(item))}>
                        {t('resourcePage.action.bind')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{t('resourcePage.section.manualEntry')}</h2>
        </div>
        <div className="form-grid cols-3">
          <label>
            <span>{t('resourcePage.field.siteUrl')}</span>
            <input
              value={newSiteUrl}
              onChange={(e) => setNewSiteUrl(e.target.value)}
              placeholder={t('resourcePage.placeholder.siteUrl')}
            />
          </label>
          <label>
            <span>{t('resourcePage.field.entryType')}</span>
            <select value={newSiteEntryType} onChange={(e) => setNewSiteEntryType(e.target.value)}>
              <option value="domain_root">domain_root</option>
              <option value="rss">rss</option>
              <option value="sitemap">sitemap</option>
              <option value="search_template">search_template</option>
              <option value="official_api">official_api</option>
            </select>
          </label>
          <div className="inline-actions">
            <button disabled={siteEntryMutation.isPending} onClick={() => siteEntryMutation.mutate()}>
              <Database size={14} />{t('resourcePage.action.addEntry')}
            </button>
          </div>
        </div>
      </section>

      <section className="panel two-col">
        <div>
          <div className="panel-header">
            <h2>{t('resourcePage.section.urlPool')}</h2>
            <div className="inline-actions">
              <button disabled={resourceUrlPage <= 1} onClick={() => setResourceUrlPage((p) => Math.max(1, p - 1))}>
                {t('resourcePage.action.previousPage')}
              </button>
              <span className="chip">{tf('resourcePage.pagination.page', { page: resourceUrlPage })}</span>
              <button onClick={() => setResourceUrlPage((p) => p + 1)}>{t('resourcePage.action.nextPage')}</button>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t('resourcePage.field.url')}</th>
                  <th>{t('resourcePage.field.domain')}</th>
                  <th>{t('resourcePage.field.source')}</th>
                  <th>{t('resourcePage.field.createdAt')}</th>
                </tr>
              </thead>
              <tbody>
                {(resourceUrls.data || []).map((item, idx) => (
                  <tr key={`${item.id || item.url || idx}`}>
                    <td>{renderUrlFold(item.url)}</td>
                    <td>{item.domain || '-'}</td>
                    <td>{item.source || '-'}</td>
                    <td>{formatDate(item.created_at, locale)}</td>
                  </tr>
                ))}
                {!resourceUrls.data?.length ? (
                  <tr>
                    <td colSpan={4} className="empty-cell">
                      {t('resourcePage.empty.urls')}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="panel-header">
            <h2>{t('resourcePage.section.siteEntries')}</h2>
            <div className="inline-actions">
              <button disabled={resourceSitePage <= 1} onClick={() => setResourceSitePage((p) => Math.max(1, p - 1))}>
                {t('resourcePage.action.previousPage')}
              </button>
              <span className="chip">{tf('resourcePage.pagination.page', { page: resourceSitePage })}</span>
              <button onClick={() => setResourceSitePage((p) => p + 1)}>{t('resourcePage.action.nextPage')}</button>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t('resourcePage.field.siteUrl')}</th>
                  <th>{t('resourcePage.field.domain')}</th>
                  <th>{t('resourcePage.field.entryType')}</th>
                  <th>{t('resourcePage.field.source')}</th>
                  <th>{t('resourcePage.field.enabled')}</th>
                </tr>
              </thead>
              <tbody>
                {(siteEntries.data || []).map((item, idx) => (
                  <tr key={`${item.id || item.site_url || idx}`}>
                    <td>{renderUrlFold(item.site_url)}</td>
                    <td>{item.domain || '-'}</td>
                    <td>{item.entry_type || '-'}</td>
                    <td>{item.source || '-'}</td>
                    <td>{String(item.enabled ?? true)}</td>
                  </tr>
                ))}
                {!siteEntries.data?.length ? (
                  <tr>
                    <td colSpan={5} className="empty-cell">
                      {t('resourcePage.empty.siteEntries')}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  )
}

export default ResourcePage
