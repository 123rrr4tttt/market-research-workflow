"""Portable integration declarations. No credential resolution, network or execution.

This is the authority copied by the experimental adapter pool. An integration
binds one interface and access method to one project's parameter references.
"""
from __future__ import annotations

import re
from typing import Annotated, Literal, NoReturn, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


INTEGRATION_MANIFEST_VERSION = "external_item.manifest.v2"
ExecutionMode = Literal["rss_feed", "sitemap", "http_api", "article_extractor", "python_library", "cli_or_container"]
FrameworkType = Literal["api_client", "browser_client", "media_downloader", "feed", "parser", "crawler"]
AccessMode = Literal["anonymous", "api_key", "oauth2", "account_login", "session"]
ParameterKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
CredentialRef = Annotated[str, Field(pattern=r"^env:[A-Z][A-Z0-9_]{0,127}$")]
ConfigValue = str | int | float | bool


def _invalid() -> NoReturn:
    # Pydantic catches this at the wire-schema boundary. The MRW normalizer
    # translates ValidationError to external_project_manifest_invalid.
    # kit:boundary owner=source_library.external_integration class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source_library.contract_failure witness=test:test_integration_contract
    raise ValueError("integration declarations and bindings are inconsistent")


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True, allow_inf_nan=False)


class ParameterBase(ContractModel):
    key: ParameterKey
    required: bool = True
    description: str = ""


class ConfigParameter(ParameterBase):
    kind: Literal["config"] = "config"
    value_type: Literal["string", "integer", "number", "boolean"] = "string"

    @model_validator(mode="after")
    def public_configuration_only(self) -> Self:
        if re.search(r"(^|_)(password|passwd|secret|token|cookie|cookies|session|authorization|credential|credentials)(_|$)", self.key) or self.key in {"api_key", "api_hash", "username", "email", "login"}:
            _invalid()
        return self


class CredentialParameter(ParameterBase):
    kind: Literal["credential"] = "credential"


class RegistrationParameter(ParameterBase):
    kind: Literal["registration"] = "registration"
    registration_url: str

    @model_validator(mode="after")
    def public_registration_url(self) -> Self:
        _validate_public_link(self.registration_url)
        return self


Parameter = Annotated[ConfigParameter | CredentialParameter | RegistrationParameter, Field(discriminator="kind")]


class ProjectBindings(ContractModel):
    project_key: str = Field(min_length=1, pattern=r"^\S(?:.*\S)?$")
    config: dict[ParameterKey, ConfigValue] = Field(default_factory=dict)
    credential_refs: dict[ParameterKey, CredentialRef] = Field(default_factory=dict)
    registrations: dict[ParameterKey, Literal["pending", "approved", "denied"]] = Field(default_factory=dict)


class IntegrationConfiguration(ContractModel):
    framework_type: FrameworkType
    access_mode: AccessMode = "anonymous"
    license: str | None = None
    parameters: list[Parameter] = Field(default_factory=list)
    bindings: ProjectBindings

    @model_validator(mode="after")
    def consistent_bindings(self) -> Self:
        definitions = {p.key: p for p in self.parameters}
        if len(definitions) != len(self.parameters):
            _invalid()
        if self.access_mode != "anonymous" and not any(isinstance(p, CredentialParameter) and p.required for p in self.parameters):
            _invalid()
        groups = (("config", self.bindings.config), ("credential", self.bindings.credential_refs), ("registration", self.bindings.registrations))
        for kind, values in groups:
            if any(key not in definitions or definitions[key].kind != kind for key in values):
                _invalid()
        for key, value in self.bindings.config.items():
            parameter = definitions[key]
            if not isinstance(parameter, ConfigParameter):
                _invalid()
            accepted_types = {"string": (str,), "integer": (int,), "number": (int, float), "boolean": (bool,)}
            if type(value) not in accepted_types[parameter.value_type]:
                _invalid()
        return self

    def readiness(self) -> dict[str, object]:
        missing: list[str] = []
        for parameter in self.parameters:
            if not parameter.required:
                continue
            if parameter.kind == "config":
                value = self.bindings.config.get(parameter.key)
                present = value is not None and (not isinstance(value, str) or bool(value.strip()))
            elif parameter.kind == "credential":
                present = parameter.key in self.bindings.credential_refs
            else:
                present = self.bindings.registrations.get(parameter.key) == "approved"
            if not present:
                missing.append(parameter.key)
        return {
            "configuration_ready": not missing, "missing_parameters": missing,
            "credentials_verified": False, "registration_status_authority": "user_declared",
            "execution_available": False, "execution_blocker": "integration_runtime_not_connected",
        }


def _validate_public_link(value: str) -> None:
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
    except ValueError:
        valid = False
    if not valid:
        _invalid()


class IntegrationSpec(ContractModel):
    """A catalog entry; `to_mrw_item` is a pure export for MRW's existing writer."""

    item_key: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    name: str = Field(min_length=1, max_length=255, pattern=r"^\S(?:.*\S)?$")
    project_link: str
    source_scope: str = Field(min_length=1)
    execution_mode: ExecutionMode
    runner_ref: str = Field(min_length=1)
    integration: IntegrationConfiguration

    @model_validator(mode="after")
    def compatible_runner(self) -> Self:
        _validate_public_link(self.project_link)
        schemes = {
            "python_library": ("python-library://",), "cli_or_container": ("cli://", "container://"),
            "article_extractor": ("article-extractor://",), "rss_feed": ("https://", "http://", "rsshub://"),
            "sitemap": ("https://", "http://"), "http_api": ("https://", "http://"),
        }
        if not self.runner_ref.startswith(schemes[self.execution_mode]):
            _invalid()
        if self.runner_ref.startswith(("http://", "https://")):
            _validate_public_link(self.runner_ref)
        else:
            parsed = urlsplit(self.runner_ref)
            if not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
                _invalid()
        return self

    def to_mrw_item(self) -> dict[str, object]:
        return {
            "item_key": self.item_key, "name": self.name,
            "channel_key": "external_project.manifest", "enabled": False,
            "item_type": "user_defined", "params": {},
            "extra": {"external_project_manifest": {
                "contract_version": INTEGRATION_MANIFEST_VERSION,
                "item_key": self.item_key, "display_name": self.name,
                "project_link": self.project_link, "source_kind": self.integration.framework_type,
                "source_scope": self.source_scope, "execution_mode": self.execution_mode,
                "runner_ref": self.runner_ref,
                "integration": self.integration.model_dump(mode="json"),
            }},
        }
