import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const socket = {
  connected: false,
  connect: vi.fn(),
  off: vi.fn(),
  on: vi.fn(),
};

vi.mock('../socket', () => ({ getSocket: () => socket }));
vi.mock('@/stores/connection-store', () => ({
  useConnectionStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({ setConnected: vi.fn() }),
}));

describe('useCodexSocket disconnect handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('leaves authentication recovery to REST 401 handling', async () => {
    socket.connected = false;
    const { useCodexSocket } = await import('./use-codex-socket');
    const { unmount } = renderHook(() => useCodexSocket(true), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={new QueryClient()}>
          {children}
        </QueryClientProvider>
      ),
    });

    const registration = socket.on.mock.calls.find(([event]) => event === 'disconnect');
    const handleDisconnect = registration?.[1] as (reason: string) => void;
    const authExpired = vi.fn();
    window.addEventListener('codex-webui:auth-expired', authExpired);

    handleDisconnect('transport close');
    handleDisconnect('io server disconnect');
    expect(authExpired).not.toHaveBeenCalled();

    window.removeEventListener('codex-webui:auth-expired', authExpired);
    expect(socket.connect).toHaveBeenCalledTimes(1);
    unmount();
  });

  it('syncs an already-connected singleton without reconnecting', async () => {
    socket.connected = true;
    const { useCodexSocket } = await import('./use-codex-socket');
    const { unmount } = renderHook(() => useCodexSocket(true), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={new QueryClient()}>
          {children}
        </QueryClientProvider>
      ),
    });

    expect(socket.connect).not.toHaveBeenCalled();
    unmount();
  });
});
