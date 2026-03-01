export const queryKeys = {
  health: {
    all: ['health'] as const,
    deep: () => ['health-deep'] as const,
  },
  projects: {
    all: () => ['projects'] as const,
  },
  config: {
    envStatus: () => ['app-env-status'] as const,
  },
  process: {
    all: () => ['process'] as const,
    list: (limit = 50) => ['process', 'list', limit] as const,
    stats: () => ['process', 'stats'] as const,
    history: (limit = 50) => ['process', 'history', limit] as const,
    detail: (taskId: string) => ['process', 'detail', taskId] as const,
    logs: (taskId: string, tail = 200) => ['process', 'logs', taskId, tail] as const,
  },
  ingest: {
    all: () => ['ingest'] as const,
    history: (limit = 8) => ['ingest', 'history', limit] as const,
  },
} as const
