import { useState, type ComponentType } from 'react'
import {
  ChevronDown,
  Plus,
  Wrench,
} from 'lucide-react'
import type { NavMode } from '../app/kernel/types'
import { MODULE_ICON_BY_KEY } from '../app/kernel/moduleChrome'
import { translate, useAppLocale } from '../app/platform/i18n'
import { getModulesByGroup, MODULE_NAV_GROUP_KEYS } from '../app/platform/modules'
import type { ModuleDescriptor, ModuleNavGroupKey } from '../app/platform/modules'
import { resolveInteractionSurface } from '../app/topology/contracts'
import type { InteractionSurface } from '../app/topology/surfaces'

export type { NavMode } from '../app/kernel/types'

type Props = {
  mode: NavMode
  onModeChange: (mode: NavMode) => void
  surface: InteractionSurface
  onSurfaceChange: (surface: InteractionSurface) => void
  theme?: 'light' | 'dark' | 'brand'
}

export default function FigmaSideNav({ mode, onModeChange, surface, onSurfaceChange, theme = 'dark' }: Props) {
  const locale = useAppLocale()
  const [expandedByGroup, setExpandedByGroup] = useState<Record<ModuleNavGroupKey, boolean>>(() =>
    Object.fromEntries(MODULE_NAV_GROUP_KEYS.map((groupKey) => [groupKey, true])) as Record<ModuleNavGroupKey, boolean>,
  )
  const visibleGroups: Array<{ groupKey: ModuleNavGroupKey; items: ModuleDescriptor[] }> = MODULE_NAV_GROUP_KEYS
    .map((group) => ({
      groupKey: group,
      items: getModulesByGroup(group).filter((item) => resolveInteractionSurface(item.mode) === surface),
    }))
    .filter((group) => group.items.length > 0)

  return (
    <aside className={`figma-side-nav is-${theme}`} data-node-id="1186:27288" data-surface={surface}>
      <div className="figma-side-nav__surface-switch" role="tablist" aria-label="interaction surface switch">
        <button
          type="button"
          role="tab"
          aria-selected={surface === 'management'}
          className={`figma-side-nav__surface-btn ${surface === 'management' ? 'is-active' : ''}`.trim()}
          onClick={() => onSurfaceChange('management')}
        >
          Management
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={surface === 'workbench'}
          className={`figma-side-nav__surface-btn ${surface === 'workbench' ? 'is-active' : ''}`.trim()}
          onClick={() => onSurfaceChange('workbench')}
        >
          Workbench
        </button>
      </div>
      <div className="figma-side-nav__group">
        {visibleGroups.map((group) => {
          const expanded = expandedByGroup[group.groupKey] || group.items.some((item) => item.mode === mode)
          return (
            <section key={group.groupKey} className="figma-side-nav__section">
              <div className="figma-side-nav__title-row">
                <button
                  type="button"
                  className="figma-side-nav__title"
                  onClick={() => {
                    setExpandedByGroup((prev) => {
                      const currentlyExpanded = prev[group.groupKey] || group.items.some((item) => item.mode === mode)
                      return { ...prev, [group.groupKey]: !currentlyExpanded }
                    })
                  }}
                >
                  <span>{translate(locale, group.groupKey, group.groupKey)}</span>
                  <ChevronDown
                    size={14}
                    className={`figma-side-nav__title-chevron ${expanded ? 'is-open' : ''}`}
                  />
                </button>
                {group.groupKey === 'navigation.group.graph' && group.items.some((item) => item.mode === 'graphBuilder') ? (
                  <button
                    type="button"
                    className={`figma-side-nav__title-plus ${mode === 'graphBuilder' ? 'is-active' : ''}`.trim()}
                    onClick={() => onModeChange('graphBuilder')}
                    title={translate(locale, 'navigation.action.createGraph', 'Create Graph')}
                    aria-label={translate(locale, 'navigation.action.createGraph', 'Create Graph')}
                  >
                    <Plus size={14} />
                  </button>
                ) : null}
              </div>
              {expanded ? group.items.map((item) => {
                const Icon = MODULE_ICON_BY_KEY[item.mode] as ComponentType<{ size?: number; className?: string }>
                const active = mode === item.mode
                return (
                  <button
                    type="button"
                    key={item.mode}
                    className={`figma-side-nav__item ${active ? 'is-active' : ''}`}
                    onClick={() => onModeChange(item.mode)}
                  >
                    <Icon size={15} className="figma-side-nav__icon" />
                    <span className="figma-side-nav__label">
                      {translate(locale, item.navLabelKey, item.mode)}
                    </span>
                  </button>
                )
              }) : null}
            </section>
          )
        })}
      </div>
      <button type="button" className="figma-side-nav__fold" aria-label="sidebar hint">
        <Wrench size={14} />
      </button>
    </aside>
  )
}
