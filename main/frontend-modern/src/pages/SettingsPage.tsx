import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Settings2 } from 'lucide-react'
import {
  copyProjectLlmTemplates,
  getEnvSettings,
  listProjectLlmTemplates,
  updateEnvSettings,
  updateProjectLlmTemplate,
} from '../lib/api'
import type { EnvSettings, LlmServiceConfigItem, LlmTemplateUpdatePayload } from '../lib/types'

export type SettingsPageProps = {
  projectKey: string
  variant?: 'settings' | 'llm'
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
  'GOOGLE_SEARCH_API_KEY',
  'GOOGLE_SEARCH_CSE_ID',
  'AZURE_SEARCH_ENDPOINT',
  'AZURE_SEARCH_KEY',
] as const

function formatDate(value?: string | null) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString('zh-CN')
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

export function SettingsPage({ projectKey, variant = 'settings' }: SettingsPageProps) {
  const queryClient = useQueryClient()
  const [envDraft, setEnvDraft] = useState<EnvSettings | null>(null)
  const [saveMessage, setSaveMessage] = useState('')
  const [templateDrafts, setTemplateDrafts] = useState<Record<string, ProjectLlmTemplateDraft>>({})
  const [templateMessage, setTemplateMessage] = useState('')
  const [copySourceProjectKey, setCopySourceProjectKey] = useState('')
  const [copyOverwrite, setCopyOverwrite] = useState(false)
  const [copyMessage, setCopyMessage] = useState('')
  const [expandedService, setExpandedService] = useState<string | null>(null)
  const [savingService, setSavingService] = useState<string | null>(null)

  const envSettings = useQuery({
    queryKey: ['env-settings'],
    queryFn: getEnvSettings,
    enabled: Boolean(projectKey),
  })

  const llmTemplates = useQuery({
    queryKey: ['project-llm-templates', projectKey],
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
      setSaveMessage('环境配置已更新')
      setEnvDraft(null)
      await queryClient.invalidateQueries({ queryKey: ['env-settings'] })
    },
    onError: (error) => {
      setSaveMessage(`环境配置更新失败: ${error instanceof Error ? error.message : '未知错误'}`)
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
      setTemplateMessage(`模板已保存：${variables.serviceName}`)
      await queryClient.invalidateQueries({ queryKey: ['project-llm-templates', projectKey] })
    },
    onError: (error) => {
      setTemplateMessage(`模板保存失败：${error instanceof Error ? error.message : '未知错误'}`)
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
      setCopyMessage(`复制完成：copied=${data.copied ?? 0}, skipped=${data.skipped ?? 0}`)
      await queryClient.invalidateQueries({ queryKey: ['project-llm-templates', projectKey] })
    },
    onError: (error) => {
      setCopyMessage(`复制失败：${error instanceof Error ? error.message : '未知错误'}`)
    },
  })

  const hasAnyEnvValue = Object.values(effectiveEnvDraft).some((value) => String(value || '').trim().length > 0)

  return (
    <div className="content-stack">
      <section className="panel">
        <div className="panel-header">
          <h2>{variant === 'llm' ? 'LLM 配置视图' : '系统设置视图'}</h2>
        </div>
      </section>
      <section className="panel">
        <div className="panel-header">
          <h2>
            <Settings2 size={15} />
            环境配置
          </h2>
          <div className="inline-actions">
            <button
              onClick={() => {
                setEnvDraft(null)
                queryClient.invalidateQueries({ queryKey: ['env-settings'] })
              }}
              disabled={envSettings.isFetching}
            >
              <RefreshCw size={14} />
              {envSettings.isFetching ? '刷新中...' : '刷新'}
            </button>
          </div>
        </div>

        <div className="form-grid cols-2">
          {ENV_KEYS.map((key) => (
            <label key={key}>
              <span>{key}</span>
              <input
                value={effectiveEnvDraft[key] || ''}
                onChange={(e) =>
                  setEnvDraft((prev) => ({
                    ...(prev ?? envSettings.data ?? {}),
                    [key]: e.target.value,
                  }))
                }
                placeholder={`输入 ${key}`}
              />
            </label>
          ))}
        </div>

        <div className="inline-actions">
          <button disabled={envSaveMutation.isPending || !hasAnyEnvValue} onClick={() => envSaveMutation.mutate()}>
            <Settings2 size={14} />
            {envSaveMutation.isPending ? '保存中...' : '保存配置'}
          </button>
        </div>

        {saveMessage ? <p className="status-line">{saveMessage}</p> : null}
        {envSettings.isError ? <p className="status-line">环境配置加载失败，请稍后重试</p> : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>项目级 LLM 模板</h2>
          <div className="inline-actions">
            <button
              onClick={() => queryClient.invalidateQueries({ queryKey: ['project-llm-templates', projectKey] })}
              disabled={llmTemplates.isFetching}
            >
              <RefreshCw size={14} />
              {llmTemplates.isFetching ? '刷新中...' : '刷新'}
            </button>
          </div>
        </div>

        <div className="inline-actions" style={{ marginBottom: 12, flexWrap: 'wrap' }}>
          <input
            value={copySourceProjectKey}
            onChange={(e) => setCopySourceProjectKey(e.target.value)}
            placeholder="来源 project_key"
            style={{ minWidth: 220 }}
          />
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={copyOverwrite} onChange={(e) => setCopyOverwrite(e.target.checked)} />
            <span>覆盖已存在模板</span>
          </label>
          <button
            disabled={copyTemplatesMutation.isPending || !copySourceProjectKey.trim()}
            onClick={() => copyTemplatesMutation.mutate()}
          >
            {copyTemplatesMutation.isPending ? '复制中...' : '从项目复制模板'}
          </button>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>service</th>
                <th>model</th>
                <th>temperature</th>
                <th>top_p</th>
                <th>max_tokens</th>
                <th>enabled</th>
                <th>updated</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {templateItems.map((row) => {
                const draft = templateDrafts[row.service_name] || toDraft(row)
                const isExpanded = expandedService === row.service_name
                const isSaving = templateSaveMutation.isPending && savingService === row.service_name
                return (
                  <>
                    <tr key={row.id}>
                      <td>{row.service_name}</td>
                      <td>{draft.model || '-'}</td>
                      <td>{draft.temperature || '-'}</td>
                      <td>{draft.top_p || '-'}</td>
                      <td>{draft.max_tokens || '-'}</td>
                      <td>{String(draft.enabled)}</td>
                      <td>{formatDate(row.updated_at)}</td>
                      <td>
                        <button onClick={() => setExpandedService(isExpanded ? null : row.service_name)}>
                          {isExpanded ? '收起' : '编辑'}
                        </button>
                      </td>
                    </tr>
                    {isExpanded ? (
                      <tr key={`${row.id}-editor`}>
                        <td colSpan={8}>
                          <div className="form-grid cols-2" style={{ marginTop: 8 }}>
                            <label>
                              <span>model</span>
                              <input
                                value={draft.model}
                                onChange={(e) =>
                                  setTemplateDrafts((prev) => ({
                                    ...prev,
                                    [row.service_name]: { ...draft, model: e.target.value },
                                  }))
                                }
                              />
                            </label>
                            <label>
                              <span>temperature</span>
                              <input
                                value={draft.temperature}
                                onChange={(e) =>
                                  setTemplateDrafts((prev) => ({
                                    ...prev,
                                    [row.service_name]: { ...draft, temperature: e.target.value },
                                  }))
                                }
                              />
                            </label>
                            <label>
                              <span>top_p</span>
                              <input
                                value={draft.top_p}
                                onChange={(e) =>
                                  setTemplateDrafts((prev) => ({
                                    ...prev,
                                    [row.service_name]: { ...draft, top_p: e.target.value },
                                  }))
                                }
                              />
                            </label>
                            <label>
                              <span>presence_penalty</span>
                              <input
                                value={draft.presence_penalty}
                                onChange={(e) =>
                                  setTemplateDrafts((prev) => ({
                                    ...prev,
                                    [row.service_name]: { ...draft, presence_penalty: e.target.value },
                                  }))
                                }
                              />
                            </label>
                            <label>
                              <span>frequency_penalty</span>
                              <input
                                value={draft.frequency_penalty}
                                onChange={(e) =>
                                  setTemplateDrafts((prev) => ({
                                    ...prev,
                                    [row.service_name]: { ...draft, frequency_penalty: e.target.value },
                                  }))
                                }
                              />
                            </label>
                            <label>
                              <span>max_tokens</span>
                              <input
                                value={draft.max_tokens}
                                onChange={(e) =>
                                  setTemplateDrafts((prev) => ({
                                    ...prev,
                                    [row.service_name]: { ...draft, max_tokens: e.target.value },
                                  }))
                                }
                              />
                            </label>
                            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                              <input
                                type="checkbox"
                                checked={draft.enabled}
                                onChange={(e) =>
                                  setTemplateDrafts((prev) => ({
                                    ...prev,
                                    [row.service_name]: { ...draft, enabled: e.target.checked },
                                  }))
                                }
                              />
                              <span>enabled</span>
                            </label>
                          </div>
                          <div className="form-grid" style={{ marginTop: 8 }}>
                            <label>
                              <span>system_prompt</span>
                              <textarea
                                value={draft.system_prompt}
                                onChange={(e) =>
                                  setTemplateDrafts((prev) => ({
                                    ...prev,
                                    [row.service_name]: { ...draft, system_prompt: e.target.value },
                                  }))
                                }
                                rows={5}
                              />
                            </label>
                            <label>
                              <span>user_prompt_template</span>
                              <textarea
                                value={draft.user_prompt_template}
                                onChange={(e) =>
                                  setTemplateDrafts((prev) => ({
                                    ...prev,
                                    [row.service_name]: { ...draft, user_prompt_template: e.target.value },
                                  }))
                                }
                                rows={5}
                              />
                            </label>
                          </div>
                          <div className="inline-actions" style={{ marginTop: 8 }}>
                            <button
                              disabled={isSaving}
                              onClick={() => templateSaveMutation.mutate({ serviceName: row.service_name, draft })}
                            >
                              {isSaving ? '保存中...' : `保存 ${row.service_name}`}
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
                    暂无项目级 LLM 模板
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        {templateMessage ? <p className="status-line">{templateMessage}</p> : null}
        {copyMessage ? <p className="status-line">{copyMessage}</p> : null}
        {llmTemplates.isError ? <p className="status-line">项目级 LLM 模板加载失败，请稍后重试</p> : null}
      </section>
    </div>
  )
}

export default SettingsPage
