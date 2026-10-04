import { useCallback, useEffect, useMemo, useState } from 'react'
import { informationTopologyClient } from '../../features/information-topology'
import type { TopologyReadResult, TopologyRef } from '../../features/information-topology/types'
import { isApiClientError } from '../../lib/api/client'
import { TopologyDetail } from '../../features/information-topology/TopologyDetail'
import './GraphTopologyPanel.css'

type Props = {
  graphIdentity: string
}

function apiErrorCode(reason: unknown) {
  if (isApiClientError(reason)) return reason.code
  if (!reason || typeof reason !== 'object') return ''
  const response = (reason as { response?: { data?: { detail?: { error?: { code?: unknown } } } } }).response
  return String(response?.data?.detail?.error?.code || '')
}

export function GraphTopologyPanel({ graphIdentity }: Props) {
  const [saved, setSaved] = useState<TopologyReadResult | null>(null)
  const [status, setStatus] = useState('正在读取图谱结构…')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const target = useMemo<TopologyRef>(() => ({ module_id: 'graph_view', namespace: 'view', state_id: `graphPage:${graphIdentity}` }), [graphIdentity])

  const readSaved = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await informationTopologyClient.readTopology(target)
      setSaved(result)
      setStatus(`已读回版本 ${result.revision}`)
    } catch (reason) {
      setSaved(null)
      if (apiErrorCode(reason) === 'NOT_FOUND') {
        setStatus('尚无已保存的抽象图谱结构')
        return
      }
      const message = reason instanceof Error ? reason.message : String(reason)
      setError(message)
      setStatus('读取失败')
    } finally {
      setBusy(false)
    }
  }, [target])

  useEffect(() => {
    let active = true
    void informationTopologyClient.readTopology(target).then((result) => {
      if (!active) return
      setError(null)
      setSaved(result)
      setStatus(`已读回版本 ${result.revision}`)
    }).catch((reason: unknown) => {
      if (!active) return
      setSaved(null)
      if (apiErrorCode(reason) === 'NOT_FOUND') {
        setStatus('尚无已保存的抽象图谱结构')
        return
      }
      const message = reason instanceof Error ? reason.message : String(reason)
      setError(message)
      setStatus('读取失败')
    })
    return () => { active = false }
  }, [target])

  return <section className="panel graph-topology-panel" aria-label="抽象图谱结构" data-testid="graph-topology-panel">
    <div className="graph-topology-panel__head">
      <div>
        <h2>抽象图谱结构</h2>
        <p>只读展示已保存的成员、关系、来源引用与观察版本；页面坐标和布局不属于拓扑。</p>
      </div>
      <div className="graph-topology-panel__actions">
        <button type="button" className="secondary" onClick={() => void readSaved()} disabled={busy}>
          {busy ? '读取中…' : '重新读取'}
        </button>
      </div>
    </div>
    <p role="status" data-testid="graph-topology-status">{status}</p>
    {error ? <p role="alert" data-testid="graph-topology-error">{error}</p> : null}
    {saved ? <>
      <p>Profile：{saved.topology.profile_id} · {saved.topology.profile_version} · 修订 {saved.revision}</p>
      <TopologyDetail value={saved.topology} title="成员、关系与来源" />
    </> : null}
  </section>
}
