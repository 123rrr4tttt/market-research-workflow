# Codex Settings Export

This directory exports the current local Codex configuration from `~/.codex`.

Included:
- `config.toml`
- `AGENTS.md`
- `agents/*.toml`
- `rules/default.rules`

Excluded for security/privacy:
- `auth.json`
- `history.jsonl`
- `sessions/`
- `state_*.sqlite*`
- `log/`

Exported at local time: 2026-02-27

## Swarm trigger usage

- Sync this directory to `~/.codex/` to make Codex CLI use latest config and `AGENTS.md`.
- In Codex chat, use `蜂群[relative/path/to/file]` or `蜂群【relative/path/to/file】` to trigger the file swarm workflow.
- The workflow bootstrap command is:
  - `bash ./codex_settings/scripts/swarm_file_bootstrap.sh "<file-path>"`
- Batch mode for multiple files:
  - `bash ./codex_settings/scripts/swarm.sh -j 4 -r 1 "<file1>" "<file2>" ...`
  - or `bash ./codex_settings/scripts/swarm.sh -j 4 -r 2 -l codex_settings/swarm_targets.txt`
