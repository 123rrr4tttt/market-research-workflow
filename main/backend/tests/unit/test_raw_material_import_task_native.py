from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from typing import Any, cast
from unittest.mock import Mock, patch

from app.api.admin import (
    _dispatch_raw_material_import_async,  # pyright: ignore[reportPrivateUsage]
    _run_raw_material_import_sync,  # pyright: ignore[reportPrivateUsage]
)
from app.composition.raw_material_import_task import (
    RAW_MATERIAL_IMPORT_TASK_DEFINITION,
    RawMaterialImportTaskAssemblyContext,
    RawMaterialImportTaskBinding,
    compile_raw_material_import_task,
    raw_material_import_task_native,
    raw_material_import_task_native_catalog,
    validate_raw_material_import_task_binding,
)
from app.contracts.raw_material_import import RawImportItem, RawImportRequest
from celery import Celery
from functorial_kit import Failure
from functorial_kit.contribution_verification import (
    VerificationSource,
    plan_contribution_verification,
    register_verification_plan,
)
from functorial_kit.native_contribution import BindingRejected, NativeContribution


def _celery_context(app: Celery) -> RawMaterialImportTaskAssemblyContext:
    return RawMaterialImportTaskAssemblyContext(
        register_task=lambda name, run: app.task(name=name)(run),
        resolve_task=app.tasks.get,
    )


def _run_catalog_verification(
    catalog: tuple[NativeContribution[Any, Any, Any], ...],
) -> tuple[object, ...]:
    plan = plan_contribution_verification(tuple(
        VerificationSource(native.projection, native.verification)
        for native in catalog
    ))
    assert not isinstance(plan, Failure)
    registered: dict[str, object] = {}
    registration = register_verification_plan(
        plan,
        lambda name, callback: registered.setdefault(name, callback),
    )
    assert not isinstance(registration, Failure)
    for callback in registered.values():
        assert callable(callback)
        callback()
    report = registration.report()
    assert report.complete is True
    assert report.passed is True
    return tuple(registered)


def test_native_projection_and_verification_planning_are_inert() -> None:
    calls: list[str] = []

    def kernel(_payload: dict[str, object], project_key: str) -> dict[str, object]:
        calls.append(project_key)
        return {"project_key": project_key}

    definition = replace(
        RAW_MATERIAL_IMPORT_TASK_DEFINITION,
        task_name="test.tasks.inert_raw_material_import",
        kernel=kernel,
    )
    native = compile_raw_material_import_task(definition)
    assert not isinstance(native, Failure)
    assert native.definition is definition
    assert native.projection.id == definition.contribution_id
    task_object = next(
        item
        for item in native.projection.objects
        if item.kind == "ProjectBoundCeleryTask"
    )
    assert all(definition.contribution_id in ref for ref in task_object.references)
    assert calls == []

    registered = _run_catalog_verification((
        *raw_material_import_task_native_catalog,
        native,
    ))
    assert len(registered) == 3
    assert calls == []


def test_effective_native_catalog_drives_the_fixed_verification_runner() -> None:
    registered = _run_catalog_verification(raw_material_import_task_native_catalog)
    assert len(registered) == 2


def test_binding_validator_rejects_a_runner_from_another_definition() -> None:
    primary = replace(
        RAW_MATERIAL_IMPORT_TASK_DEFINITION,
        task_name="test.tasks.runner_validation_source",
    )
    alternative = replace(
        RAW_MATERIAL_IMPORT_TASK_DEFINITION,
        task_name="test.tasks.wrong_runner_source",
    )
    primary_native = compile_raw_material_import_task(primary)
    alternative_native = compile_raw_material_import_task(alternative)
    assert not isinstance(primary_native, Failure)
    assert not isinstance(alternative_native, Failure)

    app = Celery("raw-material-import-wrong-runner-test", broker="memory://")
    binding = primary_native.assemble(_celery_context(app))
    wrong_runner = alternative_native.assemble(_celery_context(app))
    assert not isinstance(binding, Failure)
    assert not isinstance(wrong_runner, Failure)
    forged = RawMaterialImportTaskBinding(
        definition=binding.definition,
        task=binding.task,
        run=wrong_runner.run,
        registry_owner=binding.registry_owner,
    )
    assert isinstance(
        validate_raw_material_import_task_binding(
            primary,
            forged,
        ),
        BindingRejected,
    )


def test_none_project_key_preserves_the_unbound_task_scope() -> None:
    calls: list[str] = []

    def kernel(_payload: dict[str, object], project_key: str) -> dict[str, object]:
        calls.append(project_key)
        return {"project_key": project_key}

    definition = replace(
        RAW_MATERIAL_IMPORT_TASK_DEFINITION,
        task_name="test.tasks.unbound_raw_material_import",
        kernel=kernel,
    )
    native = compile_raw_material_import_task(definition)
    assert not isinstance(native, Failure)
    app = Celery("raw-material-import-unbound-test", broker="memory://")
    with patch("app.composition.raw_material_import_task.bind_project") as bind:
        binding = native.assemble(_celery_context(app))
        assert not isinstance(binding, Failure)
        assert binding.run({}, None) == {"project_key": ""}
    bind.assert_not_called()
    assert calls == [""]


def test_nondefault_definition_drives_real_celery_and_admin_consumers() -> None:
    calls: list[tuple[dict[str, object], str]] = []

    def kernel(payload: dict[str, object], project_key: str) -> dict[str, object]:
        calls.append((payload, project_key))
        return {
            "source_name": str(payload.get("source_name") or ""),
            "project_key": project_key,
        }

    definition = replace(
        RAW_MATERIAL_IMPORT_TASK_DEFINITION,
        task_name="test.tasks.alternative_raw_material_import",
        kernel=kernel,
    )
    native = compile_raw_material_import_task(definition)
    assert not isinstance(native, Failure)
    assert any(
        definition.task_name in item.id
        for item in native.projection.objects
    )
    assert all(
        RAW_MATERIAL_IMPORT_TASK_DEFINITION.task_name not in item.id
        for item in native.projection.objects
    )

    app = Celery(
        "raw-material-import-native-test",
        broker="memory://",
        backend="cache+memory://",
    )
    app.conf.update(task_always_eager=True, task_store_eager_result=True)
    with patch(
        "app.composition.raw_material_import_task.bind_project",
        return_value=nullcontext(),
    ) as bind:
        binding = native.assemble(_celery_context(app))
        assert not isinstance(binding, Failure)
        assert binding.task is app.tasks[definition.task_name]

        request = RawImportRequest(
            items=[RawImportItem(text="native task input")],
            source_name="alternative",
            async_mode=True,
        )
        sync_result = _run_raw_material_import_sync(
            definition,
            request,
            "project_sync",
        )
        async_result = _dispatch_raw_material_import_async(
            binding,
            request,
            "project_async",
        )

    assert sync_result == {
        "source_name": "alternative",
        "project_key": "project_sync",
    }
    assert cast(Any, async_result).get(timeout=1) == {
        "source_name": "alternative",
        "project_key": "project_async",
    }
    assert [project_key for _payload, project_key in calls] == [
        "project_sync",
        "project_async",
    ]
    assert all(
        cast(list[dict[str, object]], payload["items"])[0]["text"]
        == "native task input"
        for payload, _ in calls
    )
    assert bind.call_args_list[0].args == ("project_sync",)
    assert bind.call_args_list[1].args == ("project_async",)


def test_wrong_registry_owner_fails_before_registration() -> None:
    register = Mock()
    context = RawMaterialImportTaskAssemblyContext(
        register_task=register,
        resolve_task=lambda _name: None,
        registry_owner="other.celery.registry",
    )
    result = raw_material_import_task_native.assemble(context)
    assert isinstance(result, Failure)
    register.assert_not_called()


def test_project_catalog_contains_the_same_native_projection_once() -> None:
    from contributions.project_catalog import project_contribution_catalog

    matches = tuple(
        item
        for item in project_contribution_catalog
        if item.id == raw_material_import_task_native.projection.id
    )
    assert matches == (raw_material_import_task_native.projection,)
