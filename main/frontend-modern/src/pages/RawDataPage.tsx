import { useMemo, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { UploadCloud } from 'lucide-react'
import { rawImportDocuments } from '../lib/api'
import type { RawImportPayload, RawImportResult } from '../lib/types'

type RawDataPageProps = {
  projectKey: string
  variant?: 'rawData'
}

type DraftItem = {
  title: string
  uri: string
  publishDate: string
  state: string
  text: string
}

const initialDraft: DraftItem = {
  title: '',
  uri: '',
  publishDate: '',
  state: '',
  text: '',
}

export default function RawDataPage({ projectKey }: RawDataPageProps) {
  const [draft, setDraft] = useState<DraftItem>(initialDraft)
  const [sourceName, setSourceName] = useState('raw_import')
  const [sourceKind, setSourceKind] = useState('manual')
  const [docType, setDocType] = useState<RawImportPayload['default_doc_type']>('raw_note')
  const [extractionMode, setExtractionMode] = useState<RawImportPayload['extraction_mode']>('auto')
  const [inferFromLinks, setInferFromLinks] = useState(true)
  const [enableExtraction, setEnableExtraction] = useState(true)
  const [overwriteOnUri, setOverwriteOnUri] = useState(false)
  const [chunkSize, setChunkSize] = useState(2800)
  const [chunkOverlap, setChunkOverlap] = useState(200)
  const [maxChunks, setMaxChunks] = useState(8)
  const [result, setResult] = useState<RawImportResult | null>(null)

  const canSubmit = useMemo(() => draft.text.trim().length > 0, [draft.text])

  const importMutation = useMutation({
    mutationFn: (payload: RawImportPayload) => rawImportDocuments(payload),
    onSuccess: (data) => {
      setResult(data)
      setDraft((prev) => ({ ...prev, text: '' }))
    },
    onError: () => {
      setResult(null)
    },
  })

  const submitImport = () => {
    const payload: RawImportPayload = {
      items: [
        {
          title: draft.title.trim() || undefined,
          uri: draft.uri.trim() || undefined,
          text: draft.text.trim(),
          publish_date: draft.publishDate.trim() || undefined,
          state: draft.state.trim() || undefined,
          doc_type: docType,
        },
      ],
      source_name: sourceName.trim() || 'raw_import',
      source_kind: sourceKind.trim() || 'manual',
      infer_from_links: inferFromLinks,
      enable_extraction: enableExtraction,
      default_doc_type: docType,
      extraction_mode: extractionMode,
      overwrite_on_uri: overwriteOnUri,
      chunk_size: chunkSize,
      chunk_overlap: chunkOverlap,
      max_chunks: maxChunks,
    }
    importMutation.mutate(payload)
  }

  return (
    <div className="content-stack">
      <section className="panel">
        <div className="panel-header">
          <h2>原始数据导入</h2>
        </div>
        <p className="status-line">当前项目：{projectKey}</p>
        <p className="status-line">兼容入口：raw-data-processing.html / raw-data</p>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>导入参数</h2>
        </div>
        <div className="form-grid cols-3">
          <label>
            <span>source_name</span>
            <input value={sourceName} onChange={(e) => setSourceName(e.target.value)} placeholder="raw_import" />
          </label>
          <label>
            <span>source_kind</span>
            <input value={sourceKind} onChange={(e) => setSourceKind(e.target.value)} placeholder="manual" />
          </label>
          <label>
            <span>default_doc_type</span>
            <select value={docType} onChange={(e) => setDocType(e.target.value as RawImportPayload['default_doc_type'])}>
              <option value="raw_note">raw_note</option>
              <option value="news">news</option>
              <option value="market_info">market_info</option>
              <option value="policy">policy</option>
              <option value="social_sentiment">social_sentiment</option>
            </select>
          </label>
          <label>
            <span>extraction_mode</span>
            <select value={extractionMode} onChange={(e) => setExtractionMode(e.target.value as RawImportPayload['extraction_mode'])}>
              <option value="auto">auto</option>
              <option value="market">market</option>
              <option value="policy">policy</option>
              <option value="social">social</option>
            </select>
          </label>
          <label>
            <span>chunk_size</span>
            <input type="number" min={500} max={8000} value={chunkSize} onChange={(e) => setChunkSize(Number(e.target.value) || 2800)} />
          </label>
          <label>
            <span>chunk_overlap</span>
            <input type="number" min={0} max={1000} value={chunkOverlap} onChange={(e) => setChunkOverlap(Number(e.target.value) || 200)} />
          </label>
          <label>
            <span>max_chunks</span>
            <input type="number" min={1} max={50} value={maxChunks} onChange={(e) => setMaxChunks(Number(e.target.value) || 8)} />
          </label>
          <label className="checkbox-label">
            <span>infer_from_links</span>
            <input type="checkbox" checked={inferFromLinks} onChange={(e) => setInferFromLinks(e.target.checked)} />
          </label>
          <label className="checkbox-label">
            <span>enable_extraction</span>
            <input type="checkbox" checked={enableExtraction} onChange={(e) => setEnableExtraction(e.target.checked)} />
          </label>
          <label className="checkbox-label">
            <span>overwrite_on_uri</span>
            <input type="checkbox" checked={overwriteOnUri} onChange={(e) => setOverwriteOnUri(e.target.checked)} />
          </label>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>原始内容</h2>
        </div>
        <div className="form-grid cols-2">
          <label>
            <span>title</span>
            <input value={draft.title} onChange={(e) => setDraft((prev) => ({ ...prev, title: e.target.value }))} placeholder="可选" />
          </label>
          <label>
            <span>uri</span>
            <input value={draft.uri} onChange={(e) => setDraft((prev) => ({ ...prev, uri: e.target.value }))} placeholder="https://example.com/article" />
          </label>
          <label>
            <span>state</span>
            <input value={draft.state} onChange={(e) => setDraft((prev) => ({ ...prev, state: e.target.value }))} placeholder="CA" />
          </label>
          <label>
            <span>publish_date</span>
            <input value={draft.publishDate} onChange={(e) => setDraft((prev) => ({ ...prev, publishDate: e.target.value }))} placeholder="2026-02-27" />
          </label>
          <label>
            <span>text</span>
            <textarea rows={12} value={draft.text} onChange={(e) => setDraft((prev) => ({ ...prev, text: e.target.value }))} placeholder="粘贴原始文本内容" />
          </label>
        </div>
        <div className="inline-actions">
          <button disabled={!canSubmit || importMutation.isPending} onClick={submitImport}>
            <UploadCloud size={14} />
            {importMutation.isPending ? '导入中...' : '提交导入'}
          </button>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>导入结果</h2>
        </div>
        {importMutation.isError ? <p className="status-line">导入失败：{importMutation.error instanceof Error ? importMutation.error.message : '未知错误'}</p> : null}
        {result ? (
          <>
            <p className="status-line">inserted: {result.inserted ?? 0}</p>
            <p className="status-line">updated: {result.updated ?? 0}</p>
            <p className="status-line">skipped: {result.skipped ?? 0}</p>
            <p className="status-line">error_count: {result.error_count ?? 0}</p>
          </>
        ) : (
          <p className="status-line">暂无导入结果</p>
        )}
      </section>
    </div>
  )
}
