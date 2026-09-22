import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Settings2 } from 'lucide-react'
import {
  copyProjectLlmTemplates,
  getEnvSettings,
  listProjectLlmTemplates,
  updateEnvSettings,
  updateProjectLlmTemplate,
} from '../lib/api'
import { hashByMode } from '../app/navigation'
import { isApiClientError } from '../lib/api/client'
import { getLocalJson, removeLocal, setLocalJson } from '../lib/localStore'
import { queryKeys } from '../lib/queryKeys'
import type { EnvSettings, LlmServiceConfigItem, LlmTemplateUpdatePayload } from '../lib/types'
import { APP_THEMES, isAppTheme, setAppTheme, useAppTheme, type AppTheme } from '../app/platform/theme'
import { APP_LOCALES, setAppLocale, translate, useAppLocale, type MessageKey } from '../app/platform/i18n'

export type SettingsPageProps = {
  projectKey: string
  variant?: 'settings' | 'llm'
}

type StatusIntentMode = 'sysSettings' | 'sysLlm' | 'sysCrawler' | 'sysBackend'
type StatusIntentGuide = 'llm' | 'search' | 'news' | 'db' | 'es'
type StatusNavIntent = {
  mode: StatusIntentMode
  focusField?: string
  guide?: StatusIntentGuide
  ts: number
}

type SettingsDraftCache = {
  envDraft: EnvSettings | null
  templateDrafts: Record<string, ProjectLlmTemplateDraft>
  copySourceProjectKey: string
  copyOverwrite: boolean
  expandedService: string | null
}

const STATUS_NAV_INTENT_KEY = 'app_status_nav_intent_v1'
const SETTINGS_DRAFT_PREFIX = 'settings_page_draft_v1'

const GUIDE_MESSAGE_KEYS: Record<StatusIntentGuide, MessageKey> = {
  llm: 'settingsPage.guide.llm',
  search: 'settingsPage.guide.search',
  news: 'settingsPage.guide.news',
  db: 'settingsPage.guide.db',
  es: 'settingsPage.guide.es',
}

const GUIDE_SNIPPET_KEYS: Record<StatusIntentGuide, MessageKey> = {
  llm: 'settingsPage.snippet.llm',
  search: 'settingsPage.snippet.search',
  news: 'settingsPage.snippet.news',
  db: 'settingsPage.snippet.db',
  es: 'settingsPage.snippet.es',
}

const ENV_KEYS = [
  'DATABASE_URL',
  'ES_URL',
  'REDIS_URL',
  'LLM_PROVIDER',
  'OPENAI_API_KEY',
  'OPENAI_API_BASE',
  'AZURE_API_KEY',
  'AZURE_API_BASE',
  'AZURE_API_VERSION',
  'AZURE_CHAT_DEPLOYMENT',
  'AZURE_EMBEDDING_DEPLOYMENT',
  'OLLAMA_BASE_URL',
  'LEGISCAN_API_KEY',
  'NEWS_API_KEY',
  'SERPAPI_KEY',
  'SERPSTACK_KEY',
  'SERPER_API_KEY',
  'GOOGLE_SEARCH_API_KEY',
  'GOOGLE_SEARCH_CSE_ID',
  'AZURE_SEARCH_ENDPOINT',
  'AZURE_SEARCH_KEY',
] as const

function formatSettingsTemplate(template: string, values: Record<string, string | number>) {
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key: string) => String(values[key] ?? ''))
}

function formatDate(value: string | null | undefined, locale: (typeof APP_LOCALES)[number]) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString(locale)
}

type ProjectLlmTemplateItem = LlmServiceConfigItem & {
  system_prompt?: string | null
  user_prompt_template?: string | null
  top_p?: number | null
  presence_penalty?: number | null
  frequency_penalty?: number | null
}

type ProjectLlmTemplateDraft = {
  model: string
  temperature: string
  top_p: string
  presence_penalty: string
  frequency_penalty: string
  max_tokens: string
  enabled: boolean
  system_prompt: string
  user_prompt_template: string
}

export type SettingsPageViewProps = {
  projectKey: string
  variant: 'settings' | 'llm'
  locale: (typeof APP_LOCALES)[number]
  appTheme: AppTheme
  themeLabelByValue: Record<AppTheme, string>
  localeLabelByValue: Record<(typeof APP_LOCALES)[number], string>
  effectiveEnvDraft: EnvSettings
  templateItems: ProjectLlmTemplateItem[]
  envSettingsFetching: boolean
  envSettingsError: boolean
  llmTemplatesFetching: boolean
  llmTemplatesError: boolean
  envSavePending: boolean
  templateSavePending: boolean
  copyTemplatesPending: boolean
  hasAnyEnvValue: boolean
  saveMessage: string
  templateMessage: string
  copyMessage: string
  copySourceProjectKey: string
  copyOverwrite: boolean
  expandedService: string | null
  savingService: string | null
  guideType: StatusIntentGuide | null
  focusField: string
  envSnippet: string
  templateDrafts: Record<string, ProjectLlmTemplateDraft>
  onLocaleChange: (locale: (typeof APP_LOCALES)[number]) => void
  onThemeChange: (theme: AppTheme) => void
  onRefreshEnv: () => void
  onCopySnippet: () => void
  onDismissGuide: () => void
  onNavigateCrawler: () => void
  onEnvDraftChange: (key: string, value: string) => void
  onSaveEnv: () => void
  onRefreshTemplates: () => void
  onCopySourceProjectKeyChange: (value: string) => void
  onCopyOverwriteChange: (value: boolean) => void
  onCopyTemplates: () => void
  onExpandedServiceChange: (serviceName: string | null) => void
  onTemplateDraftChange: (serviceName: string, patch: Partial<ProjectLlmTemplateDraft>) => void
  onSaveTemplate: (serviceName: string, draft: ProjectLlmTemplateDraft) => void
}

function toDraft(item: ProjectLlmTemplateItem): ProjectLlmTemplateDraft {
  return {
    model: item.model ?? '',
    temperature: item.temperature == null ? '' : String(item.temperature),
    top_p: item.top_p == null ? '' : String(item.top_p),
    presence_penalty: item.presence_penalty == null ? '' : String(item.presence_penalty),
    frequency_penalty: item.frequency_penalty == null ? '' : String(item.frequency_penalty),
    max_tokens: item.max_tokens == null ? '' : String(item.max_tokens),
    enabled: Boolean(item.enabled),
    system_prompt: item.system_prompt ?? '',
    user_prompt_template: item.user_prompt_template ?? '',
  }
}

function toNullableText(value: string) {
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

function toNullableNumber(value: string) {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

function toNullableInt(value: string) {
  const numeric = toNullableNumber(value)
  if (numeric == null) return null
  return Math.trunc(numeric)
}

function getTraceId(meta: unknown): string {
  if (!meta || typeof meta !== 'object') return ''
  const traceId = (meta as { trace_id?: unknown; traceId?: unknown }).trace_id ?? (meta as { traceId?: unknown }).traceId
  return typeof traceId === 'string' && traceId.trim() ? traceId.trim() : ''
}

function formatActionError(locale: (typeof APP_LOCALES)[number], error: unknown) {
  const t = (key: MessageKey) => translate(locale, key)
  if (isApiClientError(error)) {
    const details: string[] = []
    if (error.code) details.push(formatSettingsTemplate(t('settingsPage.error.codeDetail'), { code: error.code }))
    const traceId = getTraceId(error.meta)
    if (traceId) details.push(formatSettingsTemplate(t('settingsPage.error.traceDetail'), { traceId }))
    return details.length
      ? formatSettingsTemplate(t('settingsPage.error.withDetails'), {
        message: error.message,
        details: details.join(t('settingsPage.error.detailSeparator')),
      })
      : error.message
  }
  if (error instanceof Error && error.message) return error.message
  return t('settingsPage.error.unknown')
}

export function SettingsPage({ projectKey, variant = 'settings' }: SettingsPageProps) {
  const queryClient = useQueryClient()
  const locale = useAppLocale()
  const appTheme = useAppTheme()
  const [envDraft, setEnvDraft] = useState<EnvSettings | null>(null)
  const [saveMessage, setSaveMessage] = useState('')
  const [templateDrafts, setTemplateDrafts] = useState<Record<string, ProjectLlmTemplateDraft>>({})
  const [templateMessage, setTemplateMessage] = useState('')
  const [copySourceProjectKey, setCopySourceProjectKey] = useState('')
  const [copyOverwrite, setCopyOverwrite] = useState(false)
  const [copyMessage, setCopyMessage] = useState('')
  const [expandedService, setExpandedService] = useState<string | null>(null)
  const [savingService, setSavingService] = useState<string | null>(null)
  const [guideType, setGuideType] = useState<StatusIntentGuide | null>(null)
  const [focusField, setFocusField] = useState('')
  const draftStorageKey = useMemo(() => [SETTINGS_DRAFT_PREFIX, projectKey, variant].join(':'), [projectKey, variant])
  const t = (key: MessageKey) => translate(locale, key)

  const envSettings = useQuery({
    queryKey: queryKeys.settings.env(),
    queryFn: getEnvSettings,
    enabled: Boolean(projectKey),
  })

  const llmTemplates = useQuery({
    queryKey: queryKeys.settings.projectLlmTemplates(projectKey),
    queryFn: () => listProjectLlmTemplates(projectKey),
    enabled: Boolean(projectKey),
  })

  const templateItems = useMemo(
    () => (llmTemplates.data?.items || []) as ProjectLlmTemplateItem[],
    [llmTemplates.data?.items],
  )
  const effectiveEnvDraft = envDraft ?? envSettings.data ?? {}

  const envSaveMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, string> = {}
      for (const [key, value] of Object.entries(effectiveEnvDraft)) {
        if (String(value || '').trim()) payload[key] = String(value).trim()
      }
      return updateEnvSettings(payload)
    },
    onSuccess: async () => {
      setSaveMessage(t('settingsPage.message.envUpdated'))
      setEnvDraft(null)
      removeLocal(draftStorageKey)
      await queryClient.invalidateQueries({ queryKey: queryKeys.settings.env() })
      await queryClient.invalidateQueries({ queryKey: queryKeys.config.envStatus() })
    },
    onError: (error) => {
      setSaveMessage(formatSettingsTemplate(t('settingsPage.message.envUpdateFailed'), { error: formatActionError(locale, error) }))
    },
  })

  const templateSaveMutation = useMutation({
    mutationFn: async ({ serviceName, draft }: { serviceName: string; draft: ProjectLlmTemplateDraft }) => {
      const payload: LlmTemplateUpdatePayload = {
        model: toNullableText(draft.model),
        temperature: toNullableNumber(draft.temperature),
        top_p: toNullableNumber(draft.top_p),
        presence_penalty: toNullableNumber(draft.presence_penalty),
        frequency_penalty: toNullableNumber(draft.frequency_penalty),
        max_tokens: toNullableInt(draft.max_tokens),
        enabled: draft.enabled,
        system_prompt: toNullableText(draft.system_prompt),
        user_prompt_template: toNullableText(draft.user_prompt_template),
      }
      return updateProjectLlmTemplate(serviceName, payload, projectKey)
    },
    onMutate: ({ serviceName }) => {
      setSavingService(serviceName)
      setTemplateMessage('')
    },
    onSuccess: async (_data, variables) => {
      setTemplateMessage(formatSettingsTemplate(t('settingsPage.message.templateSaved'), { serviceName: variables.serviceName }))
      await queryClient.invalidateQueries({ queryKey: queryKeys.settings.projectLlmTemplates(projectKey) })
    },
    onError: (error) => {
      setTemplateMessage(formatSettingsTemplate(t('settingsPage.message.templateSaveFailed'), { error: formatActionError(locale, error) }))
    },
    onSettled: () => {
      setSavingService(null)
    },
  })

  const copyTemplatesMutation = useMutation({
    mutationFn: async () => {
      return copyProjectLlmTemplates(
        {
          source_project_key: copySourceProjectKey.trim(),
          overwrite: copyOverwrite,
        },
        projectKey,
      )
    },
    onMutate: () => {
      setCopyMessage('')
    },
    onSuccess: async (data) => {
      setCopyMessage(formatSettingsTemplate(t('settingsPage.message.copyDone'), {
        copied: data.copied ?? 0,
        skipped: data.skipped ?? 0,
      }))
      await queryClient.invalidateQueries({ queryKey: queryKeys.settings.projectLlmTemplates(projectKey) })
    },
    onError: (error) => {
      setCopyMessage(formatSettingsTemplate(t('settingsPage.message.copyFailed'), { error: formatActionError(locale, error) }))
    },
  })

  const hasAnyEnvValue = Object.values(effectiveEnvDraft).some((value) => String(value || '').trim().length > 0)
  const envSnippet = useMemo(() => {
    return guideType ? translate(locale, GUIDE_SNIPPET_KEYS[guideType]) : ''
  }, [guideType, locale])

  useEffect(() => {
    const cached = getLocalJson<SettingsDraftCache | null>(draftStorageKey, null)
    if (!cached) return
    const timerId = window.setTimeout(() => {
      setEnvDraft(cached.envDraft ?? null)
      setTemplateDrafts(cached.templateDrafts || {})
      setCopySourceProjectKey(cached.copySourceProjectKey || '')
      setCopyOverwrite(Boolean(cached.copyOverwrite))
      setExpandedService(cached.expandedService || null)
    }, 0)
    return () => {
      window.clearTimeout(timerId)
    }
  }, [draftStorageKey])

  useEffect(() => {
    setLocalJson<SettingsDraftCache>(draftStorageKey, {
      envDraft,
      templateDrafts,
      copySourceProjectKey,
      copyOverwrite,
      expandedService,
    })
  }, [draftStorageKey, envDraft, templateDrafts, copySourceProjectKey, copyOverwrite, expandedService])

  useEffect(() => {
    const intent = getLocalJson<StatusNavIntent | null>(STATUS_NAV_INTENT_KEY, null)
    if (!intent) return
    const expectedMode: StatusIntentMode = variant === 'llm' ? 'sysLlm' : 'sysSettings'
    if (intent.mode !== expectedMode) return
    removeLocal(STATUS_NAV_INTENT_KEY)
    const nextField = String(intent.focusField || '').trim()
    const stateTimerId = window.setTimeout(() => {
      setGuideType(intent.guide || null)
      setFocusField(nextField)
      if (!nextField) return
      window.setTimeout(() => {
        const fieldContainer = Array.from(document.querySelectorAll<HTMLElement>('[data-env-key]'))
          .find((node) => node.dataset.envKey === nextField)
        const target = fieldContainer?.querySelector<HTMLElement>('input')
        if (!target) return
        target.scrollIntoView({ behavior: 'smooth', block: 'center' })
        target.focus()
      }, 80)
    }, 0)
    return () => {
      window.clearTimeout(stateTimerId)
    }
  }, [variant, envSettings.data])

  const themeLabelByValue: Record<AppTheme, string> = {
    light: translate(locale, 'settings.theme.light'),
    dark: translate(locale, 'settings.theme.dark'),
    brand: translate(locale, 'settings.theme.brand'),
  }
  const localeLabelByValue = {
    'zh-CN': translate(locale, 'settings.locale.zh-CN'),
    'en-US': translate(locale, 'settings.locale.en-US'),
  } as const

  return (
    <SettingsPageView
      projectKey={projectKey}
      variant={variant}
      locale={locale}
      appTheme={appTheme}
      themeLabelByValue={themeLabelByValue}
      localeLabelByValue={localeLabelByValue}
      effectiveEnvDraft={effectiveEnvDraft}
      templateItems={templateItems}
      envSettingsFetching={envSettings.isFetching}
      envSettingsError={envSettings.isError}
      llmTemplatesFetching={llmTemplates.isFetching}
      llmTemplatesError={llmTemplates.isError}
      envSavePending={envSaveMutation.isPending}
      templateSavePending={templateSaveMutation.isPending}
      copyTemplatesPending={copyTemplatesMutation.isPending}
      hasAnyEnvValue={hasAnyEnvValue}
      saveMessage={saveMessage}
      templateMessage={templateMessage}
      copyMessage={copyMessage}
      copySourceProjectKey={copySourceProjectKey}
      copyOverwrite={copyOverwrite}
      expandedService={expandedService}
      savingService={savingService}
      guideType={guideType}
      focusField={focusField}
      envSnippet={envSnippet}
      templateDrafts={templateDrafts}
      onLocaleChange={setAppLocale}
      onThemeChange={setAppTheme}
      onRefreshEnv={() => {
        setEnvDraft(null)
        void queryClient.invalidateQueries({ queryKey: queryKeys.settings.env() })
      }}
      onCopySnippet={() => {
        void (async () => {
          try {
            await navigator.clipboard.writeText(envSnippet)
            setSaveMessage(t('settingsPage.message.exampleCopied'))
          } catch {
            setSaveMessage(t('settingsPage.message.exampleCopyFailed'))
          }
        })()
      }}
      onDismissGuide={() => setGuideType(null)}
      onNavigateCrawler={() => {
        window.location.hash = hashByMode.sysCrawler
      }}
      onEnvDraftChange={(key, value) =>
        setEnvDraft((prev) => ({
          ...(prev ?? envSettings.data ?? {}),
          [key]: value,
        }))
      }
      onSaveEnv={() => envSaveMutation.mutate()}
      onRefreshTemplates={() => {
        void queryClient.invalidateQueries({ queryKey: queryKeys.settings.projectLlmTemplates(projectKey) })
      }}
      onCopySourceProjectKeyChange={setCopySourceProjectKey}
      onCopyOverwriteChange={setCopyOverwrite}
      onCopyTemplates={() => copyTemplatesMutation.mutate()}
      onExpandedServiceChange={setExpandedService}
      onTemplateDraftChange={(serviceName, patch) =>
        setTemplateDrafts((prev) => ({
          ...prev,
          [serviceName]: { ...(prev[serviceName] || toDraft(templateItems.find((item) => item.service_name === serviceName) || {
            service_name: serviceName,
            model: '',
            temperature: null,
            max_tokens: null,
            enabled: false,
          } as ProjectLlmTemplateItem)), ...patch },
        }))
      }
      onSaveTemplate={(serviceName, draft) => templateSaveMutation.mutate({ serviceName, draft })}
    />
  )
}

export function SettingsPageView({
  variant,
  locale,
  appTheme,
  themeLabelByValue,
  localeLabelByValue,
  effectiveEnvDraft,
  templateItems,
  envSettingsFetching,
  envSettingsError,
  llmTemplatesFetching,
  llmTemplatesError,
  envSavePending,
  copyTemplatesPending,
  hasAnyEnvValue,
  saveMessage,
  templateMessage,
  copyMessage,
  copySourceProjectKey,
  copyOverwrite,
  expandedService,
  savingService,
  guideType,
  focusField,
  envSnippet,
  templateDrafts,
  onLocaleChange,
  onThemeChange,
  onRefreshEnv,
  onCopySnippet,
  onDismissGuide,
  onNavigateCrawler,
  onEnvDraftChange,
  onSaveEnv,
  onRefreshTemplates,
  onCopySourceProjectKeyChange,
  onCopyOverwriteChange,
  onCopyTemplates,
  onExpandedServiceChange,
  onTemplateDraftChange,
  onSaveTemplate,
}: SettingsPageViewProps) {
  const t = (key: MessageKey) => translate(locale, key)
  const formatTemplate = (key: MessageKey, values: Record<string, string | number>) =>
    formatSettingsTemplate(t(key), values)
  const pageTitle = variant === 'llm' ? t('settingsPage.title.llmView') : t('settingsPage.title.settingsView')
  const guideMessage = guideType ? t(GUIDE_MESSAGE_KEYS[guideType]) : ''

  return (
    <div className={`content-stack settings-page settings-page--${variant}`}>
      <section className="panel">
        <div className="panel-header">
          <h2>{pageTitle}</h2>
        </div>
        <div className="inline-actions" style={{ marginTop: 10, flexWrap: 'wrap' }}>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span>{t('settings.locale.label')}</span>
            <select value={locale} onChange={(event) => onLocaleChange(event.target.value as (typeof APP_LOCALES)[number])}>
              {APP_LOCALES.map((nextLocale) => (
                <option key={nextLocale} value={nextLocale}>
                  {localeLabelByValue[nextLocale]}
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span>{t('settings.theme.label')}</span>
            <select
              value={appTheme}
              onChange={(event) => {
                const next = event.target.value
                if (!isAppTheme(next)) return
                onThemeChange(next)
              }}
            >
              {APP_THEMES.map((theme) => (
                <option key={theme} value={theme}>
                  {themeLabelByValue[theme]}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>
      <section className="panel">
        <div className="panel-header">
          <h2>
            <Settings2 size={15} />
            {t('settingsPage.section.envConfig')}
          </h2>
          <div className="inline-actions">
            <button onClick={onRefreshEnv} disabled={envSettingsFetching}>
              <RefreshCw size={14} />
              {envSettingsFetching ? t('settingsPage.action.refreshing') : t('settingsPage.action.refresh')}
            </button>
          </div>
        </div>
        {guideType ? (
          <div className="app-settings-guide">
            <strong>{t('settingsPage.guide.title')}</strong>
            <p className="status-line">
              {guideMessage}
            </p>
            {focusField ? <p className="status-line">{formatTemplate('settingsPage.guide.focusField', { field: focusField })}</p> : null}
            <div className="inline-actions" style={{ flexWrap: 'wrap' }}>
              {envSnippet ? <button onClick={onCopySnippet}>{t('settingsPage.action.copyExampleConfig')}</button> : null}
              {guideType === 'search' || guideType === 'news' ? <button onClick={onNavigateCrawler}>{t('settingsPage.action.goToCrawlerManage')}</button> : null}
              <button onClick={onDismissGuide}>{t('settingsPage.action.closeGuide')}</button>
            </div>
          </div>
        ) : null}

        <div className="form-grid cols-2">
          {ENV_KEYS.map((key) => (
            <label key={key} data-env-key={key}>
              <span>{key}</span>
              <input value={effectiveEnvDraft[key] || ''} onChange={(e) => onEnvDraftChange(key, e.target.value)} placeholder={formatTemplate('settingsPage.placeholder.envKey', { key })} />
            </label>
          ))}
        </div>

        <div className="inline-actions">
          <button disabled={envSavePending || !hasAnyEnvValue} onClick={onSaveEnv}>
            <Settings2 size={14} />
            {envSavePending ? t('settingsPage.action.saving') : t('settingsPage.action.saveEnv')}
          </button>
        </div>

        {saveMessage ? <p className="status-line">{saveMessage}</p> : null}
        {envSettingsError ? <p className="status-line">{t('settingsPage.error.envLoadFailed')}</p> : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{t('settingsPage.section.projectLlmTemplates')}</h2>
          <div className="inline-actions">
            <button onClick={onRefreshTemplates} disabled={llmTemplatesFetching}>
              <RefreshCw size={14} />
              {llmTemplatesFetching ? t('settingsPage.action.refreshing') : t('settingsPage.action.refresh')}
            </button>
          </div>
        </div>

        <div className="inline-actions" style={{ marginBottom: 12, flexWrap: 'wrap' }}>
          <input value={copySourceProjectKey} onChange={(e) => onCopySourceProjectKeyChange(e.target.value)} placeholder={t('settingsPage.placeholder.sourceProjectKey')} style={{ minWidth: 220 }} />
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={copyOverwrite} onChange={(e) => onCopyOverwriteChange(e.target.checked)} />
            <span>{t('settingsPage.field.copyOverwrite')}</span>
          </label>
          <button disabled={copyTemplatesPending || !copySourceProjectKey.trim()} onClick={onCopyTemplates}>
            {copyTemplatesPending ? t('settingsPage.action.copying') : t('settingsPage.action.copyFromProject')}
          </button>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('settingsPage.field.service')}</th>
                <th>{t('settingsPage.field.model')}</th>
                <th>{t('settingsPage.field.temperature')}</th>
                <th>{t('settingsPage.field.topP')}</th>
                <th>{t('settingsPage.field.maxTokens')}</th>
                <th>{t('settingsPage.field.enabled')}</th>
                <th>{t('settingsPage.field.updated')}</th>
                <th>{t('settingsPage.field.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {templateItems.map((row) => {
                const draft = templateDrafts[row.service_name] || toDraft(row)
                const isExpanded = expandedService === row.service_name
                const isSaving = savingService === row.service_name
                return (
                  <>
                    <tr key={row.id}>
                      <td>{row.service_name}</td>
                      <td>{draft.model || '-'}</td>
                      <td>{draft.temperature || '-'}</td>
                      <td>{draft.top_p || '-'}</td>
                      <td>{draft.max_tokens || '-'}</td>
                      <td>{draft.enabled ? t('settingsPage.value.enabledTrue') : t('settingsPage.value.enabledFalse')}</td>
                      <td>{formatDate(row.updated_at, locale)}</td>
                      <td>
                        <button onClick={() => onExpandedServiceChange(isExpanded ? null : row.service_name)}>
                          {isExpanded ? t('settingsPage.action.collapse') : t('settingsPage.action.edit')}
                        </button>
                      </td>
                    </tr>
                    {isExpanded ? (
                      <tr key={`${row.id}-editor`}>
                        <td colSpan={8}>
                          <div className="form-grid cols-2" style={{ marginTop: 8 }}>
                            <label>
                              <span>{t('settingsPage.field.model')}</span>
                              <input value={draft.model} onChange={(e) => onTemplateDraftChange(row.service_name, { model: e.target.value })} />
                            </label>
                            <label>
                              <span>{t('settingsPage.field.temperature')}</span>
                              <input value={draft.temperature} onChange={(e) => onTemplateDraftChange(row.service_name, { temperature: e.target.value })} />
                            </label>
                            <label>
                              <span>{t('settingsPage.field.topP')}</span>
                              <input value={draft.top_p} onChange={(e) => onTemplateDraftChange(row.service_name, { top_p: e.target.value })} />
                            </label>
                            <label>
                              <span>{t('settingsPage.field.presencePenalty')}</span>
                              <input value={draft.presence_penalty} onChange={(e) => onTemplateDraftChange(row.service_name, { presence_penalty: e.target.value })} />
                            </label>
                            <label>
                              <span>{t('settingsPage.field.frequencyPenalty')}</span>
                              <input value={draft.frequency_penalty} onChange={(e) => onTemplateDraftChange(row.service_name, { frequency_penalty: e.target.value })} />
                            </label>
                            <label>
                              <span>{t('settingsPage.field.maxTokens')}</span>
                              <input value={draft.max_tokens} onChange={(e) => onTemplateDraftChange(row.service_name, { max_tokens: e.target.value })} />
                            </label>
                            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                              <input type="checkbox" checked={draft.enabled} onChange={(e) => onTemplateDraftChange(row.service_name, { enabled: e.target.checked })} />
                              <span>{t('settingsPage.field.enabled')}</span>
                            </label>
                          </div>
                          <div className="form-grid" style={{ marginTop: 8 }}>
                            <label>
                              <span>{t('settingsPage.field.systemPrompt')}</span>
                              <textarea value={draft.system_prompt} onChange={(e) => onTemplateDraftChange(row.service_name, { system_prompt: e.target.value })} rows={5} />
                            </label>
                            <label>
                              <span>{t('settingsPage.field.userPromptTemplate')}</span>
                              <textarea value={draft.user_prompt_template} onChange={(e) => onTemplateDraftChange(row.service_name, { user_prompt_template: e.target.value })} rows={5} />
                            </label>
                          </div>
                          <div className="inline-actions" style={{ marginTop: 8 }}>
                            <button disabled={isSaving} onClick={() => onSaveTemplate(row.service_name, draft)}>
                              {isSaving ? t('settingsPage.action.saving') : formatTemplate('settingsPage.action.saveServiceTemplate', { serviceName: row.service_name })}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </>
                )
              })}
              {!templateItems.length ? (
                <tr>
                  <td colSpan={8} className="empty-cell">
                    {t('settingsPage.empty.projectLlmTemplates')}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        {templateMessage ? <p className="status-line">{templateMessage}</p> : null}
        {copyMessage ? <p className="status-line">{copyMessage}</p> : null}
        {llmTemplatesError ? <p className="status-line">{t('settingsPage.error.templatesLoadFailed')}</p> : null}
      </section>
    </div>
  )
}

export default SettingsPage
