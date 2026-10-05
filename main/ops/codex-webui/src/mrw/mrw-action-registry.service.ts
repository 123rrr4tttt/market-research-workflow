import { Injectable } from '@nestjs/common';
import type { MrwPendingAction } from './mrw.types';

/** One held-back dynamic tool call that still needs a trusted confirmation. */
export type MrwPendingRecord = MrwPendingAction & {
  requestId: string | number;
  namespace: string | null;
  tool: string;
};

/**
 * In-memory pending map for MRW host tool confirmations.
 *
 * Keyed by the stable backend approval id so a reconnect can replay the card
 * through GET /api/mrw/pending without inventing a new approval identity.
 */
@Injectable()
export class MrwActionRegistryService {
  private readonly records = new Map<string, MrwPendingRecord>();

  record(record: MrwPendingRecord): void {
    this.records.set(record.actionId, record);
  }

  get(actionId: string): MrwPendingRecord | undefined {
    return this.records.get(actionId);
  }

  listForThread(threadId: string): MrwPendingAction[] {
    const normalized = threadId.trim();
    return [...this.records.values()]
      .filter((record) => record.threadId === normalized)
      .map(({ requestId, namespace, tool, ...action }) => action);
  }

  getForThread(threadId: string): MrwPendingRecord[] {
    const normalized = threadId.trim();
    return [...this.records.values()].filter(
      (record) => record.threadId === normalized,
    );
  }

  getAll(): MrwPendingRecord[] {
    return [...this.records.values()];
  }

  remove(actionId: string): void {
    this.records.delete(actionId);
  }

  cancelForThread(threadId: string): string[] {
    const normalized = threadId.trim();
    const removed: string[] = [];
    for (const [actionId, record] of this.records) {
      if (record.threadId === normalized) {
        removed.push(actionId);
        this.records.delete(actionId);
      }
    }
    return removed;
  }

  clear(): void {
    this.records.clear();
  }
}
