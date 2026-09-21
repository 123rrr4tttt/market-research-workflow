from __future__ import annotations

from pathlib import Path

import pytest
from functorial_kit import Failure
from mrw_functorial_kit.core.agent_service_semantics import (
    agent_functorial_projection_failures,
)

from app.services.agent_core.functorial import compose, motif, workflow
from app.services.agent_core.functorial.registry import CatalogLoadError, FunctorialCatalog


def _assert_failure(value: object, code: str) -> None:
    assert isinstance(value, Failure)
    assert agent_functorial_projection_failures.matches(value)
    assert value.code == code
    assert value.context is not None
    assert value.context["failure_family"] == agent_functorial_projection_failures.name
    assert value.context["owner"].startswith("agent_core.functorial.")


def test_w02_compose_invalid_step_is_closed_failure_and_public_lift() -> None:
    value = compose._flatten_steps(["bad-step"])
    _assert_failure(value, "composition_step_invalid")
    with pytest.raises(TypeError, match="composition step must be a dict"):
        compose.ordered_compose(["bad-step"])


@pytest.mark.parametrize(
    ("ref", "code"),
    (
        ("", "ref_empty"),
        ("operator:", "ref_id_missing"),
        ("operator:known", "ref_unresolved"),
        ("plain", "ref_invalid_format"),
        ("skill:known", "ref_kind_unsupported"),
    ),
)
def test_w02_motif_ref_producers_are_closed(
    monkeypatch: pytest.MonkeyPatch, ref: str, code: str
) -> None:
    monkeypatch.setattr(motif, "ensure_operator_catalog", lambda: None)
    monkeypatch.setattr(motif.catalog, "get", lambda *_: None)
    _assert_failure(motif._resolve_composition_ref(ref), code)


def test_w02_motif_id_compatibility_lift() -> None:
    with pytest.raises(ValueError, match="motif_id is required"):
        motif.compose_motif("", "ignored", [])


@pytest.mark.parametrize(
    ("steps", "code"),
    (
        (None, "workflow_steps_required"),
        ("operator:x", "workflow_steps_invalid_type"),
        (42, "workflow_steps_invalid_type"),
        ([], "workflow_steps_empty"),
        ([None], "workflow_step_invalid"),
        ([""], "ref_empty"),
        (["operator:"], "ref_id_missing"),
        (["operator"], "ref_invalid_format"),
        (["skill:x"], "ref_kind_unsupported"),
    ),
)
def test_w02_workflow_step_producers_are_closed(steps: object, code: str) -> None:
    value = workflow._build_workflow_program("wf", "WF", steps)
    _assert_failure(value, code)


def test_w02_workflow_compatibility_lift() -> None:
    with pytest.raises(workflow.WorkflowValidationError, match="workflow_id is required"):
        workflow.build_workflow_program("", "WF", ["operator:x"])


def test_w02_registry_malformed_record_and_ref_validation(tmp_path: Path) -> None:
    root = tmp_path / "functorial"
    root.mkdir()
    (root / "operators.jsonl").write_text("[]\n", encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="catalog record must be an object"):
        FunctorialCatalog(data_root=root)

    catalog = FunctorialCatalog(data_root=tmp_path / "other")
    _assert_failure(catalog._upsert("unknown", "id", {}), "ref_kind_unsupported")
    _assert_failure(catalog._upsert("operators", "", {}), "ref_id_missing")


def test_w02_functorial_projection_failure_lifts() -> None:
    wrong_family = Failure("other.family", "bad", "bad")
    with pytest.raises(TypeError, match="invalid functorial projection failure"):
        compose._raise_projection_failure(wrong_family, TypeError)
    with pytest.raises(TypeError, match="invalid functorial projection failure"):
        motif._raise_projection_failure(wrong_family, TypeError)
    with pytest.raises(TypeError, match="invalid functorial projection failure"):
        workflow._raise_projection_failure(wrong_family)
    from app.services.agent_core.functorial import registry

    with pytest.raises(TypeError, match="invalid functorial projection failure"):
        registry._raise_projection_failure(wrong_family, TypeError)

    compose_failure = compose._projection_failure("ref_empty", "bad")
    with pytest.raises(ValueError, match="^bad$"):
        compose._raise_projection_failure(compose_failure, ValueError)
    motif_failure = motif._projection_failure("ref_empty", "bad")
    with pytest.raises(ValueError, match="^bad$"):
        motif._raise_projection_failure(motif_failure, ValueError)
    workflow_failure = workflow._projection_failure("ref_empty", "bad")
    with pytest.raises(workflow.WorkflowValidationError, match="^bad$"):
        workflow._raise_projection_failure(workflow_failure)
    registry_failure = registry._projection_failure("ref_empty", "bad")
    with pytest.raises(CatalogLoadError, match="^bad$"):
        registry._raise_projection_failure(registry_failure, CatalogLoadError)
