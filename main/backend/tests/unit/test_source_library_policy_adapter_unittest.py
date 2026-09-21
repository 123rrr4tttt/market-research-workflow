from __future__ import annotations

from app.services.source_library.adapters import policy


def test_policy_adapter_keeps_extraction_unrequested_by_default(monkeypatch) -> None:
    captured = {}

    def fake_ingest(**kwargs):
        captured.update(kwargs)
        return {"inserted": 0, "extraction": {"requested": False}}

    monkeypatch.setattr(
        "app.services.ingest.policy.ingest_policy_documents", fake_ingest
    )

    result = policy.handle_policy({"state": "CA"}, "project")

    assert result["extraction"]["requested"] is False
    assert captured == {
        "state": "CA",
        "source_hint": None,
        "enable_extraction": False,
        "max_documents": None,
        "cancel_check": None,
        "request_id": None,
        "idempotency_key": None,
    }


def test_policy_adapter_projects_extraction_bound_identity_and_cancel_hook(monkeypatch) -> None:
    captured = {}

    def fake_ingest(**kwargs):
        captured.update(kwargs)
        return {"inserted": 1, "extraction": {"requested": True}}

    monkeypatch.setattr(
        "app.services.ingest.policy.ingest_policy_documents", fake_ingest
    )
    cancel_check = lambda index: index > 2

    policy.handle_policy(
        {
            "state": "ny",
            "source_hint": "fixture",
            "extraction": {"requested": True},
            "max_documents": "3",
            "request_identity": {
                "request_id": "req-policy-1",
                "idempotency_key": "idem-policy-1",
            },
            "cancellation": {"check": cancel_check, "safe": True},
        },
        None,
    )

    assert captured["state"] == "ny"
    assert captured["source_hint"] == "fixture"
    assert captured["enable_extraction"] is True
    assert captured["max_documents"] == 3
    assert captured["request_id"] == "req-policy-1"
    assert captured["idempotency_key"] == "idem-policy-1"
    assert captured["cancel_check"] is cancel_check


def test_policy_adapter_does_not_downgrade_explicit_extraction_request(monkeypatch) -> None:
    captured = {}

    def fake_ingest(**kwargs):
        captured.update(kwargs)
        return {"extraction": {"status": "FAILED"}}

    monkeypatch.setattr(
        "app.services.ingest.policy.ingest_policy_documents", fake_ingest
    )

    result = policy.handle_policy({"state": "CA", "enable_extraction": True}, None)

    assert captured["enable_extraction"] is True
    assert result["extraction"]["status"] == "FAILED"
