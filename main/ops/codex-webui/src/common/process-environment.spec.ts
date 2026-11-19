import { ConfigService } from '@nestjs/config';
import { spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import { spawn as spawnTerminal } from 'node-pty';
import { CodexProcessManager } from '../codex/codex-process-manager.service';
import type { FilesService } from '../files/files.service';
import type { SettingsService } from '../settings/settings.service';
import { TerminalService } from '../terminal/terminal.service';

vi.mock('node:child_process', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:child_process')>()),
  spawn: vi.fn(),
}));
vi.mock('node-pty', () => ({ spawn: vi.fn() }));
vi.mock('../codex/codex-jsonrpc-client', () => ({
  CodexJsonRpcClient: class {
    on = vi.fn();
    initialize = vi.fn().mockResolvedValue({});
    destroy = vi.fn();
  },
}));

describe('WebUI subprocess environment', () => {
  beforeEach(() => {
    vi.stubEnv('MRW_BACKEND_API_KEY', 'fixture-mrw-key');
    vi.stubEnv('WEBUI_API_KEY', 'fixture-webui-key');
    vi.stubEnv('CODEX_HOME', '/fixture/codex-home');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
  });

  it('passes Codex configuration but not WebUI keys to app-server', async () => {
    const service = new CodexProcessManager(new ConfigService());
    try {
      await service.onModuleInit();
      expect(spawn).toHaveBeenCalledOnce();
      const env = vi.mocked(spawn).mock.calls[0]?.[2]?.env;
      expect(env).toMatchObject({ CODEX_HOME: '/fixture/codex-home' });
      expect(env).not.toHaveProperty('MRW_BACKEND_API_KEY');
      expect(env).not.toHaveProperty('WEBUI_API_KEY');
      expect(process.env.MRW_BACKEND_API_KEY).toBe('fixture-mrw-key');
    } finally {
      service.onModuleDestroy();
    }
  });

  it('keeps the terminal working directory and omits the same service keys', async () => {
    vi.mocked(spawnTerminal).mockReturnValue({
      pid: 1,
      onData: vi.fn(),
      onExit: vi.fn(),
      kill: vi.fn(),
    } as unknown as ReturnType<typeof spawnTerminal>);
    const cwd = tmpdir();
    const service = new TerminalService(
      {
        getHomeDir: () => cwd,
        resolveSafePath: () => Promise.resolve(cwd),
      } as unknown as FilesService,
      {
        getNumberSetting: () => 100,
        getStringSetting: () => null,
        onChange: () => () => undefined,
      } as unknown as SettingsService,
    );
    try {
      await service.open('fixture-socket', { contextKey: 'global' });
      expect(spawnTerminal).toHaveBeenCalledOnce();
      const options = vi.mocked(spawnTerminal).mock.calls[0]?.[2];
      expect(options?.cwd).toBe(cwd);
      expect(options?.env).toMatchObject({ CODEX_HOME: '/fixture/codex-home' });
      expect(options?.env).not.toHaveProperty('MRW_BACKEND_API_KEY');
      expect(options?.env).not.toHaveProperty('WEBUI_API_KEY');
      expect(process.env.WEBUI_API_KEY).toBe('fixture-webui-key');
    } finally {
      service.onModuleDestroy();
    }
  });
});
