type BaselineDuplicationItem = {
  concern: 'title' | 'navigation' | 'route-hash' | 'page-mount'
  files: string[]
}

export const WAVE_A_HOTSPOT_FILES = [
  'src/app/shell/AppShell.tsx',
  'src/app/navigation/index.ts',
  'src/components/FigmaSideNav.tsx',
  'src/pages/SettingsPage.tsx',
  'src/index.css',
] as const

export const WAVE_A_SHELL_STRING_INVENTORY = {
  hardcodedTitleLabels: [
    '任务',
    '数据',
    '数据仪表盘',
    '市场图谱',
    '写作工作台',
    '系统设置',
    'LLM 配置',
  ],
  hardcodedNavGroupLabels: ['总览', '数据侧面', '图谱', '流程视角', '系统管理'],
  hardcodedNavActionLabels: ['新建图谱'],
} as const

export const WAVE_A_DUPLICATED_METADATA_MAP: BaselineDuplicationItem[] = [
  {
    concern: 'title',
    files: ['src/app/shell/AppShell.tsx', 'src/components/FigmaSideNav.tsx'],
  },
  {
    concern: 'navigation',
    files: ['src/components/FigmaSideNav.tsx', 'src/app/navigation/index.ts'],
  },
  {
    concern: 'route-hash',
    files: ['src/app/navigation/index.ts', 'src/app/shell/AppShell.tsx'],
  },
  {
    concern: 'page-mount',
    files: ['src/app/shell/AppShell.tsx'],
  },
]

export const WAVE_A_EXAMPLE_KEY_MIGRATION = {
  fromLabel: '任务',
  localeKey: 'navigation.item.overviewTasks',
} as const

