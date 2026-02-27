type Props = {
  title: string
}

export default function GraphToolbar({ title }: Props) {
  return (
    <section className="gk-panel">
      <div className="gk-toolbar">
        <h2>{title}</h2>
        <div className="gk-toolbar-actions">
          <button>刷新</button>
          <button>筛选</button>
          <button>导出</button>
        </div>
      </div>
    </section>
  )
}
