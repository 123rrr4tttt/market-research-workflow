import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const invalidate = vi.fn();
const auth = vi.hoisted(() => {
  const state: { token: string | null } = { token: 'expired' };
  return {
    state,
    getApiToken: () => state.token,
    clearApiToken: () => {
      state.token = null;
    },
  };
});

vi.mock('@/auth-token', () => auth);

vi.mock('@tanstack/react-router', () => ({
  Outlet: () => null,
  useNavigate: () => vi.fn(),
  useRouter: () => ({ invalidate }),
  useRouterState: ({ select }: { select?: (value: unknown) => unknown }) =>
    select?.({ location: { pathname: '/' } }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/components/ui/tooltip', () => ({
  TooltipProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock('@/components/ui/sheet', () => ({
  Sheet: ({ children }: { children: ReactNode }) => children,
  SheetContent: ({ children }: { children: ReactNode }) => children,
  SheetTitle: () => null,
}));
vi.mock('@/components/chat/chat-header', () => ({ ChatHeader: () => null }));
vi.mock('@/components/chat/thread-sidebar', () => ({
  ThreadSidebar: () => null,
}));
vi.mock('@/components/snackbar/snackbar-container', () => ({
  SnackbarContainer: () => null,
}));
vi.mock('@/components/codex-status-banner', () => ({
  CodexStatusBanner: () => null,
}));

vi.mock('@/hooks/use-codex-socket', () => ({ useCodexSocket: vi.fn() }));
vi.mock('@/hooks/use-breakpoint', () => ({ useBreakpoint: () => 'desktop' }));

const filesState = { setRootDir: vi.fn() };
const timelineState = {
  threadCwd: null,
  addApprovalForThread: vi.fn(),
  addUserInputRequestForThread: vi.fn(),
  ensureThreadState: vi.fn(),
  hydrateTimelineForThread: vi.fn(),
  setLoadingForThread: vi.fn(),
  setThreadStatusForThread: vi.fn(),
  setActiveTurnIdForThread: vi.fn(),
  setThreadTitleForThread: vi.fn(),
  setActiveThread: vi.fn(),
  setMaxIdleSubscriptions: vi.fn(),
  cleanupIdleThreadSubscriptions: vi.fn(),
};
const themeState = { dark: false, toggleDark: vi.fn() };

vi.mock('@/stores/files-store', () => ({
  useFilesStore: (selector: (state: typeof filesState) => unknown) =>
    selector(filesState),
}));
vi.mock('@/stores/layout-store', () => ({
  useLayoutStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({ isSidebarOpen: true, setSidebarOpen: vi.fn() }),
}));
vi.mock('@/stores/timeline-store', () => ({
  useTimelineStore: (selector: (state: typeof timelineState) => unknown) =>
    selector(timelineState),
}));
vi.mock('@/stores/theme-store', () => ({
  useThemeStore: (selector: (state: typeof themeState) => unknown) =>
    selector(themeState),
}));

vi.mock('@/generated/api', () => ({
  filesGetRoots: vi.fn(() => Promise.resolve({ data: { homeDir: '/tmp' } })),
  filesAddRoot: vi.fn(() => Promise.resolve({})),
}));
vi.mock('@/generated/api/sdk.gen', () => ({
  pendingApprovalsListPending: vi.fn(() => Promise.resolve({ data: { requests: [] } })),
  settingsListSettings: vi.fn(() => Promise.resolve({ data: { settings: [] } })),
  threadsListLoadedThreads: vi.fn(() =>
    Promise.resolve({ data: { data: [], nextCursor: null } }),
  ),
  threadsResumeThread: vi.fn(() => Promise.resolve({ data: null })),
}));
vi.mock('@/generated/api/@tanstack/react-query.gen', () => ({
  settingsListSettingsQueryKey: () => ['settings'],
}));
vi.mock('@/hooks/use-thread-open', () => ({
  applyOpenResponse: vi.fn(),
}));

const socket = {
  connect: vi.fn(),
  disconnect: vi.fn(),
  off: vi.fn(),
  on: vi.fn(),
};

vi.mock('@/socket', () => ({
  getSocket: () => socket,
  resetSocket: () => {
    socket.disconnect();
    socket.connect();
  },
}));

describe('AuthenticatedLayout auth recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    invalidate.mockReset();
    auth.state.token = 'expired';
  });

  it('refreshes once, then reconnects the original socket only after bootstrap', async () => {
    const operations: Array<string> = [];
    let resolveBootstrap!: (value: void) => void;
    invalidate.mockImplementation(() => {
      operations.push('invalidate');
      return new Promise<void>((resolve) => {
        resolveBootstrap = () => {
          auth.state.token = 'new';
          operations.push('token');
          resolve();
        };
      });
    });
    socket.disconnect.mockImplementation(() => operations.push('disconnect'));
    socket.connect.mockImplementation(() => operations.push('connect'));

    const { AuthenticatedLayout } = await import('./authenticated-layout');
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AuthenticatedLayout />
      </QueryClientProvider>,
    );

    act(() => {
      window.dispatchEvent(new Event('codex-webui:auth-expired'));
    });
    await act(async () => {
      resolveBootstrap();
    });

    expect(operations).toEqual([
      'disconnect',
      'invalidate',
      'token',
      'disconnect',
      'connect',
    ]);
    expect(auth.state.token).toBe('new');
  });

  it('merges simultaneous auth failures into one recovery', async () => {
    let resolveBootstrap!: (value: void) => void;
    invalidate.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveBootstrap = () => {
            auth.state.token = 'new';
            resolve();
          };
        }),
    );

    const { AuthenticatedLayout } = await import('./authenticated-layout');
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AuthenticatedLayout />
      </QueryClientProvider>,
    );

    act(() => {
      window.dispatchEvent(new Event('codex-webui:auth-expired'));
      window.dispatchEvent(new Event('codex-webui:auth-expired'));
    });
    await act(async () => {
      resolveBootstrap();
    });

    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(socket.disconnect).toHaveBeenCalledTimes(2);
    expect(socket.connect).toHaveBeenCalledTimes(1);
  });

  it('does not reconnect when bootstrap completes without a token', async () => {
    invalidate.mockResolvedValue(undefined);

    const { AuthenticatedLayout } = await import('./authenticated-layout');
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AuthenticatedLayout />
      </QueryClientProvider>,
    );

    await act(async () => {
      window.dispatchEvent(new Event('codex-webui:auth-expired'));
    });

    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(socket.disconnect).toHaveBeenCalledTimes(1);
    expect(socket.connect).not.toHaveBeenCalled();
    expect(auth.state.token).toBeNull();
  });

});
