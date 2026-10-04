import type { MappingPreview } from './types'

export function MappingStatus({ preview }: { preview: MappingPreview }) {
  return <section className="topology-mapping-status" aria-label="映射状态">
    <h2>映射：{preview.mapping_id}</h2>
    <p>覆盖：{preview.coverage === 'total' ? '完整' : '部分'}</p>
    <p>保真：{preview.fidelity === 'lossless' ? '有见证的无损' : preview.fidelity === 'lossy' ? '有损' : '未验证'}</p>
    {preview.unmapped.length > 0 && <>
      <h3>未映射项目（{preview.unmapped.length}）</h3>
      <ul>{preview.unmapped.map((item, index) => <li key={`${item.ref.module_id}-${item.ref.local_id}-${index}`}>
        {item.ref.module_id}:{item.ref.type_id}/{item.ref.local_id}@{item.observed_revision}
      </li>)}</ul>
    </>}
    {preview.fidelity !== 'lossless' && <p role="status">此映射没有可展示为无损的往返见证。</p>}
  </section>
}

