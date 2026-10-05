import { beforeEach, describe, expect, it, vi } from 'vitest';

const io = vi.fn();

vi.mock('socket.io-client', () => ({ io }));

describe('socket singleton', () => {
  beforeEach(() => {
    vi.resetModules();
    io.mockReset();
  });

  it('reconnects the same instance and keeps live hook subscriptions', async () => {
    const instance = {
      disconnect: vi.fn(),
      connect: vi.fn(),
    };
    io.mockReturnValue(instance);

    const { getSocket, resetSocket } = await import('./socket');
    const socket = getSocket();
    resetSocket();

    expect(getSocket()).toBe(socket);
    expect(instance.disconnect).toHaveBeenCalledTimes(1);
    expect(instance.connect).toHaveBeenCalledTimes(1);
    expect(io).toHaveBeenCalledTimes(1);
  });
});
