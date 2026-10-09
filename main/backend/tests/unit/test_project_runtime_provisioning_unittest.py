"""Pure first-provisioning boundaries; actual PostgreSQL belongs to integration."""

import json
import unittest
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest
from app.composition import production_runtime as runtime
from app.services.request_identity import RequestActorContext, actor_id_from_secret
from app.successor_runtime.capabilities.acquisition_url import build_url_single_url_contract
from app.successor_runtime.capabilities.workflow_native_contribution import build_workflow_runtime_definition
from app.successor_runtime.runtime.authority_grants import (
    AuthorityOperationScope,
    AuthorityResourceCeiling,
    AuthorityResourceLimit,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.runtime.resources import ResourceClass, ResourcePolicySnapshot
from app.successor_runtime.substrate.postgres.authority import (
    AuthorityGrant,
    CapabilityAuthority,
    ProjectScopeRegistryRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import ExactBindingConflict
from app.successor_runtime.substrate.postgres.session import (
    ProjectScopeValidationError,
    compute_scope_digest,
)

from main.backend.scripts import provision_project_runtime as cli

pytestmark = pytest.mark.unit


class ProjectRuntimeProvisioningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scope = ProjectScopeRef("fresh", "mrw_fresh", 1, "install-1", compute_scope_digest("fresh", "mrw_fresh", 1, "install-1"))
        self.admin = RequestActorContext("operator", "cli", True, "os_operator")
        self.installed = build_workflow_runtime_definition().registry
        self.capability = CapabilityAuthority("workflow_graph.run", "on", 1, True, False, "a" * 64, "b" * 64, datetime(2026, 1, 1, tzinfo=UTC), "approval", "rollback")
        self.policy = ResourcePolicySnapshot("fresh", "workflow_graph.run", ResourceClass.CPU_LIGHT, 1, "c" * 64, 2, 2, 2, 2)
        self.acquisition_capability = replace(
            self.capability,
            capability_id="acquisition.url.single_url.v1",
        )
        self.acquisition_policy = replace(
            self.policy,
            capability_id="acquisition.url.single_url.v1",
        )
        self.grant = AuthorityGrant("grant-1", "target", "workflow_graph.run", AuthorityOperationScope.from_content(operation_kinds=("workflow.runtime.join.v1",), project_scope_digest=self.scope.scope_digest), AuthorityResourceCeiling.from_content(limits=(AuthorityResourceLimit(resource_class="CPU_LIGHT", units=1),), max_active=1), None, 1, datetime.now(UTC) + timedelta(days=1))
        self.kwargs = dict(administrator=self.admin, project_scope=self.scope, grant=self.grant, capability=self.capability, resource=self.policy, installed=self.installed)

    def _provision_args(
        self,
        *,
        operation: str = "acquisition.url.single_url.v1",
        incarnation: str = "install-1",
    ) -> cli.ProvisionArguments:
        args = cli.ProvisionArguments()
        args.project_key = "fresh"
        args.incarnation = incarnation
        args.administrator_id = "operator"
        args.target_actor = "target"
        args.target_local_host = False
        args.capability_json = Path("capability.json")
        args.resource_policy_json = [Path("policy.json")]
        args.grant_id = "grant-1"
        args.grant_epoch = 1
        args.expires_at = datetime.now(UTC) + timedelta(days=1)
        args.credential_ref = None
        args.operation = [operation]
        args.resource_limit = [
            AuthorityResourceLimit(resource_class="CPU_LIGHT", units=1)
        ]
        args.max_active = 1
        return args

    def test_declarations_fail_before_scope_or_ddl(self) -> None:
        cases = (
            {"administrator": replace(self.admin, actor_trusted=False)},
            {"grant": replace(self.grant, expires_at=datetime.now(UTC) - timedelta(seconds=1))},
            {"grant": replace(self.grant, grant_epoch=0)},
            {"resource": ()},
            {"resource": (self.policy, self.policy)},
            {"capability": replace(self.capability, capability_id="foreign")},
            {"grant": replace(self.grant, operation_scope_json=AuthorityOperationScope.from_content(operation_kinds=("uninstalled",), project_scope_digest=self.scope.scope_digest))},
            {"grant": replace(self.grant, resource_ceiling_json=AuthorityResourceCeiling.from_content(limits=(AuthorityResourceLimit(resource_class="CPU_LIGHT", units=3),), max_active=1))},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                connection = MagicMock()
                with self.assertRaises((runtime.ProductionRuntimeAuthorityUnavailable, ExactBindingConflict)):
                    runtime.install_project_runtime(connection, **(self.kwargs | changes))
                connection.execute.assert_not_called()
                connection.begin_nested.assert_not_called()

    def test_original_installer_still_resolves_before_resource_validation(self) -> None:
        with patch.object(runtime, "ServerProjectScopeResolver") as resolver:
            resolver.return_value.resolve.side_effect = ExactBindingConflict("stale sentinel")
            with self.assertRaisesRegex(ExactBindingConflict, "stale sentinel"):
                runtime.install_runtime_authority(MagicMock(), **(self.kwargs | {"resource": ()}))
            resolver.return_value.resolve.assert_called_once_with("fresh")
        with patch.object(runtime, "ServerProjectScopeResolver") as resolver:
            with self.assertRaises(runtime.ProductionRuntimeAuthorityUnavailable):
                runtime.install_runtime_authority(MagicMock(), **(self.kwargs | {"grant": replace(self.grant, grant_epoch=0)}))
            resolver.assert_not_called()

    def test_project_preconditions_and_savepoint_error_boundary(self) -> None:
        for project, exists in ((None, True), ({"enabled": False, "schema_name": "mrw_fresh"}, True), ({"enabled": True, "schema_name": "other"}, True), ({"enabled": True, "schema_name": "mrw_fresh"}, False)):
            with self.subTest(project=project, exists=exists):
                connection = MagicMock()
                connection.execute.return_value.mappings.return_value.one_or_none.return_value = project
                with patch.object(runtime, "inspect") as inspector, patch.object(runtime, "ProjectScopeRegistryRepository") as repository:
                    inspector.return_value.has_schema.return_value = exists
                    with self.assertRaises(ExactBindingConflict):
                        runtime.install_project_runtime(connection, **self.kwargs)
                    repository.assert_not_called()
                    self.assertEqual(connection.begin_nested.return_value.__exit__.call_args.args[0], ExactBindingConflict)
                    connection.commit.assert_not_called()
                self.assertIn("FOR UPDATE", str(connection.execute.call_args.args[0]))

    def test_native_tables_and_authority_share_savepoint(self) -> None:
        connection = MagicMock()
        connection.execute.return_value.mappings.return_value.one_or_none.return_value = {"enabled": True, "schema_name": "mrw_fresh"}
        with patch.object(runtime, "inspect") as inspector, patch.object(runtime, "ProjectScopeRegistryRepository") as repository, patch.object(runtime.MetaData, "create_all") as create_all, patch.object(runtime, "install_runtime_authority") as install, patch.object(runtime, "ServerProjectScopeResolver") as resolver:
            inspector.return_value.has_schema.return_value = True
            resolver.return_value.resolve.return_value = self.scope
            self.assertEqual(runtime.install_project_runtime(connection, **self.kwargs), self.scope)
            repository.return_value.create_initial.assert_called_once_with(approval_ref="approval")
            tables = create_all.call_args.kwargs["tables"]
            self.assertEqual(len(tables), 7)
            self.assertTrue(all(table.schema == "mrw_fresh" for table in tables))
            install.assert_called_once_with(connection, **self.kwargs)
            connection.commit.assert_not_called()
            install.side_effect = ExactBindingConflict("authority conflict")
            with self.assertRaisesRegex(ExactBindingConflict, "authority conflict"):
                runtime.install_project_runtime(connection, **self.kwargs)
            self.assertEqual(connection.begin_nested.return_value.__exit__.call_args.args[0], ExactBindingConflict)

    def test_initial_scope_exact_retry_is_read_only_and_history_refused(self) -> None:
        row = dict(project_key="fresh", resolved_schema="mrw_fresh", registry_revision=1, incarnation="install-1", scope_digest=self.scope.scope_digest, state="ACTIVE", updated_by="operator", approval_ref="approval")
        connection = MagicMock()
        repository = ProjectScopeRegistryRepository(connection, RuntimeScope(self.scope, "operator"))
        connection.execute.return_value.mappings.return_value.all.return_value = [row]
        self.assertEqual(repository.create_initial(approval_ref="approval"), self.scope)
        self.assertEqual(connection.execute.call_count, 1)
        for changes in ({"state": "RETIRED"}, {"updated_by": "other"}, {"approval_ref": "other"}, {"registry_revision": 2}):
            with self.subTest(changes=changes):
                connection.execute.return_value.mappings.return_value.all.return_value = [row | changes]
                with self.assertRaises(ExactBindingConflict):
                    repository.create_initial(approval_ref="approval")
        connection.execute.return_value.mappings.return_value.all.return_value = [row, row]
        with self.assertRaises(ExactBindingConflict):
            repository.create_initial(approval_ref="approval")

    def test_cli_native_json_and_explicit_inputs(self) -> None:
        with TemporaryDirectory(prefix="mrw-p-pure-") as directory:
            path = Path(directory) / "capability.json"
            body = asdict(self.capability)
            body["effective_at"] = self.capability.effective_at.isoformat()
            path.write_text(json.dumps(body))
            self.assertEqual(cli._read_declaration(path, CapabilityAuthority), self.capability)
            path.write_text(json.dumps(body | {"unknown": True}))
            with self.assertRaises(ValueError):
                cli._read_declaration(path, CapabilityAuthority)
        with self.assertRaises(SystemExit), patch("sys.stderr"):
            cli.build_parser().parse_args(["--project-key", "fresh"])
        with self.assertRaises(ValueError):
            AuthorityOperationScope.from_content(operation_kinds=("join", "join"), project_scope_digest=self.scope.scope_digest)

    def test_cli_local_host_configuration_refusal_and_secret_projection(self) -> None:
        args = MagicMock(target_local_host=True, target_actor=None)
        with patch.object(cli, "_read_declaration", side_effect=[self.capability, self.policy]), patch.object(cli, "settings") as settings, patch.object(cli, "create_runtime_engine") as engine:
            args.resource_policy_json = [Path("policy")]
            settings.codex_webui_local_single_user_enabled = False
            settings.codex_webui_server_api_key.get_secret_value.return_value = "private-key"
            with self.assertRaisesRegex(ValueError, "enabled single-user"):
                cli.provision(args)
            engine.assert_not_called()
        self.assertTrue(actor_id_from_secret("local_host", "private-key").startswith("local_host:"))
        self.assertNotIn("private-key", actor_id_from_secret("local_host", "private-key"))

    def test_cli_existing_scope_uses_resolved_identity_and_installs_authority_only(self) -> None:
        args = self._provision_args()
        connection = MagicMock()
        connection.execute.return_value.mappings.return_value.first.return_value = {
            "project_key": "fresh"
        }
        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = connection
        with (
            patch.object(
                cli,
                "_read_declaration",
                side_effect=[
                    self.acquisition_capability,
                    self.acquisition_policy,
                    self.acquisition_capability,
                    self.acquisition_policy,
                ],
            ),
            patch.object(cli, "create_runtime_engine", return_value=engine),
            patch.object(cli, "ServerProjectScopeResolver") as resolver,
            patch.object(cli, "install_runtime_authority") as install_authority,
            patch.object(cli, "install_project_runtime") as install_project,
        ):
            resolver.return_value.resolve.return_value = self.scope

            result = cli.provision(args)

            self.assertEqual(result["project_scope"], asdict(self.scope))
            install_project.assert_not_called()
            install_authority.assert_called_once()
            call = install_authority.call_args
            self.assertIs(call.kwargs["project_scope"], self.scope)
            self.assertEqual(
                call.kwargs["grant"].operation_scope_json.project_scope_digest,
                self.scope.scope_digest,
            )
            installed = call.kwargs["installed"]
            ref = installed.catalog.lookup(build_url_single_url_contract().ref)
            self.assertIsNotNone(ref)
            self.assertEqual(
                installed.resolve_required(ref).owner_capability_id,
                "acquisition.url.single_url.v1",
            )

            args.incarnation = "different-install"
            with self.assertRaisesRegex(ExactBindingConflict, "different incarnation"):
                cli.provision(args)

    def test_cli_exact_missing_scope_uses_first_installation(self) -> None:
        args = self._provision_args()
        expected_scope = ProjectScopeRef(
            "fresh",
            "mrw_fresh",
            1,
            "install-1",
            compute_scope_digest("fresh", "mrw_fresh", 1, "install-1"),
        )
        history = MagicMock()
        history.mappings.return_value.first.return_value = None
        project = MagicMock()
        project.mappings.return_value.one_or_none.return_value = {
            "schema_name": "mrw_fresh",
            "enabled": True,
        }
        connection = MagicMock()
        connection.execute.side_effect = [history, project]
        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = connection
        with (
            patch.object(
                cli,
                "_read_declaration",
                side_effect=[self.acquisition_capability, self.acquisition_policy],
            ),
            patch.object(cli, "create_runtime_engine", return_value=engine),
            patch.object(cli, "ServerProjectScopeResolver") as resolver,
            patch.object(cli, "install_runtime_authority") as install_authority,
            patch.object(cli, "install_project_runtime") as install_project,
        ):
            install_project.return_value = expected_scope

            result = cli.provision(args)

            resolver.assert_not_called()
            install_authority.assert_not_called()
            install_project.assert_called_once()
            scope = install_project.call_args.kwargs["project_scope"]
            self.assertEqual(scope.project_registry_revision, 1)
            self.assertEqual(scope.incarnation, "install-1")
            self.assertEqual(
                scope.scope_digest,
                compute_scope_digest("fresh", "mrw_fresh", 1, "install-1"),
            )
            self.assertEqual(result["project_scope"], asdict(scope))

    def test_cli_unknown_operation_is_rejected_before_database_access(self) -> None:
        args = self._provision_args(operation="uninstalled.operation.v1")
        with (
            patch.object(
                cli,
                "_read_declaration",
                side_effect=[self.acquisition_capability, self.acquisition_policy],
            ),
            patch.object(cli, "create_runtime_engine") as engine,
        ):
            with self.assertRaisesRegex(
                ExactBindingConflict,
                "uninstalled operation",
            ):
                cli.provision(args)

            engine.assert_not_called()

    def test_cli_existing_scope_resolver_failures_do_not_fall_back_to_first_install(self) -> None:
        args = self._provision_args()
        failures = (
            ProjectScopeValidationError("retired scope has no ACTIVE row"),
            ExactBindingConflict("scope history conflict"),
            RuntimeError("database unavailable"),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                connection = MagicMock()
                connection.execute.return_value.mappings.return_value.first.return_value = {
                    "project_key": "fresh"
                }
                engine = MagicMock()
                engine.begin.return_value.__enter__.return_value = connection
                with (
                    patch.object(
                        cli,
                        "_read_declaration",
                        side_effect=[self.acquisition_capability, self.acquisition_policy],
                    ),
                    patch.object(cli, "create_runtime_engine", return_value=engine),
                    patch.object(cli, "ServerProjectScopeResolver") as resolver,
                    patch.object(cli, "install_runtime_authority") as install_authority,
                    patch.object(cli, "install_project_runtime") as install_project,
                ):
                    resolver.return_value.resolve.side_effect = failure

                    with self.assertRaises(type(failure)) as caught:
                        cli.provision(args)

                    self.assertIs(caught.exception, failure)
                    install_authority.assert_not_called()
                    install_project.assert_not_called()


if __name__ == "__main__":
    unittest.main()
