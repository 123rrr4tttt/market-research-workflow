from types import SimpleNamespace

from app.services.collect_runtime.delivery import observe_delivery, resource_compatibility


def test_worker_success_with_provider_waiting_is_not_delivery():
    result = SimpleNamespace(
        status="completed",
        provider_job_id="job-1",
        provider_type="scrapy",
        provider_status="waiting",
        meta={"terminal_readback": {"kind": "waiting", "attempt_ref": "job-1"}},
    )

    observed = observe_delivery(result)

    assert observed.state == "waiting"
    assert observed.worker_status == "completed"
    assert observed.provider_job_id == "job-1"


def test_delivery_requires_successful_worker_and_terminal_readback():
    successful = SimpleNamespace(
        status="completed",
        provider_job_id="job-ok",
        meta={"terminal_readback": {"kind": "terminal", "readback": {
            "provider_job_id": "job-ok", "terminal_status": "completed",
        }}},
    )
    no_readback = SimpleNamespace(status="completed", meta={})
    worker_failed = SimpleNamespace(
        status="failed",
        provider_job_id="job-2",
        meta={"terminal_readback": {"kind": "waiting"}},
    )

    assert observe_delivery(successful).state == "delivered"
    assert observe_delivery(no_readback).state == "unknown"
    assert observe_delivery(worker_failed).state == "waiting"


def test_source_library_nested_terminal_readback_is_preserved():
    result = SimpleNamespace(
        status="completed",
        meta={
            "terminal_readback": {
                "kind": "terminal",
                "readback": {"provider_job_id": "job-cancel", "terminal_status": "cancelled"},
            }
        },
        provider_job_id="job-cancel",
    )

    observed = observe_delivery(result)

    assert observed.state == "cancelled"
    assert observed.readback_status == "cancelled"
    assert observed.readback_job_id == "job-cancel"
    assert observed.identity_match is True


def test_resource_compatibility_requires_more_than_distinct_concurrency_keys():
    a = SimpleNamespace(provider_concurrency_key="provider-a")
    same = SimpleNamespace(provider_concurrency_key="provider-a")
    other = SimpleNamespace(provider_concurrency_key="provider-b")
    unspecified = SimpleNamespace(provider_concurrency_key=None)

    assert resource_compatibility(a, same) == "conflict"
    assert resource_compatibility(a, other) == "unknown"
    assert resource_compatibility(a, unspecified) == "unknown"


def test_provider_terminal_and_target_delivery_are_separate():
    result = SimpleNamespace(
        status="completed",
        provider_job_id="job-1",
        provider_type="scrapy",
        provider_status="completed",
        meta={"terminal_readback": {"kind": "terminal", "readback": {
            "provider_job_id": "job-1", "terminal_status": "completed",
        }}},
    )

    provider = observe_delivery(result)
    material = observe_delivery(result, expected_delivery="material")

    assert provider.provider_state == provider.state == "delivered"
    assert material.provider_state == "delivered"
    assert material.state == "unknown"


def test_terminal_readback_job_id_must_match_the_dispatch_record():
    result = SimpleNamespace(
        status="completed",
        provider_job_id="job-1",
        provider_status="completed",
        meta={"terminal_readback": {"kind": "terminal", "readback": {
            "provider_job_id": "job-2", "terminal_status": "completed",
        }}},
    )
    assert observe_delivery(result).provider_state == "unknown"
    assert observe_delivery(result).identity_match is False
    assert observe_delivery(result).readback_job_id == "job-2"
    result.meta["terminal_readback"]["readback"].pop("provider_job_id")
    assert observe_delivery(result).provider_state == "unknown"
    assert observe_delivery(result).identity_match is None


def test_worker_failure_or_revocation_without_effect_readback_is_unknown():
    failed = SimpleNamespace(status="failed", provider_job_id=None, meta={})
    revoked = SimpleNamespace(status="cancelled", provider_job_id=None, meta={})
    assert observe_delivery(failed).provider_state == "unknown"
    assert observe_delivery(revoked).provider_state == "unknown"
