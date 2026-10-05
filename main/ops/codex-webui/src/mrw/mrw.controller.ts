import { Body, Controller, Get, HttpException, HttpStatus, Post, Query } from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiTags } from '@nestjs/swagger';
import {
  MrwConfirmRequestDto,
  MrwConfirmResultDto,
  MrwPendingActionDto,
} from './mrw.dto';
import { MrwService } from './mrw.service';

@ApiTags('mrw')
@ApiBearerAuth()
@Controller('mrw')
export class MrwController {
  constructor(private readonly mrw: MrwService) {}

  @Post('confirm')
  @ApiOperation({ summary: 'Confirm or reject a held-back macro host tool call' })
  async confirm(@Body() body: MrwConfirmRequestDto): Promise<MrwConfirmResultDto> {
    return this.mrw.confirmAction(body);
  }

  @Get('pending')
  @ApiOperation({ summary: 'List pending macro host actions for a thread' })
  async pending(@Query('threadId') threadId?: string): Promise<MrwPendingActionDto[]> {
    const normalized = (threadId ?? '').trim();
    if (!normalized) {
      throw new HttpException('threadId is required', HttpStatus.BAD_REQUEST);
    }
    return this.mrw.listPending(normalized);
  }
}
