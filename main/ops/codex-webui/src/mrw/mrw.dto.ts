import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

export class MrwConfirmRequestDto {
  @ApiProperty()
  threadId!: string;

  @ApiProperty()
  turnId!: string;

  @ApiProperty()
  actionId!: string;

  @ApiProperty()
  approved!: boolean;

  @ApiPropertyOptional()
  userText?: string;
}

export class MrwConfirmResultDto {
  @ApiProperty()
  confirmed!: boolean;

  @ApiProperty()
  actionId!: string;

  @ApiProperty()
  approved!: boolean;

  @ApiProperty()
  threadId!: string;
}

export class MrwPendingActionDto {
  @ApiProperty()
  actionId!: string;

  @ApiProperty()
  threadId!: string;

  @ApiProperty()
  turnId!: string;

  @ApiProperty()
  toolName!: string;

  @ApiProperty()
  projectKey!: string;

  @ApiProperty()
  callId!: string;

  @ApiPropertyOptional()
  actionDigest?: string;

  @ApiPropertyOptional({ type: Object })
  arguments?: Record<string, unknown>;
}
