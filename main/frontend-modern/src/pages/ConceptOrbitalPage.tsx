import './concept-lab.css'

export default function ConceptOrbitalPage() {
  return (
    <main className="concept-page concept-page--orbital">
      <div className="orbital-noise" />
      <header className="orbital-topline">
        <span>orbital plane</span>
        <span>market research workbench</span>
      </header>

      <section className="orbital-stage">
        <aside className="orbital-track orbital-track--left">
          <span>overview</span>
          <span>research</span>
          <span>writing</span>
        </aside>

        <section className="orbital-core">
          <p>Spatial operations surface</p>
          <h1>Depth without clutter.</h1>
          <strong>Glass is background structure here, not a pile of translucent cards.</strong>
        </section>

        <section className="orbital-plane orbital-plane--primary">
          <small>Primary scene</small>
          <div />
        </section>

        <section className="orbital-plane orbital-plane--secondary">
          <small>Telemetry</small>
          <div />
          <div />
        </section>

        <aside className="orbital-track orbital-track--right">
          <span>signal 248</span>
          <span>pipelines 31</span>
          <span>notes 12</span>
        </aside>
      </section>
    </main>
  )
}
