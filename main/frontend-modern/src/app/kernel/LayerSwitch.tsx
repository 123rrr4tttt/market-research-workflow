import { translate, useAppLocale, type MessageKey } from '../platform/i18n'
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

const LAYERS: Array<{ id: LayerId; labelKey: MessageKey }> = [
  { id: 'A', labelKey: 'shell.layerSwitch.workbench' },
  { id: 'B', labelKey: 'shell.layerSwitch.visual' },
  { id: 'C', labelKey: 'shell.layerSwitch.admin' },
]

export default function LayerSwitch({ activeLayer, runtime }: Props) {
  const locale = useAppLocale()

  return (
    <nav className="kernel-layer-switch" aria-label={translate(locale, 'shell.layerSwitch.ariaLabel')}>
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
            <strong>{translate(locale, layer.labelKey)}</strong>
          </button>
        )
      })}
    </nav>
  )
}
