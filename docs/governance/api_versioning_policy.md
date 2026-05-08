# API Versioning Policy

## Compatibility window

- Public API changes must keep a documented compatibility window before removal.
- Breaking changes require a replacement path and a rollback option during the window.

## Deprecation policy

- Deprecations must be announced before behavior is removed.
- Deprecated fields or endpoints should return stable envelopes until the window ends.
- Removals must be recorded in release notes and migration guidance.

## Migration announcement template

Use this template when a breaking or behavior-changing API update is planned:

1. Scope of the change
2. Compatibility window and target removal date
3. Migration steps for callers
4. Rollback or kill switch plan
5. Owners and escalation contacts
