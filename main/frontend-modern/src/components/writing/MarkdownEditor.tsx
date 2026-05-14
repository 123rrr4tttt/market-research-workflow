import { useRef } from 'react'

export type MarkdownSelectionState = {
  text: string
  start: number
  end: number
  line: number
  before: string
  after: string
}

export type MarkdownEditorProps = {
  value: string
  placeholder?: string
  autosaveLabel?: string
  onChange: (value: string) => void
  onSelectionChange?: (selectionText: string, selection: MarkdownSelectionState) => void
}

export default function MarkdownEditor({
  value,
  placeholder = 'Write markdown...',
  autosaveLabel,
  onChange,
  onSelectionChange,
}: MarkdownEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  const emitSelection = () => {
    const textarea = textareaRef.current
    if (!textarea) return
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const rawSelection = textarea.value.slice(start, end)
    const before = textarea.value.slice(Math.max(0, start - 600), start)
    const after = textarea.value.slice(end, Math.min(textarea.value.length, end + 600))
    const line = textarea.value.slice(0, start).split('\n').length
    onSelectionChange?.(String(rawSelection || '').trim(), {
      text: String(rawSelection || '').trim(),
      start,
      end,
      line,
      before,
      after,
    })
  }

  return (
    <section className="writing-editor" data-testid="writing-markdown-editor-shell">
      <div className="writing-editor__toolbar" data-testid="writing-markdown-editor-toolbar">
        <span className="chip chip-ok">{value.length} chars</span>
        {autosaveLabel ? <span className="text-muted">{autosaveLabel}</span> : null}
      </div>
      <textarea
        ref={textareaRef}
        className="writing-editor__textarea"
        data-testid="writing-markdown-editor"
        aria-label="writing markdown editor"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        onSelect={emitSelection}
        onKeyUp={emitSelection}
      />
    </section>
  )
}
