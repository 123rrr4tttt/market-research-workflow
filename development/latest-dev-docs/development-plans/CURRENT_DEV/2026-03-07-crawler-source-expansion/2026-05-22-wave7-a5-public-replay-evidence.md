# Wave7-3 A5 Public Replay Evidence

Date: 2026-05-22
Branch: `codex/devdocs-wave7-crawler-public-replay`
Scope: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-crawler-source-expansion/`

## A5 Gate Decision

A5 is sealed for deterministic replay governance, but it is not upgraded to full public-source closure in this lane.

The closed part is internal and repeatable: the historical `demo_proj` 45-site `handler.cluster.search_template` set is frozen as a manifest, the default replay gate is no-network and deterministic, and term-fallback candidates are preserved as review blockers instead of being counted as clean source closure.

The remaining blocker is external: a full 45-site public replay cannot be required as stable CI evidence because public-site availability, anti-bot controls, rate limits, and parser volatility are outside this repository's deterministic boundary. Shared navigation indexes are intentionally untouched.

## Evidence Inputs

- [source_library_replay_scaleout.py](../../../../../main/backend/scripts/source_library_replay_scaleout.py): embedded 45-site manifest, skip-safe default replay, opt-in public replay, and term-fallback review extraction.
- [source_library_public_live_probes.py](../../../../../main/backend/scripts/source_library_public_live_probes.py): public live fixture classifier for candidate-ready, transport, parser/source, and relevance-review states.
- [check_source_library_public_replay_a5_gate.py](../../../../../main/backend/scripts/check_source_library_public_replay_a5_gate.py): deterministic A5 checker that replays the no-network gate and validates stored 2026-05-22 artifacts.
- [test_source_library_public_replay_a5_gate_unittest.py](../../../../../main/backend/tests/unit/test_source_library_public_replay_a5_gate_unittest.py): fixture test for manifest counts, public-live relevance review, and external blocker recording.
- [source-library-replay-scaleout/2026-05-22](../../../automation-runs/source-library-replay-scaleout/2026-05-22/README.md): stored full-manifest dry-run artifact.
- [source-library-live-probes/2026-05-22](../../../automation-runs/source-library-live-probes/2026-05-22/README.md): stored four-target public-live fixture.

## Deterministic Gate

The deterministic gate validates the full historical manifest without contacting public sites:

| Check | Expected |
| --- | --- |
| Historical targets | `45` |
| Enabled public replay targets | `40` |
| Policy-disabled platform/API targets | `5` |
| Default status count | `skipped_public_network_disabled=45` |
| Default public targets attempted | `0` |

Command:

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 scripts/check_source_library_public_replay_a5_gate.py \
  --output ../../development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/a5-gate-output.json
```

The checker treats the absence of `development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/output.public.json` as an external blocker when the deterministic manifest and fixture gates pass. It does not perform public network access.

## Public Fixture Review

The 2026-05-22 public live fixture remains useful as evidence that the adapter can reach and parse selected public targets, but it does not close the full 45-site replay.

| Target | Fixture status | Closure treatment |
| --- | --- | --- |
| `commercialobserver_parser_weak` | `candidate_ready_with_term_fallback` | `relevance_review` |
| `pymnts_parser_weak` | `candidate_ready` | candidate-ready fixture evidence |
| `investopedia_validated_query` | `candidate_ready` | candidate-ready fixture evidence |
| `hai_stanford_mixed_shell` | `candidate_ready_with_term_fallback` | `relevance_review` |

Term-fallback rows prove public reachability and parser extraction, but the selected candidates must be inspected for relevance before they count as dirty-source closure. This preserves the distinction between adapter/runtime health and source-quality confidence.

## External Blocker

| Blocker | Status | Required future action |
| --- | --- | --- |
| Full opt-in 45-site public replay | `external_public_network_or_site_stability` | Run the opt-in replay in a controlled network window and store `output.public.json` plus `logs/replay.public.log`. |
| Platform/API-required entries | `policy_or_platform_required` | Keep `x.com`, `linkedin.com`, `reddit.com`, and `youtube.com` style entries policy-skipped unless a platform-specific lane exists. |
| Term-fallback public candidates | `relevance_review` | Review candidate relevance before counting as clean directed-source onboarding evidence. |

Opt-in command for the future public window:

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 scripts/source_library_replay_scaleout.py \
  --manifest ../../development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/input.json \
  --output ../../development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/output.public.json \
  --log-output ../../development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/logs/replay.public.log \
  --probe-timeout 6 \
  --allow-public-network
```

## Validation

Focused fixture gate:

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  tests/unit/test_source_library_replay_scaleout_unittest.py \
  tests/unit/test_source_library_public_live_probe_gate_unittest.py \
  tests/unit/test_source_library_public_replay_a5_gate_unittest.py
```

Topic closure checker:

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 scripts/check_crawler_source_expansion_closure.py
```

Expected status after this lane: A5 is `blocked_external`, while overall crawler source expansion remains `not_closed` because A4 and A6 still have separate source-policy and handoff gaps.
