from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.entities import LlmServiceConfig


class LlmConfigService:
    def list_configs(self, db: Session) -> list[LlmServiceConfig]:
        stmt = select(LlmServiceConfig).order_by(LlmServiceConfig.service_name)
        return db.execute(stmt).scalars().all()

    def get_config(self, db: Session, service_name: str) -> Optional[LlmServiceConfig]:
        stmt = select(LlmServiceConfig).where(LlmServiceConfig.service_name == service_name)
        return db.execute(stmt).scalar_one_or_none()

    def create_config(self, db: Session, payload: dict[str, Any]) -> LlmServiceConfig:
        db_config = LlmServiceConfig(**payload)
        db.add(db_config)
        db.commit()
        db.refresh(db_config)
        return db_config

    def update_config(self, db: Session, config: LlmServiceConfig, payload: dict[str, Any]) -> LlmServiceConfig:
        for key, value in payload.items():
            setattr(config, key, value)
        db.commit()
        db.refresh(config)
        return config

    def delete_config(self, db: Session, config: LlmServiceConfig) -> None:
        db.delete(config)
        db.commit()

    def upsert_config(
        self,
        db: Session,
        service_name: str,
        payload: dict[str, Any],
    ) -> LlmServiceConfig:
        config = self.get_config(db, service_name)
        if config is None:
            payload_with_name = {"service_name": service_name, **payload}
            return self.create_config(db, payload_with_name)
        return self.update_config(db, config, payload)
