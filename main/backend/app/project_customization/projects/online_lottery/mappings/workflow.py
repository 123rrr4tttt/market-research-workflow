from __future__ import annotations

from ....interfaces import WorkflowDefinition, WorkflowStep


WORKFLOW_MAPPING: dict[str, WorkflowDefinition] = {
    "collect_lottery_signals": WorkflowDefinition(
        steps=[
            WorkflowStep(
                name="lottery-reddit",
                handler="ingest.reddit",
                params={"subreddit": "Lottery", "limit": 20},
            ),
            WorkflowStep(
                name="lottery-news",
                handler="ingest.google_news",
                params={"keywords": ["lottery regulation", "lottery bill"], "limit": 20},
            ),
        ]
    ),
    "collect_lottery_policy": WorkflowDefinition(
        steps=[
            WorkflowStep(
                name="state-policy",
                handler="ingest.policy",
                params={"state": "CA"},
            )
        ]
    ),
}
