"""Candidate-source execution planning for unified search.

Inspired by publisher source inventories in fundus and route registries in RSSHub:
we make the per-entry execution path explicit instead of scattering chain metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CandidateSourceStep:
    code: str
    enabled: bool = True
    reason: str | None = None


@dataclass(frozen=True)
class CandidateSourcePlan:
    entry_type: str
    policy_category: str
    steps: tuple[CandidateSourceStep, ...]

    @property
    def service_chain(self) -> list[str]:
        return [step.code for step in self.steps if step.enabled]


def build_candidate_source_plan(
    *,
    entry_type: str,
    policy_category: str,
    allow_deprioritized: bool,
    external_search_enabled: bool,
) -> CandidateSourcePlan:
    etype = str(entry_type or "").strip().lower()
    policy = str(policy_category or "").strip().lower()
    if policy == "api_preferred":
        return CandidateSourcePlan(
            entry_type=etype,
            policy_category=policy,
            steps=(CandidateSourceStep("official_api"),),
        )
    if policy == "social_skip":
        return CandidateSourcePlan(
            entry_type=etype,
            policy_category=policy,
            steps=(CandidateSourceStep("platform_api"),),
        )
    if etype == "rss":
        return CandidateSourcePlan(
            entry_type=etype,
            policy_category=policy,
            steps=(CandidateSourceStep("feed_native"),),
        )
    if etype == "sitemap":
        return CandidateSourcePlan(
            entry_type=etype,
            policy_category=policy,
            steps=(CandidateSourceStep("sitemap_native"),),
        )
    if policy == "deprioritized" and not allow_deprioritized:
        return CandidateSourcePlan(
            entry_type=etype,
            policy_category=policy,
            steps=(CandidateSourceStep("skip", reason="deprioritized_policy"),),
        )
    if policy == "deprioritized":
        return CandidateSourcePlan(
            entry_type=etype,
            policy_category=policy,
            steps=(
                CandidateSourceStep("search_template_resilient"),
                CandidateSourceStep("external_search", enabled=external_search_enabled),
                CandidateSourceStep("browser_candidate_deferred"),
            ),
        )
    return CandidateSourcePlan(
        entry_type=etype,
        policy_category=policy or "keep",
        steps=(
            CandidateSourceStep("search_template"),
            CandidateSourceStep("external_search", enabled=external_search_enabled),
            CandidateSourceStep("external_search_slowlane", enabled=external_search_enabled),
            CandidateSourceStep("browser_candidate_deferred"),
        ),
    )


def plan_to_metadata(plan: CandidateSourcePlan) -> dict[str, Any]:
    return {
        "entry_type": plan.entry_type,
        "policy_category": plan.policy_category,
        "service_chain": plan.service_chain,
        "steps": [
            {"code": step.code, "enabled": step.enabled, "reason": step.reason}
            for step in plan.steps
        ],
    }
