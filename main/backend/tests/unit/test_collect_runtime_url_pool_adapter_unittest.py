from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.collect_runtime.adapters.url_pool import UrlPoolAdapter  # noqa: E402
from app.services.collect_runtime.contracts import CollectRequest  # noqa: E402


class CollectRuntimeUrlPoolAdapterUnitTestCase(unittest.TestCase):
    def test_expand_prepares_single_url_children_without_execution(self) -> None:
        request = CollectRequest(
            channel="url_pool",
            project_key="demo_proj",
            urls=["https://example.com/a?utm_source=x"],
            query_terms=["example"],
            options={"url_target_mode": "detail_only"},
        )

        children = UrlPoolAdapter().expand(request)

        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].urls, ["https://example.com/a?utm_source=x"])
        self.assertEqual(children[0].limit, 1)
        self.assertEqual(
            children[0].source_context["url_pool_target"]["entry_type"],
            "detail",
        )
        self.assertEqual(children[0].source_context["url_pool_context"]["mode"], "list")
        self.assertEqual(
            children[0].source_context["url_pool_prepare"]["target_deduped_count"],
            1,
        )

    def test_pool_targets_preserve_target_specific_search_contracts(self) -> None:
        from app.services.ingest.url_pool import _search_options_for_target, prepare_url_pool_targets

        targets = [
            (
                "https://alpha.example/search?q=robotics",
                {
                    "url": "https://alpha.example/search?q={{q}}",
                    "entry_type": "search_template",
                    "source_search_contract": {
                        "param_key": "term",
                        "max_candidates": 2,
                        "min_results_required": 2,
                    },
                },
                {"scope": "effective", "source": "alpha"},
            ),
            (
                "https://beta.example/search?q=robotics",
                {
                    "url": "https://beta.example/search?q={{q}}",
                    "entry_type": "search_template",
                    "source_search_contract": {
                        "param_key": "query",
                        "max_candidates": 5,
                        "min_results_required": 5,
                    },
                },
                {"scope": "effective", "source": "beta"},
            ),
        ]

        with patch(
            "app.services.ingest.url_pool.list_urls",
            return_value=([], 0),
        ), patch(
            "app.services.ingest.url_pool.unwrap_url",
            side_effect=lambda url, **_kwargs: SimpleNamespace(url=url),
        ):
            runtime_targets, diagnostics = prepare_url_pool_targets(
                scope="effective",
                project_key="demo_proj",
                query_terms=["robotics"],
            )

        self.assertEqual(diagnostics["target_deduped_count"], 0)
        for _target_url, target, _pool_item in targets:
            options = _search_options_for_target(
                _target_url,
                ["robotics"],
                target=target,
                extra_params={},
            )
            expected = target["source_search_contract"]
            self.assertEqual(
                {key: options["source_search_contract"][key] for key in expected},
                expected,
            )
            self.assertEqual(options["target_candidates"], expected["max_candidates"])

    def test_high_js_target_forwards_browser_render_boundary(self) -> None:
        from app.services.ingest.url_pool import _frontdoor_route_profile_for_url, prepare_url_list_targets

        with patch(
            "app.services.ingest.url_pool.unwrap_url",
            side_effect=lambda url, **_kwargs: SimpleNamespace(url=url),
        ):
            targets, _diagnostics = prepare_url_list_targets(
                urls=["https://x.com/search?q=robotics"],
                query_terms=["robotics"],
                extra_params={"url_target_mode": "detail_only"},
            )

        self.assertEqual(len(targets), 1)
        target_url, target = targets[0]
        options = _frontdoor_route_profile_for_url(target_url)
        self.assertEqual(target_url, "https://x.com/search?q=robotics")
        self.assertEqual(options["route_hint"], "crawler_browse")
        self.assertEqual(options["fetch_strategy"], "browser_render")
        self.assertTrue(options["render_required"])
        self.assertTrue(options["prefer_crawler"])
        self.assertTrue(options["prefer_search_shell"])
        self.assertEqual(options["router_contract"]["router_state"], "needs_browser")
        self.assertFalse(
            options["router_contract"]["fallback_boundary"]["http_fetch_fallback_allowed"]
        )

    def test_single_url_effect_uses_prepared_kernel(self) -> None:
        kernel_result = {
            "status": "success",
            "inserted": 1,
            "updated": 0,
            "skipped": 0,
            "errors": [],
            "document_id": 91,
        }
        request = CollectRequest(
            channel="url_pool",
            project_key="demo_proj",
            urls=["https://example.com/a"],
            query_terms=["example"],
            options={"enable_extraction": False},
            source_context={
                "url_pool_target": {"url": "https://example.com/a", "entry_type": "detail"},
                "url_pool_context": {"mode": "list", "entry_type": "detail"},
            },
        )

        with patch(
            "app.services.ingest.url_pool.execute_single_url_kernel",
            return_value=kernel_result,
        ) as kernel:
            result = UrlPoolAdapter().run(request)

        kernel.assert_called_once_with(
            url="https://example.com/a",
            project_key="demo_proj",
            query_terms=["example"],
            extra_params={"enable_extraction": False},
            enable_extraction=False,
            target={"url": "https://example.com/a", "entry_type": "detail"},
            context={"mode": "list", "entry_type": "detail"},
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual((result.inserted, result.updated, result.skipped), (1, 0, 0))
        self.assertEqual(result.meta["raw"]["document_id"], 91)
        self.assertFalse(result.errors)

    def test_inline_batch_executes_prepared_children_in_order(self) -> None:
        results = [
            {"status": "success", "inserted": 1, "updated": 0, "skipped": 0},
            {"status": "success", "inserted": 2, "updated": 0, "skipped": 1},
        ]
        calls: list[str] = []

        with patch(
            "app.services.ingest.url_pool.execute_single_url_kernel"
        ) as kernel, patch(
            "app.services.ingest.url_pool.prepare_url_list_targets",
            return_value=(
                (
                    ("https://example.com/a", {"url": "https://example.com/a"}),
                    ("https://example.com/b", {"url": "https://example.com/b"}),
                ),
                {"target_count": 2},
            ),
        ), patch(
            "app.services.ingest.url_pool.prepare_url_pool_targets",
            return_value=(
                (
                    ("https://example.com/a", {"url": "https://example.com/a"}, {}),
                    ("https://example.com/b", {"url": "https://example.com/b"}, {}),
                ),
                {"target_count": 2},
            ),
        ):
            def _kernel(**kwargs):
                calls.append(kwargs["url"])
                return results[(len(calls) - 1) % len(results)]

            kernel.side_effect = _kernel
            multi = UrlPoolAdapter().run(
                CollectRequest(
                    channel="url_pool",
                    project_key="demo_proj",
                    urls=["https://example.com/a", "https://example.com/b"],
                )
            )
            pool = UrlPoolAdapter().run(
                CollectRequest(channel="url_pool", project_key="demo_proj", scope="effective")
            )

        self.assertEqual(kernel.call_count, 4)
        self.assertEqual(calls[:2], ["https://example.com/a", "https://example.com/b"])
        self.assertEqual(calls[2:], ["https://example.com/a", "https://example.com/b"])
        self.assertEqual((multi.inserted, multi.skipped), (3, 1))
        self.assertEqual((pool.inserted, pool.skipped), (3, 1))
        self.assertEqual(multi.meta["raw"]["debug"]["dispatch_mode"], "inline")
        self.assertEqual(pool.meta["raw"]["debug"]["dispatch_mode"], "inline")

    def test_kernel_failure_becomes_typed_collect_failure(self) -> None:
        request = CollectRequest(channel="url_pool", urls=["https://example.com/a"])

        with patch(
            "app.services.ingest.url_pool.execute_single_url_kernel",
            return_value={"status": "failed", "inserted": 0, "skipped": 1, "error": "fetch failed"},
        ):
            result = UrlPoolAdapter().run(request)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.errors[0]["code"], "url_pool_execution_failed")
        self.assertEqual(result.errors[0]["message"], "fetch failed")

    def test_single_url_program_builder_produces_exact_effect_closure(self) -> None:
        from app.successor_runtime.capabilities.acquisition_url import (
            URL_SINGLE_URL_KIND,
            UrlSingleUrlRequest,
            build_url_single_url_program,
        )
        from app.successor_runtime.capabilities.checksum import content_digest, sha256_hex
        from app.successor_runtime.capabilities.source_contracts import project_scope_digest
        from app.successor_runtime.language.algebra import ValueRef
        from app.successor_runtime.language.program import program_atoms
        from app.successor_runtime.research.object_types import ObjectType

        project_key = "demo_proj"
        request = UrlSingleUrlRequest(
            url="https://example.com/a",
            project_key=project_key,
            query_terms=("example",),
        )
        scope_digest = project_scope_digest(project_key, "mrw_demo_proj", 7, "scope-1")
        budget_bytes = b'{"remaining":1}'
        budget_ref = ValueRef(
            value_id="retrieval-budget:root-1",
            project_key=project_key,
            object_type=ObjectType("RetrievalBudgetState.v1", codec_id="retrieval-budget.v1"),
            codec_id="retrieval-budget.v1",
            content_digest=sha256_hex(budget_bytes),
            storage_kind="project_value_ref",
            store_id="successor_values",
            store_version="1",
            storage_ref="project-value:retrieval-budget:root-1",
            byte_size=len(budget_bytes),
            provenance_digest=content_digest({"budget": "root-1"}),
        )
        closure = build_url_single_url_program(
            request=request,
            program_id="program:url-single-1",
            project_key=project_key,
            project_registry_revision=7,
            project_scope_digest=scope_digest,
            incarnation="url-incarnation-1",
            extra_bound_inputs=((budget_ref, budget_bytes),),
        )

        atoms = program_atoms(closure.program.root)
        self.assertEqual(len(atoms), 1)
        self.assertEqual(atoms[0].operation.contract_ref.kind, URL_SINGLE_URL_KIND)
        self.assertEqual(atoms[0].operation.input_refs, (budget_ref, closure.request_ref))
        self.assertEqual(atoms[0].operation.payload_ref, closure.request_ref)
        self.assertEqual(closure.values[0], (budget_ref, budget_bytes))
        self.assertEqual(closure.values[1][0], closure.request_ref)
        self.assertEqual(len(closure.canonical_bindings), 1)

        with pytest.raises(ValueError, match="repeat a value_id"):
            build_url_single_url_program(
                request=request,
                program_id="program:url-single-duplicate",
                project_key=project_key,
                project_registry_revision=7,
                project_scope_digest=scope_digest,
                incarnation="url-incarnation-duplicate",
                extra_bound_inputs=((budget_ref, budget_bytes), (budget_ref, budget_bytes)),
            )

        with pytest.raises(ValueError, match="bytes differ from ValueRef"):
            build_url_single_url_program(
                request=request,
                program_id="program:url-single-byte-drift",
                project_key=project_key,
                project_registry_revision=7,
                project_scope_digest=scope_digest,
                incarnation="url-incarnation-byte-drift",
                extra_bound_inputs=((budget_ref, b'{"remaining":2}'),),
            )

        with pytest.raises(ValueError, match="crosses the program project scope"):
            build_url_single_url_program(
                request=request,
                program_id="program:url-single-2",
                project_key="other_proj",
                project_registry_revision=7,
                project_scope_digest=scope_digest,
                incarnation="url-incarnation-2",
            )

        with pytest.raises(ValueError, match="requires program_id"):
            build_url_single_url_program(
                request=request,
                program_id="",
                project_key=project_key,
                project_registry_revision=7,
                project_scope_digest=scope_digest,
                incarnation="url-incarnation-invalid",
            )
        with pytest.raises(ValueError, match="requires project_key"):
            build_url_single_url_program(
                request=request,
                program_id="program:url-single-invalid-project",
                project_key="",
                project_registry_revision=7,
                project_scope_digest=scope_digest,
                incarnation="url-incarnation-invalid",
            )
        with pytest.raises(ValueError, match="requires incarnation"):
            build_url_single_url_program(
                request=request,
                program_id="program:url-single-invalid-incarnation",
                project_key=project_key,
                project_registry_revision=7,
                project_scope_digest=scope_digest,
                incarnation="",
            )

        with pytest.raises(ValueError, match=r"requires an http\(s\) URL"):
            build_url_single_url_program(
                request=replace(request, url="ftp://example.com/a"),
                program_id="program:url-single-invalid-url",
                project_key=project_key,
                project_registry_revision=7,
                project_scope_digest=scope_digest,
                incarnation="url-incarnation-invalid-url",
            )

        with pytest.raises(ValueError, match="extra bound input crosses"):
            build_url_single_url_program(
                request=request,
                program_id="program:url-single-cross-scope-input",
                project_key=project_key,
                project_registry_revision=7,
                project_scope_digest=scope_digest,
                incarnation="url-incarnation-cross-scope-input",
                extra_bound_inputs=((replace(budget_ref, project_key="other_proj"), budget_bytes),),
            )

        with patch(
            "app.successor_runtime.language.compile.compile_program",
            return_value=SimpleNamespace(ordered_steps=()),
        ), pytest.raises(ValueError, match="must compile to one effect"):
            build_url_single_url_program(
                request=request,
                program_id="program:url-single-no-effect",
                project_key=project_key,
                project_registry_revision=7,
                project_scope_digest=scope_digest,
                incarnation="url-incarnation-no-effect",
            )

    def test_single_url_contract_versions_preserve_legacy_identity(self) -> None:
        from app.successor_runtime.capabilities import acquisition_url as url
        from app.successor_runtime.runtime.assignments import RecoveryBinding

        legacy = url.build_url_single_url_legacy_contract()
        legacy_profiles = url.build_url_single_url_legacy_profiles()
        current = url.build_url_single_url_contract()
        current_profiles = url.build_url_single_url_profiles()
        legacy_recovery = RecoveryBinding.from_content(
            recovery_handler_id=f"{legacy.ref.kind}.readback",
            recovery_handler_version="1",
            interpreter_profile_digest=legacy_profiles.interpreter.profile_digest,
            authoritative_readback_profile_ref=(
                legacy.observation_profile_ref.profile_id
            ),
        )

        self.assertEqual(legacy.ref.contract_version, "1.0.0")
        self.assertEqual(
            legacy.ref.contract_digest,
            "080a25603e9ccb8b3ec42d6e64b06c9451663955b66e1badfd671baa4dc388fd",
        )
        self.assertEqual(
            legacy_profiles.failure.profile_digest,
            "684a900d29c01194cb7e909031e08d96a859d199bbb2fd62a33851241d2063c4",
        )
        self.assertEqual(
            legacy_profiles.interpreter.profile_digest,
            "2f4ab643a5ac0db0c1a3169083d911fe203b535c69124597f0d57111feaa1111",
        )
        self.assertEqual(
            legacy_recovery.binding_digest,
            "39f88ee99336802162c7d822df624909ac1224d883acf0ee2a9b06b7c75d3945",
        )
        self.assertEqual(current.ref.contract_version, "1.1.0")
        self.assertNotEqual(current.ref, legacy.ref)
        self.assertTrue(current_profiles.failure.unknown_outcome_supported)
        self.assertEqual(
            current_profiles.failure.readback_or_compensation,
            "readback",
        )
        self.assertEqual(
            current_profiles.failure.readback_profile_ref,
            url.URL_SINGLE_URL_OBSERVATION_PROFILE,
        )
        self.assertFalse(current_profiles.failure.retryable)
        self.assertEqual(current_profiles.failure.retryable_failure_kinds, ())
        self.assertIsNone(current_profiles.failure.compensation_profile_ref)
        self.assertEqual(
            current_profiles.interpreter.authoritative_readback_profile_ref,
            url.URL_SINGLE_URL_OBSERVATION_PROFILE,
        )
        self.assertEqual(current_profiles.failure.profile_version, "1.1.0")
        self.assertEqual(current_profiles.interpreter.profile_version, "1.1.0")
        self.assertEqual(
            url.build_url_single_url_request_codec(current.ref).codec_version,
            "1",
        )
        self.assertEqual(
            url.build_url_single_url_outcome_codec(current.ref).codec_version,
            "1",
        )
        for family in ("semantic", "effect", "resource", "authority", "observation"):
            self.assertEqual(
                getattr(current_profiles, family).ref,
                getattr(legacy_profiles, family).ref,
            )

    def test_url_single_url_input_validation_preserves_typed_scope_and_capability_failures(
        self,
    ) -> None:
        from app.services.ingest.url_pool import (
            _url_single_url_input_failure,
            validate_url_single_url_input,
        )
        from app.successor_runtime.capabilities.acquisition_url import (
            URL_SINGLE_URL_OWNER,
            UrlSingleUrlRequest,
        )
        from app.successor_runtime.runtime.ports import ProjectScopeRef

        scope = ProjectScopeRef(
            project_key="demo_proj",
            resolved_schema="mrw_demo_proj",
            project_registry_revision=7,
            incarnation="scope-1",
            scope_digest="a" * 64,
        )
        request = UrlSingleUrlRequest(
            url="https://example.com/a",
            project_key="demo_proj",
        )

        self.assertIsNone(
            _url_single_url_input_failure(request, scope, URL_SINGLE_URL_OWNER)
        )
        validate_url_single_url_input(request, scope, URL_SINGLE_URL_OWNER)

        project_failure = _url_single_url_input_failure(
            UrlSingleUrlRequest(
                url="https://example.com/a",
                project_key="other_proj",
            ),
            scope,
            URL_SINGLE_URL_OWNER,
        )
        self.assertIsNotNone(project_failure)
        assert project_failure is not None
        assert project_failure.context is not None
        self.assertEqual(project_failure.family, "ingest.operation.failure")
        self.assertEqual(project_failure.code, "url_pool_collection_failed")
        self.assertEqual(project_failure.context["reason_code"], "project_scope_mismatch")
        with self.assertRaisesRegex(
            ValueError,
            "crosses the installed project scope",
        ):
            validate_url_single_url_input(
                UrlSingleUrlRequest(
                    url="https://example.com/a",
                    project_key="other_proj",
                ),
                scope,
                URL_SINGLE_URL_OWNER,
            )

        capability_failure = _url_single_url_input_failure(
            request,
            scope,
            "acquisition.url.other",
        )
        self.assertIsNotNone(capability_failure)
        assert capability_failure is not None
        assert capability_failure.context is not None
        self.assertEqual(capability_failure.context["reason_code"], "capability_drift")
        with self.assertRaisesRegex(ValueError, "capability drift"):
            validate_url_single_url_input(
                request,
                scope,
                "acquisition.url.other",
            )


if __name__ == "__main__":
    unittest.main()
