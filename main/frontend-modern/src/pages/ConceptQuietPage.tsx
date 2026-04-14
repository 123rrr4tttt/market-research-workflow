import './concept-lab.css'

export default function ConceptQuietPage() {
  return (
    <main className="concept-page concept-page--quiet">
      <header className="quiet-hero">
        <div className="quiet-hero__meta">Signal archive / editorial field / v1</div>
        <h1>Market intelligence, arranged like a quiet exhibition.</h1>
        <p>
          壳层退后，数据前置。让信息像策展内容一样自然展开，而不是被大量控件包围。
        </p>
      </header>

      <section className="quiet-grid">
        <aside className="quiet-nav">
          <span>Overview</span>
          <span>Signals</span>
          <span>Flows</span>
          <span>Field Notes</span>
        </aside>

        <div className="quiet-stage">
          <section className="quiet-stage__headline">
            <div>
              <small>Current Lens</small>
              <strong>From raw documents to editorial-grade synthesis</strong>
            </div>
            <div className="quiet-stage__metrics">
              <span>18.4k documents</span>
              <span>248 active signals</span>
              <span>31 pipelines</span>
            </div>
          </section>

          <section className="quiet-stage__row">
            <article className="quiet-sheet">
              <small>Lead Story</small>
              <h2>Cross-market movement is starting in policy, not pricing.</h2>
              <p>
                This surface favors sequence and reading rhythm. Controls stay minimal; context appears as text,
                annotation, and soft data marks.
              </p>
            </article>
            <article className="quiet-column">
              <small>Context</small>
              <span>Updated 08:40</span>
              <span>Confidence 0.81</span>
              <span>3 linked narratives</span>
            </article>
          </section>

          <section className="quiet-timeline">
            <div />
            <div />
            <div />
            <div />
          </section>
        </div>
      </section>
    </main>
  )
}
