import type { LayerId } from './types'
import type { useKernelRuntime } from './useKernelRuntime'

type Runtime = ReturnType<typeof useKernelRuntime>

type Props = {
  activeLayer: LayerId
  runtime: Runtime
}

const DEFAULT_MODULE_BY_LAYER = {
  A: 'flowWriting',
  B: 'dataDashboard',
  C: 'overviewTasks',
} as const

const LAYERS: Array<{ id: LayerId; label: string }> = [
  { id: 'A', label: 'Workbench' },
  { id: 'B', label: 'Visual' },
  { id: 'C', label: 'Admin' },
]

export default function LayerSwitch({ activeLayer, runtime }: Props) {
  return (
    <nav className="kernel-layer-switch" aria-label="Layer navigation">
      {LAYERS.map((layer) => {
        const active = layer.id === activeLayer
        return (
          <button
            key={layer.id}
            type="button"
            className={`kernel-layer-switch__item ${active ? 'is-active' : ''}`.trim()}
            onClick={() => {
              if (active) return
              runtime.navigateToModule(DEFAULT_MODULE_BY_LAYER[layer.id])
            }}
          >
            <span>{layer.id}</span>
            <strong>{layer.label}</strong>
          </button>
        )
      })}
    </nav>
  )
}
