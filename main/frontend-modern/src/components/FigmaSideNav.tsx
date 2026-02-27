import type { ComponentType } from 'react'
import {
  AreaChart,
  Brain,
  Building2,
  Database,
  DatabaseZap,
  Download,
  Factory,
  FileInput,
  Folders,
  Landmark,
  Layers,
  LineChart,
  MessageSquare,
  Network,
  Package,
  Puzzle,
  Settings2,
  ShoppingBag,
  ShoppingCart,
  Sparkles,
  TrendingUp,
  Wrench,
  Zap,
} from 'lucide-react'

export type NavMode =
  | 'overviewTasks'
  | 'overviewData'
  | 'dataDashboard'
  | 'dataMarket'
  | 'dataSocial'
  | 'dataPolicy'
  | 'dataCatalog'
  | 'graphMarket'
  | 'graphPolicy'
  | 'graphSocial'
  | 'graphCompany'
  | 'graphProduct'
  | 'graphOperation'
  | 'graphDeep'
  | 'flowIngest'
  | 'flowSpecialized'
  | 'flowProcessing'
  | 'flowRawData'
  | 'flowExtract'
  | 'flowAnalysis'
  | 'flowBoard'
  | 'flowWorkflow'
  | 'sysProjects'
  | 'sysResource'
  | 'sysBackend'
  | 'sysSettings'
  | 'sysLlm'

type Props = {
  mode: NavMode
  onModeChange: (mode: NavMode) => void
  theme?: 'light' | 'dark' | 'brand'
}

const groups: Array<{ title: string; items: Array<{ key: NavMode; label: string }> }> = [
  {
    title: '总览',
    items: [
      { key: 'overviewTasks', label: '任务' },
      { key: 'overviewData', label: '数据' },
    ],
  },
  {
    title: '数据侧面',
    items: [
      { key: 'dataDashboard', label: '数据仪表盘' },
      { key: 'dataMarket', label: '市场' },
      { key: 'dataSocial', label: '舆情' },
      { key: 'dataPolicy', label: '政策' },
      { key: 'dataCatalog', label: '行业公司/商品/经营' },
    ],
  },
  {
    title: '图谱',
    items: [
      { key: 'graphMarket', label: '市场图谱' },
      { key: 'graphPolicy', label: '政策图谱' },
      { key: 'graphSocial', label: '社媒图谱' },
      { key: 'graphCompany', label: '公司图谱' },
      { key: 'graphProduct', label: '商品图谱' },
      { key: 'graphOperation', label: '电商/经营图谱' },
      { key: 'graphDeep', label: '市场实体加细图' },
    ],
  },
  {
    title: '流程视角',
    items: [
      { key: 'flowIngest', label: '采集' },
      { key: 'flowSpecialized', label: '特化采集' },
      { key: 'flowProcessing', label: '数据处理' },
      { key: 'flowRawData', label: '原始数据处理' },
      { key: 'flowExtract', label: '提取' },
      { key: 'flowAnalysis', label: '分析' },
      { key: 'flowBoard', label: '看板' },
      { key: 'flowWorkflow', label: '工作流模板' },
    ],
  },
  {
    title: '系统管理',
    items: [
      { key: 'sysProjects', label: '项目管理' },
      { key: 'sysResource', label: '信息资源库管理' },
      { key: 'sysBackend', label: '后端监控' },
      { key: 'sysSettings', label: '系统设置' },
      { key: 'sysLlm', label: 'LLM 配置' },
    ],
  },
]

const iconByLabel: Record<string, ComponentType<{ size?: number; className?: string }>> = {
  任务: Zap,
  数据: Database,
  数据仪表盘: AreaChart,
  市场: LineChart,
  舆情: MessageSquare,
  政策: Landmark,
  '行业公司/商品/经营': Factory,
  市场图谱: Network,
  政策图谱: Network,
  社媒图谱: Network,
  公司图谱: Building2,
  商品图谱: Package,
  '电商/经营图谱': ShoppingBag,
  市场实体加细图: TrendingUp,
  采集: Download,
  特化采集: Sparkles,
  数据处理: FileInput,
  原始数据处理: Database,
  提取: Puzzle,
  分析: Brain,
  看板: TrendingUp,
  工作流模板: TrendingUp,
  项目管理: Folders,
  信息资源库管理: DatabaseZap,
  后端监控: Layers,
  系统设置: Settings2,
  'LLM 配置': Wrench,
}

export default function FigmaSideNav({ mode, onModeChange, theme = 'dark' }: Props) {
  return (
    <aside className={`figma-side-nav is-${theme}`} data-node-id="1186:27288">
      <div className="figma-side-nav__group">
        {groups.map((group) => (
          <section key={group.title} className="figma-side-nav__section">
            <h4 className="figma-side-nav__title">{group.title}</h4>
            {group.items.map((item) => {
              const Icon = iconByLabel[item.label] || ShoppingCart
              const active = mode === item.key
              return (
                <button
                  type="button"
                  key={item.key}
                  className={`figma-side-nav__item ${active ? 'is-active' : ''}`}
                  onClick={() => onModeChange(item.key)}
                >
                  <Icon size={15} className="figma-side-nav__icon" />
                  <span className="figma-side-nav__label">{item.label}</span>
                </button>
              )
            })}
          </section>
        ))}
      </div>
      <button type="button" className="figma-side-nav__fold" aria-label="sidebar hint">
        <Wrench size={14} />
      </button>
    </aside>
  )
}
