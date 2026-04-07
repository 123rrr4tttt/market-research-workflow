import './concept-lab.css'

const links = [
  {
    href: '#concept-quiet.html',
    title: 'Layer A / Workbench',
    subtitle: 'Editorial / quiet / writing-first',
    note: '写作与工作台层',
  },
  {
    href: '#concept-orbital.html',
    title: 'Layer B / Visualization',
    subtitle: 'Analytical / spatial / signal-first',
    note: '可视化与分析层',
  },
  {
    href: '#concept-monolith.html',
    title: 'Layer C / Management',
    subtitle: 'Operational / hard-edge / governance shell',
    note: '管理与治理层',
  },
]

export default function ConceptLabIndexPage() {
  return (
    <main className="concept-index">
      <header className="concept-index__hero">
        <p>Concept Lab</p>
        <h1>Two interaction surfaces, three visual layers</h1>
        <span>按 current-dev 拓扑保留双交互面，在其上叠加 A/B/C 三层视觉语义。</span>
      </header>
      <section className="concept-index__grid">
        {links.map((link) => (
          <a key={link.href} href={link.href} className="concept-index__tile">
            <strong>{link.title}</strong>
            <em>{link.subtitle}</em>
            <span>{link.note}</span>
          </a>
        ))}
      </section>
    </main>
  )
}
