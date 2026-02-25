from __future__ import annotations

from ....project_customization import WorkflowDefinition, WorkflowStep


WORKFLOW_MAPPING: dict[str, WorkflowDefinition] = {
    "collect_embodied_signals": WorkflowDefinition(
        steps=[
            WorkflowStep(
                name="reddit-structured-scan",
                handler="ingest.social_sentiment",
                params={
                    "keywords": ["embodied ai", "humanoid robot", "robotics"],
                    "platforms": ["reddit"],
                    "base_subreddits": ["robotics", "MachineLearning", "singularity"],
                    "enable_subreddit_discovery": True,
                    "enable_extraction": True,
                    "limit": 15,
                },
            ),
            WorkflowStep(
                name="google-news-scan",
                handler="ingest.google_news",
                params={"keywords": ["embodied ai", "humanoid robot"], "limit": 10},
            ),
        ]
    ),
}
