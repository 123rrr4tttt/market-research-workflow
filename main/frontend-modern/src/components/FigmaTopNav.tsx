import { Bell, Search, Settings, User, X } from 'lucide-react'

export type NavMode = 'ingest' | 'dashboard' | 'process' | 'projects' | 'settings'
export type FigmaTheme = 'light' | 'dark' | 'brand'

type Props = {
  mode: NavMode
  onModeChange: (mode: NavMode) => void
  healthText: string
  projectKey: string
  projectOptions: string[]
  onProjectChange: (projectKey: string) => void
  projectDisabled?: boolean
  theme?: FigmaTheme
}

const MENUS: Array<{ key: NavMode; label: string }> = [
  { key: 'ingest', label: '采集控制台' },
  { key: 'dashboard', label: '业务看板' },
  { key: 'process', label: '流程任务' },
  { key: 'projects', label: '项目管理' },
  { key: 'settings', label: '系统设置' },
  { key: 'dashboard', label: '系统概览' },
]

export default function FigmaTopNav({
  mode,
  onModeChange,
  healthText,
  projectKey,
  projectOptions,
  onProjectChange,
  projectDisabled,
  theme = 'light',
}: Props) {
  return (
    <header className={`figma-top-nav is-${theme}`} data-node-id="461:24152">
      <div className="figma-top-nav__main">
        <div className="figma-top-nav__left">
          <div className="figma-top-nav__logo">YOU LOGO</div>
          <div className="figma-top-nav__menus">
            {MENUS.map((item, index) => {
              const active = index === 1 ? mode === item.key : false
              return (
                <button
                  key={`${item.label}-${index}`}
                  className={`figma-top-nav__menu ${active ? 'is-active' : ''}`}
                  onClick={() => onModeChange(item.key)}
                  type="button"
                >
                  <span>{item.label}</span>
                  <span className="figma-top-nav__chevron">⌄</span>
                </button>
              )
            })}
          </div>
        </div>

        <div className="figma-top-nav__right">
          <button type="button" className="figma-top-nav__icon-btn"><Search size={14} /></button>
          <button type="button" className="figma-top-nav__icon-btn"><Bell size={14} /></button>
          <button type="button" className="figma-top-nav__icon-btn"><Settings size={14} /></button>
          <button type="button" className="figma-top-nav__icon-btn"><User size={14} /></button>
          <span className="figma-top-nav__health">{healthText}</span>
          <select
            className="figma-top-nav__project"
            value={projectKey}
            onChange={(e) => onProjectChange(e.target.value)}
            disabled={projectDisabled}
          >
            <option value={projectKey}>{projectKey}</option>
            {projectOptions.map((key) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="figma-top-nav__tabs">
        {Array.from({ length: 5 }).map((_, index) => (
          <div className="figma-top-nav__tab" key={`tab-${index}`}>
            <span>选项卡</span>
            <X size={12} />
          </div>
        ))}
      </div>
    </header>
  )
}
