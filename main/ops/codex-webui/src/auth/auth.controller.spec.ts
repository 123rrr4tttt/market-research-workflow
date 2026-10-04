/** Unit tests for the bootstrap route's real-source authentication boundary. */
import { BusinessException } from '../common/business.exception';
import { ErrorCode } from '../common/error-codes';
import { HttpStatus } from '@nestjs/common';
import { AuthController } from './auth.controller';
import { AuthService } from './auth.service';
import type { FastifyRequest } from 'fastify';

interface RequestOptions {
  remoteAddress?: string;
  authorization?: string;
  headers?: Record<string, string>;
}

function createRequest({
  remoteAddress = '127.0.0.1',
  authorization,
  headers = {},
}: RequestOptions): FastifyRequest {
  return {
    id: 'request-1',
    headers: {
      ...headers,
      ...(authorization === undefined ? {} : { authorization }),
    },
    raw: { socket: { remoteAddress } },
  } as unknown as FastifyRequest;
}

async function expectUnauthorized(
  action: () => Promise<unknown>,
): Promise<BusinessException> {
  let error: unknown;
  try {
    await action();
  } catch (thrown) {
    error = thrown;
  }

  expect(error).toBeInstanceOf(BusinessException);
  const unauthorized = error as BusinessException;
  expect(unauthorized.getStatus()).toBe(HttpStatus.UNAUTHORIZED);
  return unauthorized;
}

describe('AuthController', () => {
  let controller: AuthController;
  let authService: {
    authenticateToken: ReturnType<typeof vi.fn>;
    logAuthEvent: ReturnType<typeof vi.fn>;
    signJwt: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    authService = {
      authenticateToken: vi.fn(),
      logAuthEvent: vi.fn(),
      signJwt: vi.fn().mockResolvedValue({
        accessToken: 'issued-token',
        expiresIn: 86_400,
      }),
    };
    controller = new AuthController(authService as unknown as AuthService);
  });

  describe('bootstrap', () => {
    it.each(['127.0.0.1', '::1', '::ffff:127.0.0.1'])(
      'issues a JWT without credentials for loopback peer %s',
      async (remoteAddress) => {
        const response = await controller.bootstrap(
          createRequest({ remoteAddress }),
        );

        expect(response).toEqual({
          accessToken: 'issued-token',
          expiresIn: 86_400,
        });
        expect(authService.authenticateToken).not.toHaveBeenCalled();
        expect(authService.signJwt).toHaveBeenCalledTimes(1);
      },
    );

    it('authenticates a non-loopback bearer through AuthService', async () => {
      authService.authenticateToken.mockResolvedValue({
        ok: true,
        authType: 'jwt',
      });

      await controller.bootstrap(
        createRequest({
          remoteAddress: '192.0.2.10',
          authorization: 'Bearer valid-token',
        }),
      );

      expect(authService.authenticateToken).toHaveBeenCalledWith(
        'valid-token',
        'request-1',
      );
      expect(authService.signJwt).toHaveBeenCalledTimes(1);
    });

    it('rejects a non-loopback request without credentials', async () => {
      await expect(
        controller.bootstrap(createRequest({ remoteAddress: '192.0.2.10' })),
      ).rejects.toMatchObject({
        errorCode: ErrorCode.auth.missingHeader,
      });

      expect(authService.authenticateToken).not.toHaveBeenCalled();
      expect(authService.signJwt).not.toHaveBeenCalled();
    });

    it('ignores spoofable forwarded and browser metadata', async () => {
      await expect(
        controller.bootstrap(
          createRequest({
            remoteAddress: '192.0.2.10',
            headers: {
              'x-forwarded-for': '127.0.0.1',
              'x-real-ip': '127.0.0.1',
              origin: 'http://localhost:5174',
              'sec-fetch-site': 'same-origin',
            },
          }),
        ),
      ).rejects.toBeInstanceOf(BusinessException);

      expect(authService.authenticateToken).not.toHaveBeenCalled();
      expect(authService.signJwt).not.toHaveBeenCalled();
    });

    it.each([
      ['x-forwarded-prefix', '/codex'],
      ['x-forwarded-for', '127.0.0.1'],
      ['x-forwarded-host', 'localhost:5174'],
      ['x-forwarded-proto', 'http'],
      ['forwarded', 'for=127.0.0.1'],
      ['x-forwarded-prefix', ''],
    ])(
      'rejects an unauthenticated loopback request carrying %s',
      async (header, value) => {
        const error = await expectUnauthorized(() =>
          controller.bootstrap(
            createRequest({
              remoteAddress: '127.0.0.1',
              headers: { [header]: value },
            }),
          ),
        );

        expect(error.errorCode).toBe(ErrorCode.auth.missingHeader);
        expect(authService.authenticateToken).not.toHaveBeenCalled();
        expect(authService.signJwt).not.toHaveBeenCalled();
      },
    );

    it('authenticates a proxied loopback bearer through AuthService', async () => {
      authService.authenticateToken.mockResolvedValue({
        ok: true,
        authType: 'jwt',
      });

      await controller.bootstrap(
        createRequest({
          remoteAddress: '127.0.0.1',
          authorization: 'Bearer valid-token',
          headers: {
            'x-forwarded-prefix': '/codex',
            'x-forwarded-for': '127.0.0.1',
          },
        }),
      );

      expect(authService.authenticateToken).toHaveBeenCalledWith(
        'valid-token',
        'request-1',
      );
      expect(authService.signJwt).toHaveBeenCalledTimes(1);
    });

    it('rejects an invalid non-loopback bearer', async () => {
      authService.authenticateToken.mockResolvedValue({
        ok: false,
        reason: 'invalidToken',
      });

      await expect(
        controller.bootstrap(
          createRequest({
            remoteAddress: '192.0.2.10',
            authorization: 'Bearer invalid-token',
          }),
        ),
      ).rejects.toMatchObject({
        errorCode: ErrorCode.auth.invalidToken,
      });

      expect(authService.signJwt).not.toHaveBeenCalled();
    });

    it('rejects a malformed Authorization header', async () => {
      await expect(
        controller.bootstrap(
          createRequest({
            remoteAddress: '192.0.2.10',
            authorization: 'Basic credentials',
          }),
        ),
      ).rejects.toMatchObject({
        errorCode: ErrorCode.auth.invalidToken,
      });

      expect(authService.authenticateToken).not.toHaveBeenCalled();
      expect(authService.signJwt).not.toHaveBeenCalled();
    });
  });
});
