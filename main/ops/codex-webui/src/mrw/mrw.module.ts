import { Module } from '@nestjs/common';
import { CodexModule } from '../codex/codex.module';
import { MrwActionRegistryService } from './mrw-action-registry.service';
import { MrwBackendClient } from './mrw-backend.client';
import { MrwController } from './mrw.controller';
import { MrwEventBus } from './mrw-event-bus';
import { MrwService } from './mrw.service';

@Module({
  imports: [CodexModule],
  controllers: [MrwController],
  providers: [MrwBackendClient, MrwActionRegistryService, MrwEventBus, MrwService],
  exports: [MrwService, MrwActionRegistryService, MrwEventBus],
})
export class MrwModule {}
