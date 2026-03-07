import type { WritingTemplate, WritingTemplateValidation } from '../../lib/api'

export type TemplateLibraryPanelProps = {
  templates: WritingTemplate[]
  activeTemplateKey?: string | null
  validation?: WritingTemplateValidation | null
  validating?: boolean
  onApplyTemplate?: (templateKey: string) => void
  onValidateTemplate?: (templateKey: string) => void
}

export default function TemplateLibraryPanel({
  templates,
  activeTemplateKey,
  validation,
  validating = false,
  onApplyTemplate,
  onValidateTemplate,
}: TemplateLibraryPanelProps) {
  return (
    <section className="panel writing-side-panel">
      <div className="panel-header">
        <div>
          <h2>报告模板</h2>
          <p className="text-muted writing-panel-subtitle">优先套用成熟模板，不在页面里手搓报告结构。</p>
        </div>
        {validating ? <span className="chip chip-warn">checking</span> : null}
      </div>

      <div className="writing-list">
        {templates.map((template) => (
          <article
            key={template.template_key}
            className={`writing-list-card is-static${activeTemplateKey === template.template_key ? ' is-active' : ''}`}
          >
            <div className="writing-list-card__header">
              <strong>{template.label}</strong>
              <span className="chip">{template.template_key}</span>
            </div>
            <p>{template.description || '内置模板'}</p>
            <div className="writing-list-card__footer">
              <button type="button" className="button-secondary" onClick={() => onValidateTemplate?.(template.template_key)}>
                校验
              </button>
              <button type="button" className="button-primary" onClick={() => onApplyTemplate?.(template.template_key)}>
                套用
              </button>
            </div>
          </article>
        ))}
        {!templates.length ? <div className="empty-cell">暂无模板</div> : null}
      </div>

      {validation ? (
        <div className="writing-validation">
          <span className={validation.valid ? 'chip chip-ok' : 'chip chip-danger'}>{validation.valid ? 'valid' : 'invalid'}</span>
          {validation.errors.length ? <p className="status-line">{validation.errors.join(', ')}</p> : null}
          {validation.warnings.length ? <p className="text-muted">{validation.warnings.join(', ')}</p> : null}
        </div>
      ) : null}
    </section>
  )
}
