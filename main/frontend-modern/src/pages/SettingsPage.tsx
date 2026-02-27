import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Settings2 } from 'lucide-react'
import { getEnvSettings, listLlmConfigs, updateEnvSettings } from '../lib/api'
import type { EnvSettings } from '../lib/types'

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

export function SettingsPage({ projectKey, variant = 'settings' }: SettingsPageProps) {
  const queryClient = useQueryClient()
  const [envDraft, setEnvDraft] = useState<EnvSettings>({})
  const [saveMessage, setSaveMessage] = useState('')

  const envSettings = useQuery({
    queryKey: ['env-settings'],
    queryFn: getEnvSettings,
    enabled: Boolean(projectKey),
  })

  const llmConfigs = useQuery({
    queryKey: ['llm-configs', projectKey],
    queryFn: listLlmConfigs,
    enabled: Boolean(projectKey),
  })

  useEffect(() => {
    if (envSettings.data) setEnvDraft(envSettings.data)
  }, [envSettings.data])

  const envSaveMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, string> = {}
      for (const [key, value] of Object.entries(envDraft)) {
        if (String(value || '').trim()) payload[key] = String(value).trim()
      }
      return updateEnvSettings(payload)
    },
    onSuccess: async () => {
      setSaveMessage('环境配置已更新')
      await queryClient.invalidateQueries({ queryKey: ['env-settings'] })
    },
    onError: (error) => {
      setSaveMessage(`环境配置更新失败: ${error instanceof Error ? error.message : '未知错误'}`)
    },
  })

  const hasAnyEnvValue = useMemo(
    () => Object.values(envDraft).some((value) => String(value || '').trim().length > 0),
    [envDraft],
  )

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
            <button onClick={() => queryClient.invalidateQueries({ queryKey: ['env-settings'] })} disabled={envSettings.isFetching}>
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
                value={envDraft[key] || ''}
                onChange={(e) => setEnvDraft((prev) => ({ ...prev, [key]: e.target.value }))}
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
          <h2>LLM 服务配置</h2>
          <div className="inline-actions">
            <button
              onClick={() => queryClient.invalidateQueries({ queryKey: ['llm-configs', projectKey] })}
              disabled={llmConfigs.isFetching}
            >
              <RefreshCw size={14} />
              {llmConfigs.isFetching ? '刷新中...' : '刷新'}
            </button>
          </div>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>service</th>
                <th>model</th>
                <th>temperature</th>
                <th>max_tokens</th>
                <th>enabled</th>
                <th>updated</th>
              </tr>
            </thead>
            <tbody>
              {(llmConfigs.data || []).map((row) => (
                <tr key={row.id}>
                  <td>{row.service_name}</td>
                  <td>{row.model || '-'}</td>
                  <td>{row.temperature ?? '-'}</td>
                  <td>{row.max_tokens ?? '-'}</td>
                  <td>{String(row.enabled)}</td>
                  <td>{formatDate(row.updated_at)}</td>
                </tr>
              ))}
              {!llmConfigs.data?.length ? (
                <tr>
                  <td colSpan={6} className="empty-cell">
                    暂无 LLM 配置
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        {llmConfigs.isError ? <p className="status-line">LLM 配置加载失败，请稍后重试</p> : null}
      </section>
    </div>
  )
}

export default SettingsPage
