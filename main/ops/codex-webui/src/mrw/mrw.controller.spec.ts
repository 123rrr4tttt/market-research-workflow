import { HttpException, HttpStatus } from '@nestjs/common';
import { MrwController } from './mrw.controller';

describe('MrwController', () => {
  let controller: MrwController;
  const mockMrw = {
    confirmAction: vi.fn(),
    listPending: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    controller = new MrwController(mockMrw as never);
  });

  it('confirms an action through the service', async () => {
    mockMrw.confirmAction.mockResolvedValue({
      confirmed: true,
      actionId: 'a1',
      approved: true,
      threadId: 't1',
    });

    const body = {
      threadId: 't1',
      turnId: 'turn1',
      actionId: 'a1',
      approved: true,
    };

    await expect(controller.confirm(body)).resolves.toEqual({
      confirmed: true,
      actionId: 'a1',
      approved: true,
      threadId: 't1',
    });
    expect(mockMrw.confirmAction).toHaveBeenCalledWith(body);
  });

  it('requires a threadId to list pending actions', async () => {
    let caught: unknown;
    try {
      await controller.pending(undefined);
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(HttpException);
    expect((caught as HttpException).getStatus()).toBe(HttpStatus.BAD_REQUEST);
  });

  it('lists pending actions for a thread', async () => {
    mockMrw.listPending.mockReturnValue([
      {
        actionId: 'a1',
        threadId: 't1',
        turnId: 'turn1',
        toolName: 'demo.write',
        projectKey: 'p1',
        callId: 'call1',
      },
    ]);

    await expect(controller.pending('t1')).resolves.toHaveLength(1);
    expect(mockMrw.listPending).toHaveBeenCalledWith('t1');
  });
});
