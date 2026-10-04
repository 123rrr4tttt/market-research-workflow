---
name: keyword-generation
description: Generate social search and subreddit discovery keywords using the existing keyword-generation business contract.
---

# Social keyword generation

## Work

Given a topic and the caller's language, platform, optional base keywords, and output mode, produce search keywords. In combined mode, also produce subreddit discovery keywords. Follow the active `social_keyword_generation` configuration and its project-specific social keyword guidelines. The legacy list mode remains supported and may use `keyword_generation` configuration.

Keep Chinese and English search coverage in bilingual modes. Subreddit terms should be lowercase, use underscores in place of spaces or hyphens, and contain only letters, digits, and underscores.

## Result shape

- Combined mode: `search_keywords` and `subreddit_keywords` lists.
- Legacy mode: a search keyword list.
- Preserve the existing per-mode result limits and existing parser behavior.

## Context and boundaries

Use only the caller's topic, language, platform, base keywords, configured prompt, and project customization guidelines. The existing service owns response parsing, cleaning, fallback selection, and storage of non-empty search terms for the selected platform. Keep the existing no-key and exception fallback behavior.

This content records the business method for a future Core binding. It does not itself establish native skill mounting or execution. The current implementation continues to call `get_chat_model()` and invoke the resulting model once; do not turn the model provider into an Agent loop or add tools.
