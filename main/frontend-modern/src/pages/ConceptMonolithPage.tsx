import './concept-lab.css'

export default function ConceptMonolithPage() {
  return (
    <main className="concept-page concept-page--monolith">
      <header className="mono-rail">
        <span>project alpha</span>
        <span>api nominal</span>
        <span>db synced</span>
        <span>assistant armed</span>
      </header>

      <section className="mono-shell">
        <aside className="mono-sidebar">
          <strong>MRW</strong>
          <nav>
            <span>01 overview</span>
            <span>02 ingest</span>
            <span>03 graph</span>
            <span>04 control</span>
          </nav>
        </aside>

        <section className="mono-main">
          <header className="mono-main__header">
            <p>monolith grid / operating surface</p>
            <h1>Quiet power, hard edges, zero decorative fluff.</h1>
          </header>

          <section className="mono-metrics">
            <article>
              <span>docs</span>
              <strong>18.4k</strong>
            </article>
            <article>
              <span>alerts</span>
              <strong>06</strong>
            </article>
            <article>
              <span>workers</span>
              <strong>14</strong>
            </article>
          </section>

          <section className="mono-panels">
            <div className="mono-panels__plot" />
            <div className="mono-panels__stack">
              <div />
              <div />
            </div>
          </section>
        </section>
      </section>
    </main>
  )
}
