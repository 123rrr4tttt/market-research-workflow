#!/usr/bin/env python3
"""Fail-closed static production-contract preflight."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.formal_release.model import Finding, PreflightReport


CHECKER = "static-production-contract"
COMPOSE_PATH = Path("main/ops/docker-compose.production.yml")
ENV_PATH = Path("main/backend/.env.production.example")
FRONTEND_PATH = Path("main/frontend-modern/package.json")
PYPROJECT_PATH = Path("pyproject.toml")
BRANCH_PROTECTION_PATH = Path(".github/branch-protection-required-checks.json")
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
REQUIRED_PRODUCTION_SERVICES = ("db", "es", "redis", "backend", "celery-worker", "frontend")
REQUIRED_PRODUCTION_POLICY_SERVICES = ("backend", "celery-worker")
REQUIRED_PRODUCTION_POLICY_ENV = (
    "DATABASE_URL",
    "ES_URL",
    "REDIS_URL",
    "RELEASE_BUILD_COMMIT",
    "RELEASE_BUILD_TREE",
    "RELEASE_BUILD_DIGEST",
    "RUN_MIGRATIONS",
)
ALLOWED_STEP_CONDITIONS = frozenset({"failure()", "always()"})
SUPPORT_STEP_MARKERS = ("cleanup", "diagnostic", "teardown")
REQUIRED_CHECK_CATEGORIES = (
    "formal-release",
    "backend-unit",
    "backend-integration",
    "frontend-lint",
    "frontend-typecheck",
    "frontend-build",
    "frontend-component-e2e",
    "migration",
    "security",
    "docker-config",
    "evidence",
    "artifact-metadata",
    "image-vulnerability-scan",
)
EXACT_REQUIRED_CHECK_NAMES = {
    "frontend-component-e2e": "frontend-component-e2e-check",
    "image-vulnerability-scan": "image-vulnerability-scan-check",
}
ARTIFACT_ROLES = ("backend", "frontend", "migration-runner")
ARTIFACT_BUILD_CONTRACTS = {
    "backend": {
        "contexts": frozenset({".", "./"}),
        "files": frozenset({"main/backend/Dockerfile", "./main/backend/Dockerfile"}),
        "targets": frozenset({"backend-runtime"}),
    },
    "frontend": {
        "contexts": frozenset({"main/frontend-modern", "./main/frontend-modern"}),
        "files": frozenset(
            {
                "Dockerfile",
                "./Dockerfile",
                "main/frontend-modern/Dockerfile",
                "./main/frontend-modern/Dockerfile",
            }
        ),
        "targets": frozenset({"frontend-runtime"}),
    },
    "migration-runner": {
        "contexts": frozenset({".", "./"}),
        "files": frozenset({"main/backend/Dockerfile", "./main/backend/Dockerfile"}),
        "targets": frozenset({"migration-runner"}),
    },
}
PRODUCTION_IMAGE_PATTERN = re.compile(r"^\$\{[A-Z][A-Z0-9_]*:\?required production sha256 digest\}$")
PRODUCTION_REQUIRED_VALUE_PATTERN = re.compile(r"^\$\{[A-Z][A-Z0-9_]*:\?required [^}]+\}$")
DEFAULT_POSTGRES_URL = re.compile(r"postgres(?:ql)?(?:\+[a-z0-9]+)?://postgres:postgres(?:@|/)", re.IGNORECASE)


class StrictParseError(RuntimeError):
    """Raised when input uses syntax outside the accepted structured subset."""


@dataclass(frozen=True, slots=True)
class ParseLine:
    indent: int
    text: str


@dataclass(frozen=True, slots=True)
class CheckContract:
    required_check: str
    source: str


@dataclass(frozen=True, slots=True)
class ContractInputs:
    compose: Any = None
    compose_error: str | None = "not_loaded"
    env: tuple[tuple[str, str], ...] | None = None
    env_error: str | None = "not_loaded"
    branch_protection: Any = None
    branch_protection_error: str | None = "not_loaded"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args(argv)


def resolve_root(root: Path | None) -> Path:
    return (root if root is not None else Path(__file__).resolve().parents[2]).resolve()


def relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def read_text(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except FileNotFoundError:
        return None, "missing_file"
    except UnicodeError:
        return None, "invalid_utf8"
    except OSError as exc:
        return None, f"read_error:{exc}"


def read_json(path: Path) -> tuple[Any, str | None]:
    text, error = read_text(path)
    if error is not None:
        return None, error
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"invalid_json:{exc}"


def read_toml(path: Path) -> tuple[Any, str | None]:
    text, error = read_text(path)
    if error is not None:
        return None, error
    try:
        return tomllib.loads(text), None
    except tomllib.TOMLDecodeError as exc:
        return None, f"invalid_toml:{exc}"


def _strip_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if quote is not None:
            if escaped:
                escaped = False
            elif quote == '"' and char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
            continue
        if char == "#" and (index == 0 or line[index - 1] in {" ", "\t"}):
            return line[:index]
    return line


def _scalar(text: str) -> Any:
    value = text.strip()
    if not value or value in {"~", "null", "Null", "NULL"}:
        return None
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise StrictParseError(f"invalid_double_quoted_scalar:{exc.msg}") from exc
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    if value.startswith("["):
        return _flow_collection(value, "]", "list")
    if value.startswith("{"):
        return _flow_collection(value, "}", "dict")
    if value in {"true", "True", "TRUE"}:
        return True
    if value in {"false", "False", "FALSE"}:
        return False
    if re.fullmatch(r"[+-]?\d+", value):
        return int(value)
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?", value):
        return float(value)
    if value.startswith(("&", "*", "!!")):
        raise StrictParseError(f"unsupported_yaml_scalar:{value[:24]}")
    return value


def _split_flow(text: str, terminator: str) -> list[str]:
    if not text.endswith(terminator):
        raise StrictParseError("unterminated_flow_collection")
    body = text[:-1]
    items: list[str] = []
    start = 0
    quote: str | None = None
    depth = 0
    escaped = False
    for index, char in enumerate(body):
        if quote is not None:
            if escaped:
                escaped = False
            elif quote == '"' and char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(body[start:index])
            start = index + 1
    if quote is not None or depth != 0:
        raise StrictParseError("unbalanced_flow_collection")
    items.append(body[start:])
    if any(not item.strip() for item in items):
        raise StrictParseError("empty_flow_collection_item")
    return items


def _flow_collection(text: str, terminator: str, kind: str) -> Any:
    if text.strip() == ("[]" if terminator == "]" else "{}"):
        return [] if kind == "list" else {}
    values: list[Any] = []
    mapping: dict[str, Any] = {}
    for item in _split_flow(text.strip(), terminator):
        separator = _key_separator(item)
        if kind == "dict":
            if separator is None:
                raise StrictParseError("flow_map_without_key")
            key, raw_value = separator
            mapping[str(_scalar(key))] = _scalar(raw_value)
        elif separator is not None:
            raise StrictParseError("flow_list_contains_map")
        else:
            values.append(_scalar(item))
    return mapping if kind == "dict" else values


def _key_separator(text: str) -> tuple[str, str] | None:
    quote: str | None = None
    escaped = False
    depth = 0
    for index, char in enumerate(text):
        if quote is not None:
            if escaped:
                escaped = False
            elif quote == '"' and char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == ":" and depth == 0 and (index + 1 == len(text) or text[index + 1] in {" ", "\t"}):
            return text[:index], text[index + 1 :]
    return None


class StrictYamlParser:
    """Parse the explicit YAML subset allowed by this production contract."""

    def __init__(self, text: str):
        if text.startswith("---"):
            text = text[3:]
        if "\n---" in text or text.lstrip().startswith("..."):
            raise StrictParseError("multiple_yaml_documents_unsupported")
        self.lines: list[ParseLine] = []
        for raw in text.splitlines():
            if not raw.strip():
                continue
            indentation = len(raw) - len(raw.lstrip(" "))
            if raw.startswith(" " * indentation + "\t") or raw.startswith("\t"):
                raise StrictParseError("tab_indentation_unsupported")
            content = _strip_comment(raw).strip()
            if not content:
                continue
            self.lines.append(ParseLine(indentation, content))

    def parse(self) -> Any:
        if not self.lines:
            return None
        value, index = self._block(0, self.lines[0].indent)
        if index != len(self.lines):
            raise StrictParseError("yaml_indentation_boundary")
        return value

    def _block(self, index: int, indent: int) -> tuple[Any, int]:
        if index >= len(self.lines) or self.lines[index].indent != indent:
            raise StrictParseError("yaml_block_indent")
        if self.lines[index].text.startswith("- ") or self.lines[index].text == "-":
            return self._sequence(index, indent)
        return self._mapping(index, indent)

    def _sequence(self, index: int, indent: int) -> tuple[list[Any], int]:
        items: list[Any] = []
        while index < len(self.lines) and self.lines[index].indent == indent:
            line = self.lines[index]
            if not (line.text == "-" or line.text.startswith("- ")):
                raise StrictParseError("mixed_mapping_and_sequence")
            if line.text == "-":
                index += 1
                if index >= len(self.lines) or self.lines[index].indent <= indent:
                    raise StrictParseError("empty_yaml_sequence_item")
                value, index = self._block(index, self.lines[index].indent)
                items.append(value)
                continue
            child_indent = indent + 2
            item_start = index
            original = self.lines[index]
            remainder = line.text[2:].strip()
            if _key_separator(remainder) is None:
                items.append(_scalar(remainder))
                index += 1
                continue
            self.lines[index] = ParseLine(child_indent, remainder)
            value, index = self._block(index, child_indent)
            self.lines[item_start] = original
            items.append(value)
        return items, index

    def _mapping(self, index: int, indent: int) -> tuple[dict[str, Any], int]:
        mapping: dict[str, Any] = {}
        while index < len(self.lines) and self.lines[index].indent == indent:
            line = self.lines[index]
            if line.text.startswith("- ") or line.text == "-":
                break
            separator = _key_separator(line.text)
            if separator is None:
                raise StrictParseError(f"yaml_mapping_key_missing:{line.text[:32]}")
            raw_key, raw_value = separator
            key = str(_scalar(raw_key))
            if key in mapping:
                raise StrictParseError(f"duplicate_yaml_key:{key}")
            index += 1
            value_text = raw_value.strip()
            if value_text in {"|", "|-", "|+", ">", ">-", ">+"}:
                value, index = self._literal_scalar(index, indent, value_text)
            elif value_text:
                value = _scalar(value_text)
            elif index < len(self.lines) and self.lines[index].indent > indent:
                value, index = self._block(index, self.lines[index].indent)
            else:
                value = None
            mapping[key] = value
        return mapping, index

    def _literal_scalar(self, index: int, parent_indent: int, style: str) -> tuple[str, int]:
        body: list[str] = []
        while index < len(self.lines) and self.lines[index].indent > parent_indent:
            body.append(" " * (self.lines[index].indent - parent_indent - 2) + self.lines[index].text)
            index += 1
        if not body:
            raise StrictParseError("empty_yaml_block_scalar")
        if style.startswith(">"):
            return " ".join(part for line in body for part in line.split()), index
        return "\n".join(body) + "\n", index


def parse_yaml(path: Path) -> tuple[Any, str | None]:
    text, error = read_text(path)
    if error is not None:
        return None, error
    try:
        return StrictYamlParser(text).parse(), None
    except StrictParseError as exc:
        return None, f"unsupported_or_invalid_yaml:{exc}"


def read_env_file(path: Path) -> tuple[tuple[tuple[str, str], ...] | None, str | None]:
    text, error = read_text(path)
    if error is not None:
        return None, error
    pairs: list[tuple[str, str]] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            return None, f"line_{line_number}:missing_key_value_separator"
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            return None, f"line_{line_number}:invalid_env_key"
        pairs.append((key, value.strip().strip("'\"")))
    return tuple(pairs), None


def load_inputs(root: Path) -> ContractInputs:
    compose, compose_error = parse_yaml(root / COMPOSE_PATH)
    env, env_error = read_env_file(root / ENV_PATH)
    branch, branch_error = read_json(root / BRANCH_PROTECTION_PATH)
    return ContractInputs(
        compose=compose,
        compose_error=compose_error,
        env=env,
        env_error=env_error,
        branch_protection=branch,
        branch_protection_error=branch_error,
    )


def blocked(check_id: str, summary: str, evidence: Sequence[str]) -> Finding:
    return Finding(check_id=check_id, status="BLOCKED", summary=summary, evidence=tuple(evidence))


def pass_finding(check_id: str, summary: str, evidence: Sequence[str]) -> Finding:
    return Finding(check_id=check_id, status="PASS", summary=summary, evidence=tuple(evidence))


def fail_finding(check_id: str, summary: str, evidence: Sequence[str]) -> Finding:
    return Finding(check_id=check_id, status="FAIL", summary=summary, evidence=tuple(evidence))


def as_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StrictParseError(f"{label}_not_object")
    if any(not isinstance(key, str) for key in value):
        raise StrictParseError(f"{label}_key_not_string")
    return value


def production_services(compose: Any) -> dict[str, dict[str, Any]]:
    root = as_mapping(compose, "compose_root")
    services = as_mapping(root.get("services"), "compose_services")
    if not services:
        raise StrictParseError("compose_services_empty")
    selected: dict[str, dict[str, Any]] = {}
    for name, value in services.items():
        service = as_mapping(value, f"service:{name}")
        profiles = service.get("profiles")
        if profiles is not None and profiles != ["production"]:
            raise StrictParseError(f"service_profiles_invalid:{name}")
        if profiles is None:
            selected[name] = service
    missing = [name for name in REQUIRED_PRODUCTION_SERVICES if name not in selected]
    if missing:
        raise StrictParseError("production_services_missing:" + ",".join(missing))
    return selected


def service_environment(service: dict[str, Any], service_name: str) -> dict[str, str]:
    value = service.get("environment")
    if value is None:
        return {}
    if isinstance(value, dict):
        result: dict[str, str] = {}
        for key, raw in value.items():
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", key):
                raise StrictParseError(f"invalid_environment_key:{service_name}")
            if raw is None:
                result[key] = ""
            elif isinstance(raw, (str, int, float, bool)):
                result[key] = str(raw)
            else:
                raise StrictParseError(f"invalid_environment_value:{service_name}:{key}")
        return result
    if not isinstance(value, list):
        raise StrictParseError(f"invalid_environment_type:{service_name}")
    result = {}
    for item in value:
        if not isinstance(item, str) or "=" not in item:
            raise StrictParseError(f"invalid_environment_entry:{service_name}")
        key, item_value = item.split("=", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", key):
            raise StrictParseError(f"invalid_environment_key:{service_name}")
        result[key] = item_value
    return result


def image_digest_contract(image: Any) -> str:
    if not isinstance(image, str):
        return "invalid"
    if PRODUCTION_IMAGE_PATTERN.fullmatch(image) is None:
        return "invalid"
    return "required_reference"


def production_image_digest_states(inputs: ContractInputs) -> tuple[dict[str, str], str | None]:
    try:
        services = production_services(inputs.compose)
    except StrictParseError as exc:
        return {}, str(exc)
    return {name: image_digest_contract(service.get("image")) for name, service in sorted(services.items())}, None


def check_production_profile(inputs: ContractInputs) -> Finding:
    if inputs.compose_error is not None:
        return blocked(
            "compose.production_profile",
            "compose production profile could not be parsed",
            (f"{COMPOSE_PATH.as_posix()}:{inputs.compose_error}",),
        )
    try:
        services = production_services(inputs.compose)
    except StrictParseError as exc:
        return blocked(
            "compose.production_profile",
            "compose production profile is not resolvable",
            (str(exc),),
        )
    return pass_finding(
        "compose.production_profile",
        "production contract resolves exactly the required production services",
        (f"{COMPOSE_PATH.as_posix()} services={','.join(sorted(services))}",),
    )


def check_image_digests(inputs: ContractInputs) -> Finding:
    if inputs.compose_error is not None:
        return blocked("compose.image_digest_pinning", "compose file is unavailable", (inputs.compose_error,))
    try:
        services = production_services(inputs.compose)
    except StrictParseError as exc:
        return blocked("compose.image_digest_pinning", "production services are not resolvable", (str(exc),))
    states, state_error = production_image_digest_states(inputs)
    if state_error is not None:
        return blocked("compose.image_digest_pinning", "production services are not resolvable", (state_error,))
    evidence = [
        f"{COMPOSE_PATH.as_posix()} {name}.image={services[name].get('image')!r}"
        for name, state in states.items()
        if state == "invalid"
    ]
    if evidence:
        return fail_finding(
            "compose.image_digest_pinning",
            "production images must be digest-pinned by sha256",
            tuple(evidence),
        )
    if all(state == "literal_digest" for state in states.values()):
        return pass_finding(
            "compose.image_digest_pinning",
            "all production service images are pinned by literal sha256 digests",
            (f"{COMPOSE_PATH.as_posix()} production_images=literal_sha256_digest_pinned",),
        )
    return pass_finding(
        "compose.image_digest_pinning",
        "all production service images use fail-fast required digest references",
        (
            f"{COMPOSE_PATH.as_posix()} production_images=fail_fast_required_refs",
            "image_digest_evidence=unresolved_required_refs_not_artifact_evidence",
        ),
    )


def check_production_policy(inputs: ContractInputs) -> Finding:
    if inputs.compose_error is not None:
        return blocked(
            "compose.production_policy",
            "production policy could not be checked because compose is unavailable",
            (inputs.compose_error,),
        )
    try:
        services = production_services(inputs.compose)
    except StrictParseError as exc:
        return blocked(
            "compose.production_policy",
            "production policy is not resolvable",
            (str(exc),),
        )
    if set(services) != set(REQUIRED_PRODUCTION_SERVICES):
        return blocked(
            "compose.production_policy",
            "production policy is not resolvable",
            ("production_services_not_exact",),
        )
    try:
        evidence: list[str] = []
        for name in sorted(services):
            if services[name].get("build") is not None:
                evidence.append(f"{COMPOSE_PATH.as_posix()} {name}.build=forbidden")
        for name in REQUIRED_PRODUCTION_POLICY_SERVICES:
            environment = service_environment(services[name], name)
            for key in REQUIRED_PRODUCTION_POLICY_ENV:
                value = environment.get(key)
                if value is None or PRODUCTION_REQUIRED_VALUE_PATTERN.fullmatch(value) is None:
                    evidence.append(f"{COMPOSE_PATH.as_posix()} {name}.{key}=required_value_invalid")
    except StrictParseError as exc:
        return blocked(
            "compose.production_policy",
            "production policy is not resolvable",
            (str(exc),),
        )
    if evidence:
        return fail_finding(
            "compose.production_policy",
            "production services must use immutable images and explicit policy bindings",
            tuple(evidence),
        )
    return pass_finding(
        "compose.production_policy",
        "production services use immutable images and explicit release and migration policy",
        (
            f"{COMPOSE_PATH.as_posix()} build=absent",
            f"{COMPOSE_PATH.as_posix()} release_policy=explicit_required_refs",
        ),
    )


def check_public_ports(inputs: ContractInputs) -> Finding:
    if inputs.compose_error is not None:
        return blocked("compose.public_ports", "compose file is unavailable", (inputs.compose_error,))
    try:
        services = production_services(inputs.compose)
    except StrictParseError as exc:
        return blocked("compose.public_ports", "production services are not resolvable", (str(exc),))

    evidence: list[str] = []
    for name in ("db", "es", "redis"):
        ports = services[name].get("ports")
        if ports is None:
            continue
        if not isinstance(ports, list):
            evidence.append(f"{COMPOSE_PATH.as_posix()} {name}.ports_type_invalid")
            continue
        for port in ports:
            if isinstance(port, dict):
                host = port.get("host_ip")
            elif isinstance(port, str):
                parts = port.split(":")
                if len(parts) == 3:
                    host = parts[0]
                elif len(parts) == 4 and ":" in parts[0]:
                    host = parts[0]
                else:
                    host = ""
            else:
                host = ""
            if not isinstance(host, str) or host.lower().strip("[]") not in LOOPBACK_HOSTS:
                evidence.append(f"{COMPOSE_PATH.as_posix()} {name}.ports={port!r}")
    if evidence:
        return fail_finding(
            "compose.public_ports",
            "db/es/redis ports must be omitted or explicitly loopback-bound",
            tuple(evidence),
        )
    return pass_finding(
        "compose.public_ports",
        "db/es/redis are not published outside loopback",
        (f"{COMPOSE_PATH.as_posix()} published_ports=loopback_only",),
    )


def check_source_bind_mounts(inputs: ContractInputs) -> Finding:
    if inputs.compose_error is not None:
        return blocked("compose.source_bind_mounts", "compose file is unavailable", (inputs.compose_error,))
    try:
        services = production_services(inputs.compose)
        compose_root = as_mapping(inputs.compose, "compose_root")
        named_volumes = set(as_mapping(compose_root.get("volumes") or {}, "compose_volumes"))
    except StrictParseError as exc:
        return blocked("compose.source_bind_mounts", "compose volumes are not resolvable", (str(exc),))
    evidence: list[str] = []
    for name in sorted(services):
        volumes = services[name].get("volumes")
        if volumes is None:
            continue
        if not isinstance(volumes, list):
            evidence.append(f"{COMPOSE_PATH.as_posix()} {name}.volumes_type_invalid")
            continue
        for volume in volumes:
            if isinstance(volume, dict):
                if volume.get("type") == "bind":
                    evidence.append(f"{COMPOSE_PATH.as_posix()} {name}.volumes={volume!r}")
                continue
            if not isinstance(volume, str):
                evidence.append(f"{COMPOSE_PATH.as_posix()} {name}.volumes={volume!r}")
                continue
            source = volume.split(":", 1)[0] if ":" in volume else volume
            if source.startswith((".", "/", "\\")) or "/" in source or "\\" in source:
                evidence.append(f"{COMPOSE_PATH.as_posix()} {name}.volumes={volume}")
            elif source not in named_volumes:
                evidence.append(f"{COMPOSE_PATH.as_posix()} {name}.volumes={source} unregistered")
    if evidence:
        return fail_finding(
            "compose.source_bind_mounts",
            "production services must not bind source or host paths into containers",
            tuple(evidence),
        )
    return pass_finding(
        "compose.source_bind_mounts",
        "production services use only registered named volumes",
        (f"{COMPOSE_PATH.as_posix()} mounts=named_volumes_only",),
    )


def check_default_credentials(inputs: ContractInputs) -> Finding:
    if inputs.compose_error is not None or inputs.env_error is not None:
        evidence = []
        if inputs.compose_error:
            evidence.append(f"{COMPOSE_PATH.as_posix()}:{inputs.compose_error}")
        if inputs.env_error:
            evidence.append(f"{ENV_PATH.as_posix()}:{inputs.env_error}")
        return blocked(
            "database.default_credentials",
            "credential inputs are unavailable",
            tuple(evidence),
        )
    try:
        services = production_services(inputs.compose)
        db_env = service_environment(services["db"], "db")
        backend_env = service_environment(services["backend"], "backend")
    except StrictParseError as exc:
        return blocked(
            "database.default_credentials",
            "credential environment is not resolvable",
            (str(exc),),
        )
    evidence: list[str] = []
    for key in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        if db_env.get(key, "").strip().lower() == "postgres":
            evidence.append(f"{COMPOSE_PATH.as_posix()} {key}=postgres")
    for name, env in (("db", db_env), ("backend", backend_env)):
        if DEFAULT_POSTGRES_URL.search(env.get("DATABASE_URL", "")):
            evidence.append(f"{COMPOSE_PATH.as_posix()} {name}.DATABASE_URL=default_postgres_pair")
    for key, value in inputs.env or ():
        if key == "DATABASE_URL" and DEFAULT_POSTGRES_URL.search(value):
            evidence.append(f"{ENV_PATH.as_posix()} {key}=default_postgres_pair")
        if key in {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"} and value.strip().lower() == "postgres":
            evidence.append(f"{ENV_PATH.as_posix()} {key}=postgres")
    if evidence:
        return fail_finding(
            "database.default_credentials",
            "default postgres credentials remain in production inputs",
            tuple(evidence),
        )
    return pass_finding(
        "database.default_credentials",
        "production credential inputs do not select the postgres/postgres default pair",
        (f"{COMPOSE_PATH.as_posix()} database_default=absent",),
    )


def check_elasticsearch_security(inputs: ContractInputs) -> Finding:
    if inputs.compose_error is not None:
        return blocked(
            "compose.elasticsearch_security",
            "compose file is unavailable",
            (inputs.compose_error,),
        )
    try:
        services = production_services(inputs.compose)
        es_env = service_environment(services["es"], "es")
    except StrictParseError as exc:
        return blocked(
            "compose.elasticsearch_security",
            "Elasticsearch environment is not resolvable",
            (str(exc),),
        )
    enabled = es_env.get("xpack.security.enabled", "").strip().lower()
    if enabled != "true":
        return fail_finding(
            "compose.elasticsearch_security",
            "production Elasticsearch must explicitly enable xpack security",
            (f"{COMPOSE_PATH.as_posix()} xpack.security.enabled={enabled or '<missing>'}",),
        )
    return pass_finding(
        "compose.elasticsearch_security",
        "production Elasticsearch explicitly enables xpack security",
        (f"{COMPOSE_PATH.as_posix()} xpack.security.enabled=true",),
    )


def release_version_status(version: str) -> tuple[bool, str]:
    if version in {"", "0", "0.0", "0.0.0", "latest", "dev"}:
        return False, "placeholder_or_missing"
    try:
        from packaging.version import InvalidVersion, Version
    except ImportError:
        return False, "packaging_dependency_unavailable"
    try:
        parsed = Version(version)
    except InvalidVersion:
        return False, "invalid_pep440_version"
    if parsed.is_prerelease or parsed.is_devrelease or parsed.local is not None:
        return False, "prerelease_or_local"
    return True, "stable"


def check_release_identity(inputs: ContractInputs, root: Path) -> Finding:
    pyproject, pyproject_error = read_toml(root / PYPROJECT_PATH)
    frontend, frontend_error = read_json(root / FRONTEND_PATH)
    if pyproject_error is not None or frontend_error is not None or inputs.compose_error is not None:
        evidence = []
        if pyproject_error:
            evidence.append(f"{PYPROJECT_PATH.as_posix()}:{pyproject_error}")
        if frontend_error:
            evidence.append(f"{FRONTEND_PATH.as_posix()}:{frontend_error}")
        if inputs.compose_error:
            evidence.append(f"{COMPOSE_PATH.as_posix()}:{inputs.compose_error}")
        return blocked("release.identity_alignment", "release identity inputs are unavailable", tuple(evidence))
    try:
        services = production_services(inputs.compose)
        backend_env = service_environment(services["backend"], "backend")
    except StrictParseError as exc:
        return blocked("release.identity_alignment", "backend identity contract is not resolvable", (str(exc),))
    project = pyproject.get("project") if isinstance(pyproject, dict) else None
    root_version = str(project.get("version", "") if isinstance(project, dict) else "").strip()
    frontend_version = str(frontend.get("version", "") if isinstance(frontend, dict) else "").strip()
    backend_version = backend_env.get("SERVICE_VERSION", "").strip()
    evidence = [
        f"{PYPROJECT_PATH.as_posix()} version={root_version or '<missing>'}",
        f"{FRONTEND_PATH.as_posix()} version={frontend_version or '<missing>'}",
        f"{COMPOSE_PATH.as_posix()} backend.SERVICE_VERSION={backend_version or '<missing>'}",
    ]
    statuses = {
        "root": release_version_status(root_version),
        "frontend": release_version_status(frontend_version),
        "backend": release_version_status(backend_version),
    }
    aligned = all(ok for ok, _ in statuses.values()) and root_version == frontend_version == backend_version
    if not aligned:
        reasons = [f"{name}={reason}" for name, (ok, reason) in statuses.items() if not ok]
        if not reasons:
            reasons.append("versions_differ")
        return fail_finding(
            "release.identity_alignment",
            "root, frontend, and backend must share one stable release version",
            tuple(evidence + [";".join(reasons)]),
        )
    return pass_finding(
        "release.identity_alignment",
        "root, frontend, and backend share one stable release version",
        tuple(evidence),
    )


def check_file_dependency(root: Path) -> Finding:
    payload, error = read_toml(root / PYPROJECT_PATH)
    if error is not None:
        return blocked("pyproject.file_dependency", "root pyproject is unavailable", (error,))

    def strings(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [item for child in value.values() for item in strings(child)]
        if isinstance(value, (list, tuple)):
            return [item for child in value for item in strings(child)]
        return []

    hits = [item for item in strings(payload) if item.startswith("file:///Users/")]
    if hits:
        return fail_finding(
            "pyproject.file_dependency",
            "root pyproject contains a machine-local file dependency",
            tuple(f"{PYPROJECT_PATH.as_posix()} {item}" for item in hits),
        )
    return pass_finding(
        "pyproject.file_dependency",
        "root pyproject has no machine-local file dependency",
        (PYPROJECT_PATH.as_posix(),),
    )


def parse_check_contract(branch: Any) -> dict[str, CheckContract]:
    payload = as_mapping(branch, "branch_protection")
    names = payload.get("required_checks")
    contracts = payload.get("required_check_contracts")
    sources = payload.get("required_check_sources")
    if not isinstance(names, list) or not all(isinstance(item, str) and item.strip() for item in names):
        raise StrictParseError("required_checks_not_nonempty_strings")
    if not isinstance(contracts, dict):
        raise StrictParseError("required_check_contracts_not_object")
    if not isinstance(sources, dict):
        raise StrictParseError("required_check_sources_not_object")
    normalized_names = [item.strip() for item in names]
    if len(normalized_names) != len(set(normalized_names)):
        raise StrictParseError("required_checks_duplicate")

    result: dict[str, CheckContract] = {}
    for category in REQUIRED_CHECK_CATEGORIES:
        raw_contract = contracts.get(category)
        if not isinstance(raw_contract, dict):
            raise StrictParseError(f"required_check_contract_missing:{category}")
        check_name = raw_contract.get("required_check")
        source = raw_contract.get("source")
        if not isinstance(check_name, str) or not check_name.strip():
            raise StrictParseError(f"required_check_name_invalid:{category}")
        if not isinstance(source, str) or not source.strip():
            raise StrictParseError(f"required_check_source_invalid:{category}")
        check_name = check_name.strip()
        expected_name = EXACT_REQUIRED_CHECK_NAMES.get(category)
        if expected_name is not None and check_name != expected_name:
            raise StrictParseError(f"required_check_name_mismatch:{category}")
        source_path = Path(source.strip())
        if source_path.is_absolute() or ".." in source_path.parts:
            raise StrictParseError(f"required_check_source_outside_workflows:{category}")
        if source_path.parts[:2] != (".github", "workflows"):
            raise StrictParseError(f"required_check_source_outside_workflows:{category}")
        if source_path.suffix not in {".yml", ".yaml"}:
            raise StrictParseError(f"required_check_source_not_yaml:{category}")
        if sources.get(check_name) != source.strip():
            raise StrictParseError(f"required_check_source_map_mismatch:{category}")
        if check_name not in normalized_names:
            raise StrictParseError(f"required_check_not_required:{category}")
        result[category] = CheckContract(check_name, source.strip())
    if set(normalized_names) != {item.required_check for item in result.values()}:
        raise StrictParseError("aggregate_or_uncontracted_required_check_present")
    return result


def job_for_required_check(workflow: Any, contract: CheckContract) -> dict[str, Any]:
    root = as_mapping(workflow, "workflow")
    jobs = as_mapping(root.get("jobs"), "workflow_jobs")
    job = jobs.get(contract.required_check)
    if not isinstance(job, dict):
        raise StrictParseError(f"required_job_missing:{contract.required_check}")
    name = job.get("name")
    if name is not None and name != contract.required_check:
        raise StrictParseError(f"required_job_name_mismatch:{contract.required_check}")
    if "if" in job:
        raise StrictParseError(f"required_job_condition_unsupported:{contract.required_check}")
    if job.get("continue-on-error") is not None and job.get("continue-on-error") is not False:
        raise StrictParseError(f"required_job_continue_on_error:{contract.required_check}")
    if "uses" in job:
        raise StrictParseError(f"required_job_reusable_workflow_unsupported:{contract.required_check}")
    steps = job.get("steps")
    if not isinstance(steps, list) or not steps:
        raise StrictParseError(f"required_job_steps_missing:{contract.required_check}")
    for step in steps:
        if not isinstance(step, dict):
            raise StrictParseError(f"required_step_not_object:{contract.required_check}")
        if "if" in step:
            condition = normalized_step_condition(step["if"])
            if condition not in ALLOWED_STEP_CONDITIONS or not explicit_support_step(step):
                raise StrictParseError(f"required_step_condition_unsupported:{contract.required_check}")
        if step.get("continue-on-error") not in {None, False}:
            raise StrictParseError(f"required_step_continue_on_error:{contract.required_check}")
        has_run = isinstance(step.get("run"), str) and bool(step["run"].strip())
        has_uses = isinstance(step.get("uses"), str) and bool(step["uses"].strip())
        if not has_run and not has_uses:
            raise StrictParseError(f"required_step_has_no_action:{contract.required_check}")
    return job


def parse_contracts_and_jobs(
    root: Path,
    branch: Any,
) -> tuple[dict[str, CheckContract], dict[str, tuple[Any, str | None]]]:
    contracts = parse_check_contract(branch)
    parsed: dict[str, tuple[Any, str | None]] = {}
    for contract in contracts.values():
        if contract.source not in parsed:
            parsed[contract.source] = parse_yaml(root / contract.source)
    return contracts, parsed


def raise_contract_error(message: str) -> None:
    raise StrictParseError(message)


def normalized_step_condition(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2].strip()
    return re.sub(r"\s+", "", text).lower()


def explicit_support_step(step: dict[str, Any]) -> bool:
    name = str(step.get("name", "")).strip().lower()
    uses = str(step.get("uses", "")).strip()
    return (
        any(marker in name for marker in SUPPORT_STEP_MARKERS)
        or "upload" in name
        or uses.startswith("actions/upload-artifact@")
    )


def check_branch_protection(inputs: ContractInputs, root: Path) -> Finding:
    if inputs.branch_protection_error is not None:
        return blocked(
            "branch_protection.required_checks",
            "branch protection contract is unavailable",
            (f"{BRANCH_PROTECTION_PATH.as_posix()}:{inputs.branch_protection_error}",),
        )
    try:
        contracts, parsed = parse_contracts_and_jobs(root, inputs.branch_protection)
        for source, (workflow, error) in parsed.items():
            if error is not None:
                raise_contract_error(f"workflow_parse_failed:{source}:{error}")
            workflow_root = as_mapping(workflow, "workflow")
            concurrency = workflow_root.get("concurrency")
            if isinstance(concurrency, dict) and concurrency.get("cancel-in-progress") is not False:
                raise_contract_error(f"required_workflow_cancel_in_progress:{source}")
        for contract in contracts.values():
            job_for_required_check(parsed[contract.source][0], contract)
    except StrictParseError as exc:
        return fail_finding(
            "branch_protection.required_checks",
            "branch protection does not provide complete concrete required-check contracts",
            (str(exc),),
        )
    categories = ",".join(REQUIRED_CHECK_CATEGORIES)
    return pass_finding(
        "branch_protection.required_checks",
        "every release domain maps to a concrete required job",
        (f"{BRANCH_PROTECTION_PATH.as_posix()} categories={categories}",),
    )


def security_steps(
    contracts: dict[str, CheckContract],
    parsed: dict[str, tuple[Any, str | None]],
) -> list[dict[str, Any]] | None:
    contract = contracts.get("security")
    if contract is None:
        return None
    workflow, error = parsed.get(contract.source, (None, "not_loaded"))
    if error is not None:
        return None
    try:
        job = job_for_required_check(workflow, contract)
    except StrictParseError:
        return None
    steps = job.get("steps")
    if not isinstance(steps, list):
        return None
    return [step for step in steps if isinstance(step, dict)]


def job_for_category(
    category: str,
    contracts: dict[str, CheckContract],
    parsed: dict[str, tuple[Any, str | None]],
) -> dict[str, Any] | None:
    contract = contracts.get(category)
    if contract is None:
        return None
    workflow, error = parsed.get(contract.source, (None, "not_loaded"))
    if error is not None:
        return None
    try:
        return job_for_required_check(workflow, contract)
    except StrictParseError:
        return None


def executable_run_text(step: dict[str, Any]) -> str:
    run = step.get("run")
    if not isinstance(run, str):
        return ""
    lines = []
    for line in run.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^(?:echo|printf)\b", stripped, re.IGNORECASE):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def critical_step_is_blocking(step: dict[str, Any]) -> bool:
    run = executable_run_text(step).lower()
    return not any(
        re.search(pattern, run)
        for pattern in (
            r"\|\|\s*(?:true|:)(?:\s|$)",
            r"(?:^|[;&]\s*)set\s+\+e(?:\s|$)",
            r"(?:^|;)\s*exit\s+0(?:\s|$)",
        )
    )


def frontend_scoped(job: dict[str, Any], step: dict[str, Any]) -> bool:
    step_directory = step.get("working-directory")
    defaults = job.get("defaults")
    job_directory: Any = None
    if isinstance(defaults, dict) and isinstance(defaults.get("run"), dict):
        job_directory = defaults["run"].get("working-directory")
    directories = {str(value).strip().rstrip("/") for value in (step_directory, job_directory)}
    if "main/frontend-modern" in directories or "./main/frontend-modern" in directories:
        return True
    run = executable_run_text(step)
    return bool(re.search(r"(?:^|\s)(?:cd|--dir|-C)\s+['\"]?(?:\./)?main/frontend-modern(?:/)?['\"]?(?:\s|$)", run))


def check_frontend_component_e2e(
    contracts: dict[str, CheckContract],
    parsed: dict[str, tuple[Any, str | None]],
) -> Finding:
    job = job_for_category("frontend-component-e2e", contracts, parsed)
    if job is None:
        return fail_finding(
            "workflow.frontend_component_e2e",
            "frontend component/e2e required job is unavailable or bypassable",
            ("frontend_component_e2e_job=unavailable",),
        )
    steps = [step for step in job.get("steps", []) if isinstance(step, dict)]
    install_indexes = [
        index
        for index, step in enumerate(steps)
        if re.search(r"(?:^|\n)pnpm\s+install\b[^\n]*--frozen-lockfile\b", executable_run_text(step))
        and frontend_scoped(job, step)
        and critical_step_is_blocking(step)
    ]
    storybook_indexes = [
        index
        for index, step in enumerate(steps)
        if re.search(
            r"(?:^|\n)pnpm\s+(?:run\s+)?(?:build-storybook|storybook:build)\b",
            executable_run_text(step),
        )
        and frontend_scoped(job, step)
        and critical_step_is_blocking(step)
    ]
    playwright_indexes = [
        index
        for index, step in enumerate(steps)
        if re.search(
            r"(?:^|\n)pnpm\s+exec\s+playwright\s+install\b[^\n]*(?:--with-deps\s+chromium|chromium\s+--with-deps)\b",
            executable_run_text(step),
        )
        and frontend_scoped(job, step)
        and critical_step_is_blocking(step)
    ]
    e2e_indexes = [
        index
        for index, step in enumerate(steps)
        if re.search(r"(?:^|\n)pnpm\s+(?:run\s+)?test:e2e\b", executable_run_text(step))
        and "--list" not in executable_run_text(step)
        and frontend_scoped(job, step)
        and critical_step_is_blocking(step)
    ]
    evidence = []
    if not install_indexes:
        evidence.append("frontend_frozen_install=missing")
    if not storybook_indexes:
        evidence.append("storybook_component_build=missing")
    if not playwright_indexes:
        evidence.append("playwright_chromium_setup=missing")
    if not e2e_indexes:
        evidence.append("blocking_pnpm_test_e2e=missing")
    if (
        install_indexes
        and storybook_indexes
        and playwright_indexes
        and e2e_indexes
        and min(install_indexes) >= min(storybook_indexes + playwright_indexes + e2e_indexes)
    ):
        evidence.append("frontend_frozen_install=not_before_execution")
    if evidence:
        return fail_finding(
            "workflow.frontend_component_e2e",
            "frontend component/e2e job lacks a complete blocking execution contract",
            tuple(evidence),
        )
    return pass_finding(
        "workflow.frontend_component_e2e",
        "frontend component build and Playwright e2e execution are blocking",
        ("frontend_component_e2e_contract=complete",),
    )


def check_workflow_security(
    contracts: dict[str, CheckContract],
    parsed: dict[str, tuple[Any, str | None]],
) -> Finding:
    steps = security_steps(contracts, parsed)
    if steps is None:
        return fail_finding(
            "workflow.security_scans",
            "security required-check contract does not expose scannable steps",
            ("security_contract=unavailable",),
        )
    commands = [executable_run_text(step) for step in steps]
    uses = [str(step["uses"]) for step in steps if isinstance(step.get("uses"), str)]
    evidence = []
    if not any(
        re.search(r"(?:^|\n)(?:python(?:3)?\s+-m\s+)?bandit\b", command) and critical_step_is_blocking(step)
        for step, command in zip(steps, commands, strict=True)
    ):
        evidence.append("bandit=missing")
    functorial_kit_audit_tokens = (
        "python scripts/formal_release/check_functorial_kit_dependency_audit.py",
        "--requirements main/backend/requirements.txt",
        "--pyproject pyproject.toml",
        "--manifest tools/functorial-kit/consumer-gate.manifest.json",
        "--source-checkout .ci/functorial-kit-source",
        '--public-requirements "${RUNNER_TEMP}/mrw-public-pypi-requirements.txt"',
        '--report "${RUNNER_TEMP}/mrw-functorial-kit-dependency-audit.json"',
    )
    functorial_kit_checkout_indexes = []
    for index, step in enumerate(steps):
        step_with = step.get("with")
        if (
            step.get("uses") == "actions/checkout@v4"
            and isinstance(step_with, dict)
            and step_with.get("repository") == "123rrr4tttt/functorial-kit"
            and step_with.get("ref") == "785ff25e201c9eae84c862e68e786bc975e7a800"
            and step_with.get("path") == ".ci/functorial-kit-source"
            and step_with.get("persist-credentials") is False
        ):
            functorial_kit_checkout_indexes.append(index)
    functorial_kit_audit_indexes = [
        index
        for index, (step, command) in enumerate(zip(steps, commands, strict=True))
        if all(token in command for token in functorial_kit_audit_tokens) and critical_step_is_blocking(step)
    ]
    public_pip_audit_indexes = [
        index
        for index, (step, command) in enumerate(zip(steps, commands, strict=True))
        if re.search(
            r'(?:^|\n)pip-audit\s+-r\s+"\$\{RUNNER_TEMP\}/mrw-public-pypi-requirements\.txt"\s+--strict(?:\s|$)',
            command,
        )
        and critical_step_is_blocking(step)
    ]
    if len(functorial_kit_checkout_indexes) != 1:
        evidence.append("functorial_kit_source_checkout=missing_or_nonunique")
    if len(functorial_kit_audit_indexes) != 1:
        evidence.append("functorial_kit_dependency_audit=missing")
    if len(public_pip_audit_indexes) != 1:
        evidence.append("pip_audit_public_strict=missing")
    elif not functorial_kit_audit_indexes or min(functorial_kit_audit_indexes) >= min(public_pip_audit_indexes):
        evidence.append("pip_audit_public_strict=not_after_functorial_kit_classification")
    if (
        functorial_kit_checkout_indexes
        and functorial_kit_audit_indexes
        and min(functorial_kit_checkout_indexes) >= min(functorial_kit_audit_indexes)
    ):
        evidence.append("functorial_kit_dependency_audit=not_after_source_checkout")
    public_projection_token = '${RUNNER_TEMP}/mrw-public-pypi-requirements.txt'
    public_projection_users = [
        index for index, command in enumerate(commands) if public_projection_token in command
    ]
    allowed_public_projection_users = set(functorial_kit_audit_indexes + public_pip_audit_indexes)
    if set(public_projection_users) != allowed_public_projection_users:
        evidence.append("pip_audit_public_input=unexpected_producer_or_consumer")
    frozen_install_indexes = [
        index
        for index, (step, command) in enumerate(zip(steps, commands, strict=True))
        if re.search(r"(?:^|\n)pnpm\s+install\b[^\n]*--frozen-lockfile\b", command)
        and frontend_scoped({"steps": steps}, step)
        and critical_step_is_blocking(step)
    ]
    frontend_audit_indexes = [
        index
        for index, (step, command) in enumerate(zip(steps, commands, strict=True))
        if re.search(r"(?:^|\n)pnpm\s+audit\b[^\n]*(?:--prod\b)", command)
        and re.search(r"--audit-level(?:=|\s+)high\b", command)
        and frontend_scoped({"steps": steps}, step)
        and critical_step_is_blocking(step)
    ]
    if not frozen_install_indexes:
        evidence.append("frontend_frozen_install=missing")
    if not frontend_audit_indexes:
        evidence.append("pnpm_audit_prod_high=missing")
    elif not frozen_install_indexes or min(frozen_install_indexes) >= min(frontend_audit_indexes):
        evidence.append("pnpm_audit_prod_high=not_after_frozen_install")
    if not any(
        re.search(r"(?:^|\n)gitleaks\b", command) and critical_step_is_blocking(step)
        for step, command in zip(steps, commands, strict=True)
    ) and not any("gitleaks" in use.lower() for use in uses):
        evidence.append("gitleaks=missing")
    if evidence:
        return fail_finding(
            "workflow.security_scans",
            "required security job is missing executable security scans",
            tuple(evidence),
        )
    return pass_finding(
        "workflow.security_scans",
        "required security job classifies the fixed Git dependency and executes blocking public dependency audits",
        ("security_contract=fixed_git_source_plus_public_pypi_strict",),
    )


def artifact_job(
    contracts: dict[str, CheckContract],
    parsed: dict[str, tuple[Any, str | None]],
) -> dict[str, Any] | None:
    contract = contracts.get("artifact-metadata")
    if contract is None:
        return None
    workflow, error = parsed.get(contract.source, (None, "not_loaded"))
    if error is not None:
        return None
    try:
        return job_for_required_check(workflow, contract)
    except StrictParseError:
        return None


def static_step_text(step: dict[str, Any]) -> str:
    return json.dumps(step, sort_keys=True, separators=(",", ":")).lower()


def build_role(step: dict[str, Any]) -> Annotated[
    str | None,
    "kit:non-authoritative derived_as=static_artifact_role "
    "fact_source=workflow_step_identity "
    "witness=test:test_build_role_is_non_authoritative_and_rejects_ambiguity",
]:
    with_payload = step.get("with")
    if not isinstance(with_payload, dict):
        return None
    identity = " ".join(
        str(value).lower()
        for value in (
            step.get("id", ""),
            step.get("name", ""),
            with_payload.get("tags", ""),
        )
    ).replace("_", "-")
    matched = []
    if "migration-runner" in identity:
        matched.append("migration-runner")
        identity = identity.replace("migration-runner", "")
    for role in ("backend", "frontend"):
        if re.search(rf"(?:^|[^a-z0-9]){role}(?:[^a-z0-9]|$)", identity):
            matched.append(role)
    return matched[0] if len(matched) == 1 else None


def artifact_builds(
    job: dict[str, Any],
    *,
    require_supply_chain: bool,
    id_prefix: str | None = None,
    evidence_prefix: str = "artifact",
    builder_id: str | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    steps = [step for step in job.get("steps", []) if isinstance(step, dict)]
    build_steps = [
        step
        for step in steps
        if isinstance(step.get("uses"), str) and str(step["uses"]).startswith("docker/build-push-action@")
        and (id_prefix is None or str(step.get("id", "")).startswith(id_prefix))
    ]
    evidence: list[str] = []
    if len(build_steps) != len(ARTIFACT_ROLES):
        evidence.append(f"{evidence_prefix}_build_count={len(build_steps)}")
    by_role: dict[str, dict[str, Any]] = {}
    tags: list[str] = []
    build_ids: list[str] = []
    for step in build_steps:
        role = build_role(step)
        if role is None or role in by_role:
            evidence.append(f"{evidence_prefix}_build_role=ambiguous_or_duplicate")
            continue
        by_role[role] = step
        with_payload = step.get("with")
        if not isinstance(with_payload, dict):
            evidence.append(f"{evidence_prefix}_{role}.build_with=missing")
            continue
        contract = ARTIFACT_BUILD_CONTRACTS[role]
        context = str(with_payload.get("context", "")).strip()
        dockerfile = str(with_payload.get("file", "")).strip()
        target = str(with_payload.get("target", "")).strip()
        tag = str(with_payload.get("tags", "")).strip()
        build_id = str(step.get("id", "")).strip()
        if context not in contract["contexts"]:
            evidence.append(f"{evidence_prefix}_{role}.context=invalid")
        if dockerfile not in contract["files"]:
            evidence.append(f"{evidence_prefix}_{role}.dockerfile=invalid")
        if target not in contract["targets"]:
            evidence.append(f"{evidence_prefix}_{role}.target=invalid")
        if not tag or role not in tag.lower().replace("_", "-"):
            evidence.append(f"{evidence_prefix}_{role}.tag=invalid")
        outputs = str(with_payload.get("outputs", ""))
        if with_payload.get("push") is not False:
            evidence.append(f"{evidence_prefix}_{role}.registry_write=not_disabled")
        if "type=oci" not in outputs or "dest=" not in outputs:
            evidence.append(f"{evidence_prefix}_{role}.oci_output=missing")
        if builder_id is not None and str(with_payload.get("builder", "")).strip() != (
            "${{ steps." + builder_id + ".outputs.name }}"
        ):
            evidence.append(f"{evidence_prefix}_{role}.builder=not_bound")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", build_id):
            evidence.append(f"{evidence_prefix}_{role}.build_id=invalid")
        if require_supply_chain and (
            with_payload.get("provenance") is not True or with_payload.get("sbom") is not True
        ):
            evidence.append(f"{evidence_prefix}_{role}.provenance_and_sbom=missing")
        if with_payload.get("no-cache") is not True:
            evidence.append(f"{evidence_prefix}_{role}.clean_build=missing")
        if str(with_payload.get("platforms", "")).strip() != "linux/amd64":
            evidence.append(f"{evidence_prefix}_{role}.platform=not_fixed")
        if "SOURCE_DATE_EPOCH=0" not in str(with_payload.get("build-args", "")):
            evidence.append(f"{evidence_prefix}_{role}.source_date_epoch=missing")
        tags.append(tag)
        build_ids.append(build_id)
    missing_roles = sorted(set(ARTIFACT_ROLES) - set(by_role))
    if missing_roles:
        evidence.append(f"{evidence_prefix}_roles_missing=" + ",".join(missing_roles))
    if len(tags) != len(set(tags)):
        evidence.append(f"{evidence_prefix}_tags=not_distinct")
    if len(build_ids) != len(set(build_ids)):
        evidence.append(f"{evidence_prefix}_build_ids=not_distinct")
    return by_role, evidence


def digest_reference(build_id: str) -> str:
    return f"steps.{build_id}.outputs.digest"


def step_consumes_digest(step: dict[str, Any], build_id: str) -> bool:
    digest = digest_reference(build_id).lower()
    run = executable_run_text(step).lower()
    if digest in run:
        return True
    env = step.get("env")
    if not isinstance(env, dict):
        return False
    for key, value in env.items():
        if digest not in str(value).lower():
            continue
        variable = re.escape(str(key).lower())
        if re.search(rf"\$(?:{variable}\b|\{{{variable}\}})", run) or re.search(
            rf"os\.environ(?:\[\s*['\"]{variable}['\"]\s*\]|\.get\(\s*['\"]{variable}['\"])",
            run,
        ):
            return True
    return False


def role_operation_coverage(
    steps: list[dict[str, Any]],
    builds: dict[str, dict[str, Any]],
    operation: re.Pattern[str],
) -> set[str]:
    covered: set[str] = set()
    for role, build in builds.items():
        build_id = str(build.get("id", ""))
        for step in steps:
            run = executable_run_text(step).lower()
            if (
                operation.search(run)
                and step_consumes_digest(step, build_id)
                and "@" in run
                and critical_step_is_blocking(step)
            ):
                covered.add(role)
                break
    return covered


def missing_role_evidence(prefix: str, covered: set[str]) -> str | None:
    missing = sorted(set(ARTIFACT_ROLES) - covered)
    return f"{prefix}_roles_missing=" + ",".join(missing) if missing else None


def check_artifact_metadata(
    inputs: ContractInputs,
    contracts: dict[str, CheckContract],
    parsed: dict[str, tuple[Any, str | None]],
) -> Finding:
    image_finding = check_image_digests(inputs)
    digest_states, digest_state_error = production_image_digest_states(inputs)
    job = artifact_job(contracts, parsed)
    evidence = []
    unresolved_required_refs = False
    if image_finding.status != "PASS":
        evidence.append("compose.image_digest_pinning=not_clean")
    elif digest_state_error is not None:
        evidence.append("compose.image_digest_contract=unresolved")
    else:
        unresolved_required_refs = any(state == "required_reference" for state in digest_states.values())
    if job is None:
        evidence.append("artifact_metadata_job=unavailable")
        return fail_finding(
            "artifact_metadata.immutable_release",
            "immutable metadata job does not cover the required artifact contracts",
            tuple(evidence),
        )
    steps = [step for step in job.get("steps", []) if isinstance(step, dict)]
    all_build_steps = [
        step for step in steps
        if str(step.get("uses", "")).startswith("docker/build-push-action@")
    ]
    if len(all_build_steps) != 2 * len(ARTIFACT_ROLES):
        evidence.append(f"artifact_chain_build_count={len(all_build_steps)}")
    builds, build_evidence = artifact_builds(
        job,
        require_supply_chain=True,
        id_prefix="build-",
        evidence_prefix="artifact",
        builder_id="canonical-builder",
    )
    evidence.extend(build_evidence)
    rebuilds, rebuild_evidence = artifact_builds(
        job,
        require_supply_chain=False,
        id_prefix="rebuild-",
        evidence_prefix="rebuild",
        builder_id="rebuild-builder",
    )
    evidence.extend(rebuild_evidence)
    setup_step_list = [
        step
        for step in steps
        if str(step.get("uses", "")).startswith("docker/setup-buildx-action@")
    ]
    setup_steps = {str(step.get("id", "")): step for step in setup_step_list}
    if len(setup_step_list) != 2 or set(setup_steps) != {"canonical-builder", "rebuild-builder"}:
        evidence.append("independent_builders=missing")
    elif any(
        not isinstance(step.get("with"), dict) or step["with"].get("driver") != "docker-container"
        for step in setup_steps.values()
    ):
        evidence.append("independent_builders=not_isolated")

    canonical_step = next((step for step in steps if str(step.get("id", "")) == "canonical-evidence"), None)
    canonical_text = static_step_text(canonical_step) if canonical_step is not None else ""
    attestation_markers = (
        "https://slsa.dev/provenance/",
        "https://spdx.dev/document",
        "predicatetype",
        "spdxversion",
        "subject_matches",
        "artifact_digest",
        "oci root digest mismatch",
        "oci blob digest mismatch",
        "canonical image platform is not linux/amd64",
        "canonical image manifest content is incomplete",
        "digest-inspection.json",
        "provenance.intoto.json",
        "sbom.spdx.intoto.json",
    )
    if canonical_step is None or not all(marker in canonical_text for marker in attestation_markers):
        evidence.append("attestation_content_validation=missing")
    elif not all(step_consumes_digest(canonical_step, str(build.get("id", ""))) for build in builds.values()):
        evidence.append("attestation_canonical_digest_flow=incomplete")

    reproducibility_steps = [
        step for step in steps if "compare clean rebuild digests" in str(step.get("name", "")).lower()
    ]
    reproducibility_text = "\n".join(static_step_text(step) for step in reproducibility_steps)
    reproducibility_run = "\n".join(executable_run_text(step).lower() for step in reproducibility_steps)
    for role, rebuild in rebuilds.items():
        canonical_output = f"steps.canonical-evidence.outputs.{role.replace('-', '_')}_digest"
        rebuild_output = digest_reference(str(rebuild.get("id", "")))
        if canonical_output not in reproducibility_text or rebuild_output not in reproducibility_text:
            evidence.append(f"reproducibility_digest_flow_missing={role}")
    if not all(
        marker in reproducibility_run
        for marker in (
            "non-reproducible clean build",
            '"status": "match"',
            "comparison_scope",
            "linux/amd64-image-manifest-digest",
            "rebuild oci blob digest mismatch",
            '"canonical": "canonical-builder"',
            '"rebuild": "rebuild-builder"',
        )
    ):
        evidence.append("reproducibility_comparison=missing")

    job_text = "\n".join(static_step_text(step) for step in steps)
    if any(marker in job_text for marker in ("cosign sign", "rekor", "tlog-upload", "docker/login-action@", '"push":true')):
        evidence.append("authority_write_present_in_preflight")
    if not all(marker in job_text for marker in ("production_release_not_authorized", "unexecuted_authority_required", "authority-receipt.json", "signing_status", "publishing_status")):
        evidence.append("authority_boundary=missing")
    role_indexed = set()
    for role, build in builds.items():
        build_id = str(build.get("id", ""))
        role_path = role.replace("-", r"[-_/]")
        for step in steps:
            if step_consumes_digest(step, build_id) and re.search(
                rf"immutable-release-metadata/(?:roles/)?{role_path}(?:[/_.-]|$)", static_step_text(step)
            ):
                role_indexed.add(role)
                break
    role_index_missing = missing_role_evidence("metadata_role_index", role_indexed)
    if role_index_missing is not None:
        evidence.append(role_index_missing)
    persisted = [
        step
        for step in steps
        if isinstance(step.get("uses"), str)
        and step["uses"].startswith("actions/upload-artifact@")
        and isinstance(step.get("with"), dict)
        and str(step["with"].get("name", "")).startswith("immutable-release-metadata")
        and isinstance(step["with"].get("path"), str)
        and bool(step["with"]["path"].strip())
    ]
    if not persisted:
        evidence.append("metadata_artifact=missing")
    if evidence:
        return fail_finding(
            "artifact_metadata.immutable_release",
            "release job lacks a real immutable artifact contract",
            tuple(evidence),
        )
    return pass_finding(
        "artifact_metadata.immutable_release",
        "canonical three-role artifact chain validates scans, predicates, and reproducible digests",
        tuple(
            (
                "canonical_artifact_chain_contract=complete",
                "artifact_bytes_not_built_or_verified_current_run",
                "required_refs_not_artifact_evidence",
            )
            if unresolved_required_refs
            else (
                "canonical_artifact_chain_contract=complete",
                "artifact_bytes_not_built_or_verified_current_run",
            )
        ),
    )


def check_image_vulnerability_scan(
    contracts: dict[str, CheckContract],
    parsed: dict[str, tuple[Any, str | None]],
) -> Finding:
    job = job_for_category("image-vulnerability-scan", contracts, parsed)
    if job is None:
        return fail_finding(
            "workflow.image_vulnerability_scan",
            "image vulnerability scan required job is unavailable or bypassable",
            ("image_vulnerability_scan_job=unavailable",),
        )
    steps = [step for step in job.get("steps", []) if isinstance(step, dict)]
    evidence: list[str] = []
    raw_needs = job.get("needs")
    needs = {raw_needs} if isinstance(raw_needs, str) else set(raw_needs or [])
    if "artifact-metadata-check" not in needs:
        evidence.append("canonical_artifact_dependency=missing")
    downloads = [
        step
        for step in steps
        if str(step.get("uses", "")).startswith("actions/download-artifact@")
        and isinstance(step.get("with"), dict)
        and step["with"].get("name") == "immutable-release-metadata"
    ]
    if not downloads:
        evidence.append("canonical_artifact_download=missing")
    validation_text = "\n".join(executable_run_text(step).lower() for step in steps)
    required_markers = (
        "vulnerability-scan-evidence",
        "high",
        "critical",
        "canonical_digest",
        "artifact_digest",
        "exit-code=1",
        "sha256",
        "production_release_not_authorized",
        "unexecuted_authority_required",
        "authority receipt hash mismatch",
        "oci blob digest mismatch",
        "canonical image manifest digest mismatch",
        "schemaversion",
        "artifactname",
        "trivy report identity or schema mismatch",
    )
    if not all(marker in validation_text for marker in required_markers):
        evidence.append("persisted_scan_content_validation=missing")
    scan_job_text = "\n".join(static_step_text(step) for step in steps)
    if any(
        str(step.get("uses", "")).startswith("docker/build-push-action@")
        for step in steps
    ):
        evidence.append("canonical_scan_rebuild=forbidden")
    if any(marker in scan_job_text for marker in ("cosign sign", "docker/login-action@", '"push":true', "docker push", "skopeo copy")):
        evidence.append("scan_authority_write=forbidden")
    scan_pattern = re.compile(r"(?:^|\n)docker\s+run\b[^\n]*\btrivy\b")
    for role in ARTIFACT_ROLES:
        role_path = f"immutable-release-metadata/{role}/image.oci.tar"
        role_steps = [step for step in steps if role_path in static_step_text(step)]
        if not any(
            scan_pattern.search(executable_run_text(step).lower())
            and re.search(r"--severity(?:=|\s+)(?:high,critical|critical,high)\b", executable_run_text(step).lower())
            and re.search(r"--exit-code(?:=|\s+)1\b", executable_run_text(step).lower())
            and "--input" in executable_run_text(step).lower()
            and critical_step_is_blocking(step)
            for step in role_steps
        ):
            evidence.append(f"canonical_oci_scan_missing={role}")
    uploads = [
        step for step in steps
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
        and isinstance(step.get("with"), dict)
        and step["with"].get("name") == "canonical-vulnerability-evidence"
        and step["with"].get("if-no-files-found") == "error"
    ]
    if not uploads:
        evidence.append("vulnerability_evidence_upload=missing")
    if evidence:
        return fail_finding(
            "workflow.image_vulnerability_scan",
            "image scan job lacks exact three-role immutable blocking coverage",
            tuple(evidence),
        )
    return pass_finding(
        "workflow.image_vulnerability_scan",
        "persisted scans are rebound to the canonical digest and revalidated fail closed",
        ("canonical_vulnerability_evidence_contract=complete",),
    )


def check_required_convergence(
    contracts: dict[str, CheckContract],
    parsed: dict[str, tuple[Any, str | None]],
) -> Finding:
    expected = {contract.required_check for contract in contracts.values()}
    candidates: list[dict[str, Any]] = []
    for workflow, error in parsed.values():
        if error is not None:
            continue
        try:
            jobs = as_mapping(as_mapping(workflow, "workflow").get("jobs"), "workflow_jobs")
        except StrictParseError:
            continue
        convergence = jobs.get("required-convergence-check")
        if isinstance(convergence, dict):
            candidates.append(convergence)
    evidence = []
    if len(candidates) != 1:
        evidence.append(f"required_convergence_job_count={len(candidates)}")
    else:
        job = candidates[0]
        if normalized_step_condition(job.get("if")) != "always()":
            evidence.append("required_convergence_job_condition=not_always")
        if job.get("continue-on-error") not in {None, False}:
            evidence.append("required_convergence_job=continue_on_error")
        raw_needs = job.get("needs")
        if isinstance(raw_needs, str):
            needs = {raw_needs}
        elif isinstance(raw_needs, list) and all(isinstance(item, str) for item in raw_needs):
            needs = set(raw_needs)
        else:
            needs = set()
            evidence.append("required_convergence_needs=invalid")
        if needs != expected:
            missing = sorted(expected - needs)
            extra = sorted(needs - expected)
            evidence.append(f"required_convergence_needs_missing={','.join(missing) or '<none>'}")
            if extra:
                evidence.append("required_convergence_needs_extra=" + ",".join(extra))
        steps = job.get("steps")
        if not isinstance(steps, list) or not steps or not all(isinstance(step, dict) for step in steps):
            evidence.append("required_convergence_steps=invalid")
        else:
            run = "\n".join(executable_run_text(step) for step in steps)
            static = "\n".join(static_step_text(step) for step in steps)
            if "tojson(needs)" not in static.replace(" ", ""):
                evidence.append("required_convergence_needs_readback=missing")
            referenced = {name for name in expected if name in run}
            if referenced != expected:
                evidence.append("required_convergence_source_missing=" + ",".join(sorted(expected - referenced)))
            if not re.search(r"result\s*!=\s*['\"]success['\"]", run, re.IGNORECASE):
                evidence.append("required_convergence_success_predicate=missing")
            if not re.search(r"(?:sys\.exit|raise\s+systemexit)\s*\(\s*1\s*\)|(?:^|\n)exit\s+1\b", run, re.IGNORECASE):
                evidence.append("required_convergence_failure_exit=missing")
            if not all(critical_step_is_blocking(step) for step in steps if executable_run_text(step)):
                evidence.append("required_convergence_step=bypassable")
    if evidence:
        return fail_finding(
            "workflow.required_convergence",
            "required convergence does not fail closed over the complete branch contract",
            tuple(evidence),
        )
    return pass_finding(
        "workflow.required_convergence",
        "required convergence checks every contracted job outcome",
        ("required_convergence_contract=complete",),
    )


def evaluate_static_production_contract(repo_root: Path | None = None) -> PreflightReport:
    root = resolve_root(repo_root)
    inputs = load_inputs(root)
    branch_contracts: dict[str, CheckContract] | None = None
    parsed_workflows: dict[str, tuple[Any, str | None]] = {}
    if inputs.branch_protection_error is None:
        try:
            branch_contracts, parsed_workflows = parse_contracts_and_jobs(root, inputs.branch_protection)
        except StrictParseError:
            branch_contracts = None
            parsed_workflows = {}
    findings = [
        check_production_profile(inputs),
        check_image_digests(inputs),
        check_production_policy(inputs),
        check_public_ports(inputs),
        check_source_bind_mounts(inputs),
        check_default_credentials(inputs),
        check_elasticsearch_security(inputs),
        check_release_identity(inputs, root),
        check_file_dependency(root),
        check_branch_protection(inputs, root),
    ]
    if branch_contracts is None:
        findings.extend(
            [
                fail_finding(
                    "workflow.security_scans",
                    "security checks cannot be verified without concrete branch contracts",
                    ("security_contract=unavailable",),
                ),
                fail_finding(
                    "artifact_metadata.immutable_release",
                    "artifact metadata cannot be verified without concrete branch contracts",
                    ("artifact_metadata_contract=unavailable",),
                ),
                fail_finding(
                    "workflow.frontend_component_e2e",
                    "frontend component/e2e cannot be verified without concrete branch contracts",
                    ("frontend_component_e2e_contract=unavailable",),
                ),
                fail_finding(
                    "workflow.image_vulnerability_scan",
                    "image vulnerability scans cannot be verified without concrete branch contracts",
                    ("image_vulnerability_scan_contract=unavailable",),
                ),
                fail_finding(
                    "workflow.required_convergence",
                    "required convergence cannot be verified without concrete branch contracts",
                    ("required_convergence_contract=unavailable",),
                ),
            ]
        )
    else:
        findings.extend(
            [
                check_frontend_component_e2e(branch_contracts, parsed_workflows),
                check_workflow_security(branch_contracts, parsed_workflows),
                check_artifact_metadata(inputs, branch_contracts, parsed_workflows),
                check_image_vulnerability_scan(branch_contracts, parsed_workflows),
                check_required_convergence(branch_contracts, parsed_workflows),
            ]
        )
    return PreflightReport(checker=CHECKER, findings=tuple(findings))


def write_output(path: Path, report: PreflightReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_json(), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = evaluate_static_production_contract(args.repo_root)
    if args.output is not None:
        write_output(args.output, report)
    print(report.to_json(), end="")
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
