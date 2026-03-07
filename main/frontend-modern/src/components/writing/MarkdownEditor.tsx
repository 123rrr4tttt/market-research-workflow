import { useRef } from 'react'

export type MarkdownEditorProps = {
  value: string
  placeholder?: string
  autosaveLabel?: string
  onChange: (value: string) => void
  onSelectionChange?: (selectionText: string) => void
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
    const nextSelection = textareaRef.current?.value.slice(
      textareaRef.current.selectionStart,
      textareaRef.current.selectionEnd,
    )
    onSelectionChange?.(String(nextSelection || '').trim())
  }

  return (
    <section className="writing-editor">
      <div className="writing-editor__toolbar">
        <span className="chip chip-ok">{value.length} chars</span>
        {autosaveLabel ? <span className="text-muted">{autosaveLabel}</span> : null}
      </div>
      <textarea
        ref={textareaRef}
        className="writing-editor__textarea"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        onSelect={emitSelection}
        onKeyUp={emitSelection}
      />
    </section>
  )
}
