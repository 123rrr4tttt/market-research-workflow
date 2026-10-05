import { Injectable } from '@nestjs/common';
import { EventEmitter } from 'node:events';
import type { MrwPendingAction } from './mrw.types';

export const MRW_ACTION_REQUIRED = 'mrw.actionRequired';
export const MRW_ACTION_RESOLVED = 'mrw.actionResolved';

export type MrwActionResolvedEvent = { actionId: string; threadId: string };

/**
 * In-process bridge between the MRW service and the socket gateway.
 * Keeps the service free of any socket/server dependency so it stays testable.
 */
@Injectable()
export class MrwEventBus {
  private readonly emitter = new EventEmitter();

  emitActionRequired(action: MrwPendingAction): void {
    this.emitter.emit(MRW_ACTION_REQUIRED, action);
  }

  emitActionResolved(actionId: string, threadId: string): void {
    const event: MrwActionResolvedEvent = { actionId, threadId };
    this.emitter.emit(MRW_ACTION_RESOLVED, event);
  }

  onActionRequired(handler: (action: MrwPendingAction) => void): () => void {
    this.emitter.on(MRW_ACTION_REQUIRED, handler);
    return () => this.emitter.off(MRW_ACTION_REQUIRED, handler);
  }

  onActionResolved(handler: (event: MrwActionResolvedEvent) => void): () => void {
    this.emitter.on(MRW_ACTION_RESOLVED, handler);
    return () => this.emitter.off(MRW_ACTION_RESOLVED, handler);
  }
}
