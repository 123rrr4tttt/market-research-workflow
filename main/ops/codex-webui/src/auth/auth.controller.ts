/** REST controller for JWT login/logout flows. */
import {
  Body,
  Controller,
  Get,
  Header,
  HttpCode,
  HttpStatus,
  Post,
  Req,
} from '@nestjs/common';
import { BusinessException } from '../common/business.exception';
import { ErrorCode } from '../common/error-codes';
import {
  ApiBody,
  ApiNoContentResponse,
  ApiOkResponse,
  ApiOperation,
  ApiTags,
  ApiUnauthorizedResponse,
} from '@nestjs/swagger';
import type { FastifyRequest } from 'fastify';
import { ApiErrorResponseDto } from '../common/dto/api-responses.dto';
import { AuthService } from './auth.service';
import { LoginRequestDto, LoginResponseDto } from './dto/auth.dto';
import { Public } from './public.decorator';

function getRequestId(request: FastifyRequest): string | undefined {
  const id = (request as unknown as { id?: unknown }).id;
  return typeof id === 'string' ? id : undefined;
}

function isLoopbackRemoteAddress(address: string | undefined): boolean {
  return (
    address === '127.0.0.1' ||
    address === '::1' ||
    address === '::ffff:127.0.0.1'
  );
}

function hasForwardedHeader(headers: FastifyRequest['headers']): boolean {
  return (
    [
      'x-forwarded-for',
      'x-forwarded-host',
      'x-forwarded-prefix',
      'x-forwarded-proto',
      'forwarded',
    ] as const
  ).some((header) => Object.prototype.hasOwnProperty.call(headers, header));
}

@ApiTags('auth')
@Controller('auth')
export class AuthController {
  constructor(private readonly authService: AuthService) {}

  /** Exchanges the deployment API key for a short-lived JWT. */
  @Public()
  @Post('login')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Login with the WebUI API key' })
  @ApiBody({ type: LoginRequestDto })
  @ApiOkResponse({ type: LoginResponseDto })
  @ApiUnauthorizedResponse({ type: ApiErrorResponseDto })
  async login(
    @Body() body: LoginRequestDto,
    @Req() request: FastifyRequest,
  ): Promise<LoginResponseDto> {
    const requestId = getRequestId(request);
    if (!this.authService.validateApiKey(body.apiKey)) {
      this.authService.logAuthEvent('warn', {
        authType: 'apiKeyLogin',
        reason: 'invalidApiKey',
        requestId,
      });
      throw BusinessException.unauthorized(
        ErrorCode.auth.invalidApiKey,
        'Invalid API key',
      );
    }

    this.authService.logAuthEvent('log', {
      authType: 'apiKeyLogin',
      reason: 'loginSuccess',
      requestId,
    });
    return this.authService.signJwt();
  }

  /** Stateless logout; the browser clears the stored JWT. */
  @Post('logout')
  @HttpCode(HttpStatus.NO_CONTENT)
  @ApiOperation({ summary: 'Logout the current WebUI session' })
  @ApiNoContentResponse()
  logout(): void {}

  /**
   * Issues a JWT server-side for the embedded MRW frontend so the Codex Agent
   * page can auto-login (localhost / single-user deployment). The API key is
   * never sent to the browser.
   */
  @Public()
  @Get('bootstrap')
  @HttpCode(HttpStatus.OK)
  @Header('Cache-Control', 'no-store')
  @ApiOperation({ summary: 'Bootstrap a JWT for the embedded MRW frontend' })
  @ApiOkResponse({ type: LoginResponseDto })
  async bootstrap(@Req() request: FastifyRequest): Promise<LoginResponseDto> {
    const requestId = getRequestId(request);
    const isDirectLoopback = isLoopbackRemoteAddress(
      request.raw.socket.remoteAddress,
    );
    if (!isDirectLoopback || hasForwardedHeader(request.headers)) {
      const token = this.extractBearerToken(request.headers.authorization);
      if (!token) {
        throw BusinessException.unauthorized(
          request.headers.authorization === undefined
            ? ErrorCode.auth.missingHeader
            : ErrorCode.auth.invalidToken,
          request.headers.authorization === undefined
            ? 'Missing or invalid Authorization header'
            : 'Invalid Authorization header',
        );
      }

      const result = await this.authService.authenticateToken(token, requestId);
      if (!result.ok) {
        throw BusinessException.unauthorized(
          ErrorCode.auth.invalidToken,
          'Invalid authentication token',
        );
      }
    }

    this.authService.logAuthEvent('log', {
      authType: 'jwt',
      reason: 'issued',
      requestId,
    });
    return this.authService.signJwt();
  }

  private extractBearerToken(
    authorization: string | string[] | undefined,
  ): string | null {
    const value = Array.isArray(authorization)
      ? authorization[0]
      : authorization;
    if (!value?.startsWith('Bearer ')) return null;
    const token = value.slice(7).trim();
    return token.length > 0 ? token : null;
  }
}
