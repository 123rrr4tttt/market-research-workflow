from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .social import collect_policy_and_regulation, collect_user_social_sentiment


@dataclass
class SocialIngestApplicationService:
    def collect_social_sentiment(self, **kwargs) -> dict[str, Any]:
        return collect_user_social_sentiment(**kwargs)

    def collect_policy_regulation(self, **kwargs) -> dict[str, Any]:
        return collect_policy_and_regulation(**kwargs)
