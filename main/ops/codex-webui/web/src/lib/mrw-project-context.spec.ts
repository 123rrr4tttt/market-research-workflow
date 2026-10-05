import { describe, expect, it, vi } from 'vitest';
import { attachMrwProjectContext, getMrwProjectKey } from './mrw-project-context';

describe('MRW parent project context', () => {
  it('only accepts a valid project selection from the exact allowed parent', () => {
    const parent = { postMessage: vi.fn() };
    let receive: (event: MessageEvent) => void = () => {};
    const removeEventListener = vi.fn();
    const host = {
      parent,
      location: { origin: 'http://127.0.0.1:8172' },
      document: { referrer: 'http://127.0.0.1:5174/' },
      addEventListener: (_name: string, listener: typeof receive) => { receive = listener; },
      removeEventListener,
    } as unknown as Window;
    const cleanup = attachMrwProjectContext(host);
    expect(parent.postMessage).toHaveBeenCalledWith(
      { type: 'mrw.project-context-ready' }, 'http://127.0.0.1:5174',
    );
    const send = (source: unknown, origin: string, projectKey: string) => receive({
      source, origin, data: { type: 'mrw.project-context', projectKey },
    } as MessageEvent);
    send({}, 'http://127.0.0.1:5174', 'forged_source');
    send(parent, 'https://untrusted.example', 'forged_origin');
    expect(getMrwProjectKey()).toBeUndefined();
    send(parent, 'http://127.0.0.1:5174', 'hk_water_investigation');
    expect(getMrwProjectKey()).toBe('hk_water_investigation');
    send(parent, 'http://127.0.0.1:5174', '../another_project');
    expect(getMrwProjectKey()).toBe('hk_water_investigation');
    send(parent, 'http://127.0.0.1:5174', 'project_b');
    expect(getMrwProjectKey()).toBe('project_b');
    cleanup();
    expect(removeEventListener).toHaveBeenCalledWith('message', receive);
  });
});
