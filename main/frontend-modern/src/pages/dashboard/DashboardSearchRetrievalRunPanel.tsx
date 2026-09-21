import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { translate, useAppLocale } from '../../app/platform/i18n'
import { getSearchRetrievalRun } from '../../lib/api'
import { stringifyJson } from '../../lib/dashboardDiagnostics'

type DashboardSearchRetrievalRunPanelProps = {
  projectKey: string
}

function formatDashboardTemplate(template: string, values: Record<string, string | number>) {
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key: string) => String(values[key] ?? ''))
}

function asRecord(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function formatUnknownValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') return stringifyJson(value)
  return String(value)
}

export function DashboardSearchRetrievalRunPanel({ projectKey }: DashboardSearchRetrievalRunPanelProps) {
  const locale = useAppLocale()
  type DashboardMessageKey = Parameters<typeof translate>[1]
  const t = (key: DashboardMessageKey, fallback?: string) => translate(locale, key, fallback)
  const formatTemplate = (key: DashboardMessageKey, values: Record<string, string | number>) =>
    formatDashboardTemplate(t(key), values)
  const [searchRunIdInput, setSearchRunIdInput] = useState('')
  const [searchRunIdSelection, setSearchRunIdSelection] = useState('')
  const searchRetrievalRun = useQuery({
    queryKey: ['dashboard-search-retrieval-run', projectKey, searchRunIdSelection],
    queryFn: () => getSearchRetrievalRun(searchRunIdSelection),
    enabled: Boolean(projectKey && searchRunIdSelection),
  })
  const searchProviderTrace = asRecord(searchRetrievalRun.data?.provider_trace)
  const searchIndexFreshness = asRecord(searchRetrievalRun.data?.index_freshness)
  const searchReadback = asRecord(searchRetrievalRun.data?.retrieval_run_readback || searchRetrievalRun.data?.readback)
  const openSearchRetrievalRun = () => {
    const trimmed = searchRunIdInput.trim()
    if (!trimmed) return
    setSearchRunIdSelection(trimmed)
  }

  return (
    <section className="panel" data-testid="dashboard-search-retrieval-run-panel">
      <div className="panel-header">
        <h3>{t('dashboardPage.section.searchRetrievalRunDetail')}</h3>
      </div>
      <p className="status-line">
        {t('dashboardPage.hint.searchRetrievalRunDetail')}
      </p>
      <div className="inline-actions">
        <input
          data-testid="dashboard-search-run-id-input"
          value={searchRunIdInput}
          onChange={(event) => setSearchRunIdInput(event.target.value)}
          placeholder="retrieval_run_..."
          aria-label={t('dashboardPage.aria.searchRetrievalRunId')}
        />
        <button
          type="button"
          data-testid="dashboard-load-search-run"
          disabled={!searchRunIdInput.trim() || searchRetrievalRun.isFetching}
          onClick={openSearchRetrievalRun}
        >
          {searchRetrievalRun.isFetching
            ? t('dashboardPage.action.loadingSearchRetrievalRun')
            : t('dashboardPage.action.loadSearchRetrievalRun')}
        </button>
        {searchRunIdSelection ? (
          <span className="status-line">
            {formatTemplate('dashboardPage.status.currentSearchRetrievalRun', { id: searchRunIdSelection })}
          </span>
        ) : null}
        {searchRetrievalRun.isError ? (
          <span className="status-line">{t('dashboardPage.error.searchRetrievalRunLoadFailed')}</span>
        ) : null}
      </div>
      {searchRetrievalRun.data ? (
        <div className="status-line">
          <p>
            <strong>{t('dashboardPage.field.retrievalRunId')}</strong>: {searchRetrievalRun.data.retrieval_run_id || searchRunIdSelection || '-'}
          </p>
          <p>
            <strong>{t('dashboardPage.field.provider')}</strong>: {formatUnknownValue(searchProviderTrace?.providers_used)}
          </p>
          <p>
            <strong>{t('dashboardPage.field.indexBackend')}</strong>: {formatUnknownValue(searchIndexFreshness?.index_backend || searchProviderTrace?.index_backend)}
          </p>
          <p>
            <strong>{t('dashboardPage.field.fallbackUsed')}</strong>: {formatUnknownValue(searchProviderTrace?.fallback_used ?? searchIndexFreshness?.fallback_used)}
          </p>
          <p>
            <strong>{t('dashboardPage.field.freshnessState')}</strong>: {formatUnknownValue(searchIndexFreshness?.freshness_state)}
          </p>
          <p>
            <strong>{t('dashboardPage.field.readbackAvailable')}</strong>: {formatUnknownValue(searchReadback?.readback_available ?? searchIndexFreshness?.readback_available)}
          </p>
          <p>{t('dashboardPage.field.sourceRefs')}</p>
          <pre data-testid="dashboard-search-run-source-refs">
            {stringifyJson(searchRetrievalRun.data.source_refs || [])}
          </pre>
          <p>{t('dashboardPage.field.providerTrace')}</p>
          <pre data-testid="dashboard-search-run-provider-trace">
            {stringifyJson(searchRetrievalRun.data.provider_trace || {})}
          </pre>
          <p>{t('dashboardPage.field.indexFreshness')}</p>
          <pre data-testid="dashboard-search-run-index-freshness">
            {stringifyJson(searchRetrievalRun.data.index_freshness || {})}
          </pre>
        </div>
      ) : null}
    </section>
  )
}
