import { HttpException, HttpStatus, Injectable, Logger } from '@nestjs/common';
import type {
  MrwBindResult,
  MrwConfirmRequest,
  MrwDispatchResult,
  MrwDynamicToolCallParams,
  MrwPreparedEnvironment,
  MrwRequestCredentials,
} from './mrw.types';

const HEADER_API_KEY = 'X-MRW-Server-API-Key';

export function readMrwRequestCredentials(
  headers: Record<string, string | string[] | undefined>,
): MrwRequestCredentials | undefined {
  const cookieName =
    process.env.CODEX_OAUTH_COOKIE_NAME?.trim() || 'codex_session';
  const cookies =
    typeof headers.cookie === 'string' ? headers.cookie.split(';') : [];
  const matches = cookies
    .map((item) => item.trim())
    .filter((item) => item.startsWith(`${cookieName}=`));
  const sessionCookie = matches.length === 1 ? matches[0] : undefined;
  const codexAuth =
    typeof headers['x-codex-auth'] === 'string'
      ? headers['x-codex-auth']
      : undefined;
  return sessionCookie || codexAuth ? { sessionCookie, codexAuth } : undefined;
}

type MrwApiEnvelope = {
  status?: unknown;
  data?: unknown;
  error?: unknown;
  meta?: unknown;
};

/** Server-to-server transport to the MRW backend native macro host API. */
@Injectable()
export class MrwBackendClient {
  private readonly logger = new Logger(MrwBackendClient.name);
  private readonly baseUrl: string;
  private readonly apiKey: string;

  constructor() {
    this.baseUrl = (process.env.MRW_BACKEND_URL ?? '').replace(/\/+$/, '');
    this.apiKey = process.env.MRW_BACKEND_API_KEY ?? '';
  }

  async prepare(projectKey: string): Promise<MrwPreparedEnvironment> {
    return this.post<MrwPreparedEnvironment>('/prepare', { projectKey });
  }

  async bind(bindingId: string, threadId: string): Promise<MrwBindResult> {
    return this.post<MrwBindResult>('/bind', { bindingId, threadId });
  }

  async dispatch(
    params: MrwDynamicToolCallParams,
    credentials?: MrwRequestCredentials,
  ): Promise<MrwDispatchResult> {
    return this.post<MrwDispatchResult>('/dispatch', params, credentials);
  }

  async confirm(req: MrwConfirmRequest): Promise<unknown> {
    return this.post<unknown>('/confirm', req);
  }

  async recordInput(
    threadId: string,
    turnId: string,
    content: string,
    credentials?: MrwRequestCredentials,
  ): Promise<unknown> {
    return this.post<unknown>(
      '/record-input',
      { threadId, turnId, content },
      credentials,
    );
  }

  async endTurn(threadId: string, turnId: string): Promise<unknown> {
    return this.post<unknown>('/end-turn', { threadId, turnId });
  }

  async environment(threadId: string): Promise<MrwPreparedEnvironment> {
    return this.get<MrwPreparedEnvironment>(
      `/environment?threadId=${encodeURIComponent(threadId)}`,
    );
  }

  private async post<T>(
    path: string,
    body: unknown,
    credentials?: MrwRequestCredentials,
  ): Promise<T> {
    const url = this.resolveUrl(path);
    return this.fetchJson<T>(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        [HEADER_API_KEY]: this.apiKey,
        ...(credentials?.sessionCookie
          ? { Cookie: credentials.sessionCookie }
          : {}),
        ...(credentials?.codexAuth
          ? { 'X-Codex-Auth': credentials.codexAuth }
          : {}),
      },
      body: JSON.stringify(body),
    });
  }

  private async get<T>(path: string): Promise<T> {
    const url = this.resolveUrl(path);
    return this.fetchJson<T>(url, {
      method: 'GET',
      headers: { [HEADER_API_KEY]: this.apiKey },
    });
  }

  private async fetchJson<T>(url: string, init: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetch(url, init);
    } catch (error) {
      throw this.unavailable(error);
    }

    const envelope = await this.readEnvelope(response);
    const errorMessage = this.envelopeErrorMessage(envelope);

    if (!response.ok) {
      const message = errorMessage ?? 'MRW backend rejected the request';
      if (response.status === 409) {
        throw new HttpException(message, HttpStatus.CONFLICT);
      }
      if (response.status === 503) {
        throw new HttpException(message, HttpStatus.SERVICE_UNAVAILABLE);
      }
      throw new HttpException(message, response.status);
    }

    if (!envelope || envelope.status !== 'ok' || envelope.data == null) {
      throw new HttpException(
        errorMessage ?? 'MRW backend returned a non-ok envelope',
        HttpStatus.BAD_GATEWAY,
      );
    }
    return envelope.data as T;
  }

  private resolveUrl(path: string): string {
    if (!this.baseUrl) {
      throw new HttpException(
        'MRW backend URL is not configured',
        HttpStatus.SERVICE_UNAVAILABLE,
      );
    }
    if (!this.apiKey) {
      throw new HttpException(
        'MRW backend API key is not configured',
        HttpStatus.SERVICE_UNAVAILABLE,
      );
    }
    return `${this.baseUrl}/api/v1/agent-macro-host${path}`;
  }

  private unavailable(error: unknown): HttpException {
    const message = error instanceof Error ? error.message : String(error);
    this.logger.warn(`MRW backend unreachable: ${message}`);
    return new HttpException(
      'MRW backend unreachable',
      HttpStatus.SERVICE_UNAVAILABLE,
    );
  }

  private async readEnvelope(
    response: Response,
  ): Promise<MrwApiEnvelope | null> {
    try {
      const body = (await response.json()) as MrwApiEnvelope;
      if (!body || typeof body !== 'object') return null;
      return body;
    } catch {
      return null;
    }
  }

  private envelopeErrorMessage(
    envelope: MrwApiEnvelope | null,
  ): string | undefined {
    const error = envelope?.error;
    if (typeof error === 'string') return error;
    if (error && typeof error === 'object') {
      const obj = error as { message?: unknown; detail?: unknown };
      if (typeof obj.message === 'string') return obj.message;
      if (typeof obj.detail === 'string') return obj.detail;
    }
    return undefined;
  }
}
