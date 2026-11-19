import { HttpException, HttpStatus } from '@nestjs/common';
import {
  MrwBackendClient,
  readMrwRequestCredentials,
} from './mrw-backend.client';

describe('MrwBackendClient', () => {
  const originalUrl = process.env.MRW_BACKEND_URL;
  const originalKey = process.env.MRW_BACKEND_API_KEY;

  beforeEach(() => {
    process.env.MRW_BACKEND_URL = 'http://backend/';
    process.env.MRW_BACKEND_API_KEY = 'server-secret';
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    if (originalUrl === undefined) delete process.env.MRW_BACKEND_URL;
    else process.env.MRW_BACKEND_URL = originalUrl;
    if (originalKey === undefined) delete process.env.MRW_BACKEND_API_KEY;
    else process.env.MRW_BACKEND_API_KEY = originalKey;
  });

  it('forwards only the configured MRW cookie and original MRW token', async () => {
    vi.stubEnv('CODEX_OAUTH_COOKIE_NAME', 'custom_mrw_session');
    const credentials = readMrwRequestCredentials({
      cookie:
        'other=private; custom_mrw_session=mrw-session; codex_session=wrong-name',
      authorization: 'Bearer webui-jwt',
      'x-codex-auth': 'mrw-token',
    });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok', data: {} }),
    });
    vi.stubGlobal('fetch', fetchMock);
    await new MrwBackendClient().recordInput(
      't1',
      'turn1',
      'read',
      'admission-1',
      credentials,
    );
    expect(fetchMock.mock.calls[0][1].headers).toEqual({
      'Content-Type': 'application/json',
      'X-MRW-Server-API-Key': 'server-secret',
      Cookie: 'custom_mrw_session=mrw-session',
      'X-Codex-Auth': 'mrw-token',
    });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      threadId: 't1',
      turnId: 'turn1',
      content: 'read',
      admissionId: 'admission-1',
      attachments: [],
    });
    expect(
      readMrwRequestCredentials({ authorization: 'Bearer webui-jwt' }),
    ).toBeUndefined();
    expect(
      readMrwRequestCredentials({
        cookie: 'custom_mrw_session=a; custom_mrw_session=b',
      }),
    ).toBeUndefined();
  });

  it('posts prepare with the server API key and normalized base URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        status: 'ok',
        data: { bindingId: 'b1', environmentDigest: 'd1' },
        error: null,
        meta: { requestId: 'r1' },
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const client = new MrwBackendClient();
    const result = await client.prepare('hk_water_investigation');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend/api/v1/agent-macro-host/prepare',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'X-MRW-Server-API-Key': 'server-secret',
        }),
        body: JSON.stringify({ projectKey: 'hk_water_investigation' }),
      }),
    );
    expect(result).toEqual({ bindingId: 'b1', environmentDigest: 'd1' });
  });

  it('unwraps the data field for the environment GET', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        status: 'ok',
        data: { threadId: 't1', environmentStale: false },
        error: null,
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const client = new MrwBackendClient();
    const result = await client.environment('t1');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend/api/v1/agent-macro-host/environment?threadId=t1',
      expect.objectContaining({ method: 'GET' }),
    );
    expect(result).toEqual({ threadId: 't1', environmentStale: false });
  });

  it('maps a backend conflict to a 409 HttpException', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({
        status: 'error',
        data: null,
        error: { code: 'environment_stale', message: 'environment stale' },
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const client = new MrwBackendClient();
    await expect(client.bind('b1', 't1')).rejects.toMatchObject({
      status: HttpStatus.CONFLICT,
    });
  });

  it('rejects a non-ok envelope even when the HTTP status is 200', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        status: 'error',
        data: null,
        error: { message: 'bad' },
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const client = new MrwBackendClient();
    await expect(
      client.dispatch({
        threadId: 't1',
        turnId: 'turn1',
        callId: 'c1',
        namespace: null,
        tool: 'read',
        arguments: {},
      }),
    ).rejects.toBeInstanceOf(HttpException);
  });

  it('rejects a malformed response body', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ bindingId: 'raw' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const client = new MrwBackendClient();
    await expect(client.prepare('p1')).rejects.toBeInstanceOf(HttpException);
  });

  it('throws service unavailable when the backend URL is not configured', async () => {
    delete process.env.MRW_BACKEND_URL;
    const client = new MrwBackendClient();

    let caught: unknown;
    try {
      await client.prepare('p1');
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(HttpException);
    expect((caught as HttpException).getStatus()).toBe(
      HttpStatus.SERVICE_UNAVAILABLE,
    );
  });
});
