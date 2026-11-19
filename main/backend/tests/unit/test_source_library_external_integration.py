from contextlib import nullcontext
from copy import deepcopy
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.services.source_library.external_integration import IntegrationSpec
from app.services.source_library.external_project import (
    build_external_project_summary, get_external_project_manifest,
    normalize_external_project_extra, normalize_external_project_manifest,
)
from app.services.source_library.adapters.external_project import handle_external_project_manifest
from app.services.source_library.item_plan import build_item_query_readiness
from app.services.source_library import item_writer


def spec_payload(access_mode="anonymous"):
    parameters = [] if access_mode == "anonymous" else [{"kind": "credential", "key": "access"}]
    return {
        "item_key": "social.demo", "name": "Demo", "project_link": "https://example.com/demo",
        "source_scope": "social", "execution_mode": "python_library", "runner_ref": "python-library://demo",
        "integration": {"framework_type": "api_client", "access_mode": access_mode, "parameters": parameters,
                        "bindings": {"project_key": "organization-investigation"}},
    }


@pytest.fixture(autouse=True)
def no_real_dns():
    with patch("app.services.source_library.external_project.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
        yield


@pytest.mark.parametrize("mode", ["anonymous", "api_key", "oauth2", "account_login", "session"])
def test_integration_contract(mode):
    payload = spec_payload(mode)
    spec = IntegrationSpec.model_validate(payload)
    assert spec.integration.readiness()["configuration_ready"] == (mode == "anonymous")
    if mode != "anonymous":
        payload["integration"]["bindings"]["credential_refs"] = {"access": "env:SOCIAL_ACCESS"}
        spec = IntegrationSpec.model_validate(payload)
    ready = spec.integration.readiness()
    assert ready["configuration_ready"] is True
    assert ready["credentials_verified"] is False
    assert ready["execution_available"] is False
    assert IntegrationSpec.model_validate_json(spec.model_dump_json()) == spec


def test_registration_and_typed_config_are_independent_requirements():
    payload = spec_payload("api_key")
    integration = payload["integration"]
    integration["parameters"] += [
        {"kind": "registration", "key": "developer_app", "registration_url": "https://example.com/developers"},
        {"kind": "config", "key": "api_id", "value_type": "integer"},
        {"kind": "config", "key": "optional", "required": False},
    ]
    integration["bindings"].update(credential_refs={"access": "env:API_KEY"}, config={"api_id": 123}, registrations={"developer_app": "pending"})
    ready = IntegrationSpec.model_validate(payload).integration.readiness()
    assert ready["missing_parameters"] == ["developer_app"]
    integration["bindings"]["registrations"]["developer_app"] = "approved"
    assert IntegrationSpec.model_validate(payload).integration.readiness()["configuration_ready"]
    for bad in [True, "123", 1.2]:
        integration["bindings"]["config"]["api_id"] = bad
        with pytest.raises(ValidationError):
            IntegrationSpec.model_validate(payload)


@pytest.mark.parametrize("case", ["duplicate", "unknown", "raw_secret", "wrong_kind", "secret_config", "unbound_auth", "extra", "runner", "url_secret"])
def test_invalid_bindings_do_not_echo_values(case):
    payload = spec_payload("session")
    integration = payload["integration"]
    if case == "duplicate":
        integration["parameters"] *= 2
    elif case == "unknown":
        integration["bindings"]["config"] = {"unknown": "sensitive-sentinel"}
    elif case == "raw_secret":
        integration["bindings"]["credential_refs"] = {"access": "sensitive-sentinel"}
    elif case == "wrong_kind":
        integration["bindings"]["config"] = {"access": "sensitive-sentinel"}
    elif case == "secret_config":
        integration["parameters"].append({"kind": "config", "key": "api_key"})
    elif case == "unbound_auth":
        integration["parameters"] = []
    elif case == "extra":
        integration["bindings"]["password"] = "sensitive-sentinel"
    elif case == "runner":
        payload["runner_ref"] = "cli://demo"
    else:
        payload["project_link"] = "https://example.com/?token=sensitive-sentinel"
    with pytest.raises(ValidationError) as exc:
        IntegrationSpec.model_validate(payload)
    assert "sensitive-sentinel" not in str(exc.value)


def test_mrw_normalization_preserves_spec_and_v1_compatibility():
    spec = IntegrationSpec.model_validate(spec_payload("session"))
    item = spec.to_mrw_item()
    normalized = normalize_external_project_extra(item["extra"], item_key=spec.item_key, display_name=spec.name,
                                                  channel_key=item["channel_key"], project_key="organization-investigation")
    manifest = get_external_project_manifest(normalized)
    assert manifest["integration"] == spec.integration.model_dump(mode="json")
    assert normalize_external_project_manifest(manifest) == manifest
    assert build_external_project_summary(manifest)["integration_readiness"] == spec.integration.readiness()
    v1 = deepcopy(manifest)
    v1["contract_version"] = "external_item.manifest.v1"
    with pytest.raises(ValueError, match="require.*v2"):
        normalize_external_project_manifest(v1)
    del v1["integration"]
    assert normalize_external_project_manifest(v1)["contract_version"] == "external_item.manifest.v1"
    with pytest.raises(ValueError, match="target project"):
        normalize_external_project_extra(normalized, item_key=spec.item_key, display_name=spec.name,
                                         channel_key=item["channel_key"], project_key="another-project")


def test_v2_rejects_opaque_runtime_and_malformed_integration_without_secret_echo():
    manifest = IntegrationSpec.model_validate(spec_payload()).to_mrw_item()["extra"]["external_project_manifest"]
    manifest["runtime_config"] = {"json_body": {"token": "sensitive-sentinel"}}
    with pytest.raises(ValueError, match="declared integration bindings") as exc:
        normalize_external_project_manifest(manifest)
    assert "sensitive-sentinel" not in str(exc.value)
    del manifest["runtime_config"]
    manifest["integration"]["bindings"]["credential_refs"] = {"unknown": "sensitive-sentinel"}
    with pytest.raises(ValueError, match="specification is invalid") as exc:
        normalize_external_project_manifest(manifest)
    assert "sensitive-sentinel" not in str(exc.value)


def test_v2_never_dispatches_or_resolves_dns_even_if_enabled():
    item = IntegrationSpec.model_validate(spec_payload()).to_mrw_item()
    item["enabled"] = True
    with patch("app.services.source_library.adapters.external_project.get_external_project_manifest") as normalizer:
        with patch("app.services.source_library.adapters.external_project._RUNNER_BY_PROVIDER_KEY", {"external_project.python_library": Mock()}) as runners:
            with pytest.raises(ValueError, match="integration_runtime_not_connected"):
                handle_external_project_manifest({"_source_library_item": item}, "organization-investigation")
            normalizer.assert_not_called()
            runners["external_project.python_library"].assert_not_called()
    assert build_item_query_readiness(item)["status"] == "blocked"


def test_export_consumed_by_original_writer_and_read_back(monkeypatch):
    """Real writer/normalizer/SQLAlchemy row, replacing only database boundary."""
    session = Mock()
    session.execute.return_value.scalar_one_or_none.return_value = None
    monkeypatch.setattr(item_writer, "require_project_key", lambda key: key)
    monkeypatch.setattr(item_writer, "bind_project", lambda key: nullcontext())
    monkeypatch.setattr(item_writer, "SessionLocal", lambda: nullcontext(session))
    spec = IntegrationSpec.model_validate(spec_payload("account_login"))
    payload = item_writer.SourceLibraryItemUpsertPayload.model_validate(spec.to_mrw_item())
    result = item_writer.upsert_project_item(payload=payload, project_key=spec.integration.bindings.project_key)
    assert result["status"] == "ok"
    assert result["data"]["query_readiness"]["status"] == "blocked"
    row = session.add.call_args.args[0]
    assert get_external_project_manifest(row.extra)["integration"] == spec.integration.model_dump(mode="json")
    assert row.enabled is False
    session.commit.assert_called_once()
    session.reset_mock()
    with pytest.raises(HTTPException):
        item_writer.upsert_project_item(payload=payload, project_key="another-project")
    session.execute.assert_not_called()


def test_prepare_api_is_static_project_bound_and_redacts_invalid_input():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.source_library import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        assert client.get("/api/v1/source_library/external-projects/integration-schema").json()["data"]["title"] == "IntegrationSpec"
        url = "/api/v1/source_library/external-projects/prepare-integration?project_key=organization-investigation"
        with patch("app.api.source_library.synthesize_external_project_item") as synthesis:
            with patch("app.api.source_library._write_project_item") as writer:
                response = client.post(url, json=spec_payload())
                assert response.status_code == 200
                data = response.json()["data"]
                assert data["persisted"] is False
                assert data["readiness"]["execution_available"] is False
                assert get_external_project_manifest(data["item"]["extra"])["contract_version"] == "external_item.manifest.v2"
                synthesis.assert_not_called()
                writer.assert_not_called()
        payload = spec_payload("session")
        payload["integration"]["bindings"]["credential_refs"] = {"access": "sensitive-sentinel"}
        response = client.post(url, json=payload)
        assert response.status_code == 422
        assert "sensitive-sentinel" not in response.text
        assert client.post(url.replace("organization-investigation", "another-project"), json=spec_payload()).status_code == 422
        assert client.post(url, content='{"broken":"sensitive-sentinel"').status_code == 422
