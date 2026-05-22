# CURRENT_DEV Status Evidence Gate

- status: `PASS`
- index: [development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md](../../../development-plans/CURRENT_DEV/INDEX.md)
- gate script: [../../../../../scripts/check_current_dev_status_evidence.py](../../../../../scripts/check_current_dev_status_evidence.py)
- scope: repeatable status/evidence checks only; this run does not close or archive individual topics.

## Summary

| Check | Value |
|---|---:|
| active entries | 36 |
| Markdown links checked | 68 |
| placeholder entries recognized | 1 |
| empty directories recognized | 0 |
| Wave5/Wave6 evidence rows checked | 10 |
| problems | 0 |

## Count Gate

| Status | Expected | Parsed |
|---|---:|---:|
| `partial` | 30 | 30 |
| `not_closed` | 3 | 3 |
| `no_closure_claim` | 3 | 3 |

## Coverage Gate

| Coverage source | Rows |
|---|---:|
| matching primary status tag | 36 |
| additional evidence link | 16 |
| explicit blocker/gap text | 9 |
| placeholder row | 1 |

A row passes when it has a matching primary status tag, an evidence link, or explicit blocker/gap text.

## Wave Evidence Gate

| Line | Tag | Wave evidence links |
|---:|---|---:|
| 47 | `wave6_verified` | 1 |
| 66 | `wave6_verified` | 1 |
| 67 | `wave6_verified` | 1 |
| 68 | `wave6_verified` | 1 |
| 69 | `wave6_verified` | 1 |
| 70 | `wave6_verified` | 1 |
| 73 | `wave5_verified` | 2 |
| 78 | `wave6_checked` | 1 |
| 79 | `wave6_checked` | 1 |
| 80 | `wave6_checked` | 1 |
