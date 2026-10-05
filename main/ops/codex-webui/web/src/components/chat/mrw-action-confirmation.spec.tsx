import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MrwActionConfirmation } from './mrw-action-confirmation';

const { handlers } = vi.hoisted(() => ({ handlers: new Map<string, (value: unknown) => void>() }));
vi.mock('@/socket', () => ({ getSocket: () => ({
  on: (name: string, callback: (value: unknown) => void) => handlers.set(name, callback),
  off: (name: string) => handlers.delete(name),
}) }));
vi.mock('@/auth-token', () => ({ getApiToken: () => 'test-browser-token' }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (value: string) => value }) }));
vi.mock('@/stores/timeline-store', () => ({
  useTimelineStore: (selector: (value: { threadId: string }) => unknown) => selector({ threadId: 'thread-1' }),
}));

afterEach(() => { vi.unstubAllGlobals(); handlers.clear(); });

describe('MRW same-chat confirmation', () => {
  it('never auto-approves a model request and submits only the selected action on a user click', async () => {
    const request = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    vi.stubGlobal('fetch', request);
    render(<MrwActionConfirmation />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    const action = {
      actionId: 'approval-1', threadId: 'thread-1', turnId: 'turn-1',
      projectKey: 'hk_water_investigation', toolName: 'agent_macro.registration_package.activate',
      actionDigest: 'a'.repeat(64), arguments: { package_id: 'test.cell' },
    };
    act(() => { handlers.get('mrw.actionRequired')?.({ ...action, threadId: 'other-thread' }); });
    expect(screen.queryByRole('button', { name: 'Allow once' })).toBeNull();
    act(() => { handlers.get('mrw.actionRequired')?.(action); });
    expect(screen.getByText(action.toolName)).toBeTruthy();
    expect(request).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Allow once' }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    const [url, options] = request.mock.calls[1];
    expect(url).toContain('/api/mrw/confirm');
    expect(JSON.parse(options.body)).toEqual({
      threadId: 'thread-1', turnId: 'turn-1', actionId: 'approval-1', approved: true,
      userText: `approval:approval-1 Allow once ${action.toolName}`,
    });
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Allow once' })).toBeNull());
  });
});
