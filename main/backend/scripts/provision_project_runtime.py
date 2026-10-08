"""Explicit OS-administrator installation of workflow Runtime in an existing Project."""

from __future__ import annotations

import argparse
from dataclasses import asdict, fields
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Annotated, TypeVar

_ROOT = Path(__file__).resolve().parents[3]
for _path in (_ROOT, _ROOT / "src", _ROOT / "main" / "backend"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from pydantic import TypeAdapter  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.composition.production_runtime import ProductionRuntimeAuthorityUnavailable, install_project_runtime  # noqa: E402
from app.services.request_identity import RequestActorContext, actor_id_from_secret  # noqa: E402
from app.settings.config import settings  # noqa: E402
from app.successor_runtime.capabilities.workflow_native_contribution import build_workflow_runtime_definition  # noqa: E402
from app.successor_runtime.runtime.authority_grants import (  # noqa: E402
    AuthorityOperationScope, AuthorityResourceCeiling, AuthorityResourceLimit,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef  # noqa: E402
from app.successor_runtime.runtime.resources import ResourcePolicySnapshot  # noqa: E402
from app.successor_runtime.substrate.postgres.authority import AuthorityGrant, CapabilityAuthority  # noqa: E402
from app.successor_runtime.substrate.postgres.runtime_journal import ExactBindingConflict  # noqa: E402
from app.successor_runtime.substrate.postgres.session import compute_scope_digest, create_runtime_engine  # noqa: E402

_T = TypeVar("_T", CapabilityAuthority, ResourcePolicySnapshot)


class ProvisionArguments(argparse.Namespace):
    project_key: str
    incarnation: str
    administrator_id: str
    target_actor: str | None
    target_local_host: bool
    capability_json: Path
    resource_policy_json: list[Path]
    grant_id: str
    grant_epoch: int
    expires_at: datetime
    credential_ref: str | None
    operation: list[str]
    resource_limit: list[AuthorityResourceLimit]
    max_active: int


def _read_declaration(path: Path, declaration: type[_T]) -> _T:
    """Read the original typed declaration; reject keys its owner never declared."""
    raw = path.read_text(encoding="utf-8")
    value = TypeAdapter(dict[str, object]).validate_json(raw, strict=True)
    allowed = {field.name for field in fields(declaration)}
    if set(value) - allowed:
        raise ValueError(f"{declaration.__name__} must be an object with only declared fields")
    adapter: TypeAdapter[_T] = TypeAdapter(declaration)
    return adapter.validate_json(raw, strict=True)


def _identity(value: str) -> str:
    if not value or value != value.strip() or len(value) > 128:
        raise argparse.ArgumentTypeError("identity must be non-empty, canonical and at most 128 characters")
    return value


def _resource_limit(value: str) -> AuthorityResourceLimit:
    resource_class, separator, units = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("resource limit must be RESOURCE_CLASS=UNITS")
    try:
        return AuthorityResourceLimit(resource_class=resource_class, units=int(units))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("resource limit requires a class and positive integer units") from exc


def build_parser() -> Annotated[
    argparse.ArgumentParser,
    "kit:non-authoritative derived_as=view "
    "fact_source=provision_project_runtime.explicit_cli_arguments "
    "witness=test:test_cli_native_json_and_explicit_inputs",
]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-key", required=True, type=_identity)
    parser.add_argument("--incarnation", required=True, type=_identity)
    parser.add_argument("--administrator-id", required=True, type=_identity,
                        help="OS deployment operator's audit identity; grants no HTTP/OAuth role")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--target-actor", type=_identity)
    target.add_argument("--target-local-host", action="store_true",
                        help="derive the configured enabled single-user host actor without printing its key")
    parser.add_argument("--capability-json", required=True, type=Path)
    parser.add_argument("--resource-policy-json", required=True, action="append", type=Path,
                        help="repeat for each original ResourcePolicySnapshot; policy_digest is owner-supplied")
    parser.add_argument("--grant-id", required=True, type=_identity)
    parser.add_argument("--grant-epoch", required=True, type=int)
    parser.add_argument("--expires-at", required=True, type=datetime.fromisoformat)
    parser.add_argument("--credential-ref")
    parser.add_argument("--operation", required=True, action="append", type=_identity,
                        help="repeat explicit operations from the installed workflow registry; no default all")
    parser.add_argument("--resource-limit", required=True, action="append", type=_resource_limit)
    parser.add_argument("--max-active", required=True, type=int)
    return parser


def provision(args: ProvisionArguments) -> dict[str, object]:
    capability = _read_declaration(args.capability_json, CapabilityAuthority)
    resources = tuple(_read_declaration(path, ResourcePolicySnapshot) for path in args.resource_policy_json)
    target_actor = args.target_actor
    if args.target_local_host:
        key = settings.codex_webui_server_api_key.get_secret_value().strip()
        if not settings.codex_webui_local_single_user_enabled or not key:
            raise ValueError("local host requires enabled single-user configuration and a server key")
        target_actor = actor_id_from_secret("local_host", key)
    if target_actor is None:
        raise ValueError("an explicit target actor is required")
    administrator = RequestActorContext(
        actor_id=args.administrator_id, actor_source="local_deployment_cli",
        actor_trusted=True, actor_auth_mode="os_operator",
    )
    installed = build_workflow_runtime_definition().registry
    ceiling = AuthorityResourceCeiling.from_content(limits=tuple(args.resource_limit), max_active=args.max_active)
    engine = create_runtime_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            schema = connection.execute(text(
                "SELECT schema_name FROM public.projects WHERE project_key = :project_key"
            ), {"project_key": args.project_key}).scalar_one_or_none()
            if not isinstance(schema, str):
                raise ValueError("first installation requires an existing business Project")
            candidate = ProjectScopeRef(
                project_key=args.project_key, resolved_schema=schema, project_registry_revision=1,
                incarnation=args.incarnation,
                scope_digest=compute_scope_digest(args.project_key, schema, 1, args.incarnation),
            )
            grant = AuthorityGrant(
                grant_id=args.grant_id, actor_id=target_actor, capability_id=capability.capability_id,
                operation_scope_json=AuthorityOperationScope.from_content(
                    operation_kinds=tuple(args.operation), project_scope_digest=candidate.scope_digest,
                ), resource_ceiling_json=ceiling, credential_ref=args.credential_ref,
                grant_epoch=args.grant_epoch, expires_at=args.expires_at,
            )
            scope = install_project_runtime(
                connection, administrator=administrator, project_scope=candidate, grant=grant,
                capability=capability, resource=resources, installed=installed,
            )
        return {"project_scope": asdict(scope), "grant_id": grant.grant_id, "actor_id": grant.actor_id}
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv, namespace=ProvisionArguments())
    try:
        result = provision(args)
    except (ValueError, ProductionRuntimeAuthorityUnavailable, ExactBindingConflict) as exc:
        parser.exit(2, f"Runtime provisioning refused: {exc}\n")
    except Exception as exc:
        # Database exceptions may contain connection details; never print them.
        parser.exit(2, f"Runtime provisioning refused ({type(exc).__name__}).\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
