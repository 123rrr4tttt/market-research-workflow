import { MrwActionRegistryService } from './mrw-action-registry.service';
import type { MrwPendingRecord } from './mrw-action-registry.service';

function record(overrides: Partial<MrwPendingRecord> = {}): MrwPendingRecord {
  return {
    actionId: 'a1',
    threadId: 't1',
    turnId: 'turn1',
    toolName: 'demo.write',
    arguments: { target: 'a' },
    projectKey: 'p1',
    callId: 'call1',
    requestId: 1,
    namespace: 'demo',
    tool: 'write',
    ...overrides,
  };
}

describe('MrwActionRegistryService', () => {
  let registry: MrwActionRegistryService;

  beforeEach(() => {
    registry = new MrwActionRegistryService();
  });

  it('records, reads, and lists pending actions by thread', () => {
    registry.record(record());
    registry.record(record({ actionId: 'a2', threadId: 't2', requestId: 2 }));

    expect(registry.get('a1')?.requestId).toBe(1);
    expect(registry.listForThread('t1')).toHaveLength(1);
    expect(registry.listForThread('t1')[0]).not.toHaveProperty('requestId');
  });

  it('removes one action without touching the others', () => {
    registry.record(record());
    registry.record(record({ actionId: 'a2', requestId: 2 }));

    registry.remove('a1');

    expect(registry.get('a1')).toBeUndefined();
    expect(registry.get('a2')).toBeDefined();
  });

  it('cancels every pending action for a thread', () => {
    registry.record(record());
    registry.record(record({ actionId: 'a2', requestId: 2 }));
    registry.record(record({ actionId: 'a3', threadId: 't2', requestId: 3 }));

    const removed = registry.cancelForThread('t1');

    expect(removed).toEqual(['a1', 'a2']);
    expect(registry.listForThread('t1')).toHaveLength(0);
    expect(registry.listForThread('t2')).toHaveLength(1);
  });
});
