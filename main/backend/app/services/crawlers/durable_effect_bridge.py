"""Durable attempt bridge for legacy crawler providers.

The bridge deliberately knows nothing about a database.  A caller injects a
repository implementing :class:`CrawlerAttemptStore`; the repository is the
authority for idempotency, attempts, readback and cancellation receipts.  The
small in-memory implementation is useful for deterministic tests and is
durable for as long as its owner keeps it alive (it is never a module cache).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, NoReturn, Protocol

from functorial_kit import Failure
from mrw_functorial_kit.core.provider_port_failures import crawler_runtime_failures

from app.successor_runtime.capabilities.source_contracts import (
    CancelReceipt,
    ProviderAttemptRef,
    ProviderReadbackResult,
    SourcePlainObject,
)

from .base import (
    CrawlerCancelPort,
    CrawlerDispatchRequest,
    CrawlerDispatchResult,
    CrawlerJsonObject,
    CrawlerProvider,
    crawler_request_digest,
    typed_crawler_readback,
)


@dataclass(frozen=True, slots=True)
class CrawlerAttemptRecord:
    provider: str
    idempotency_key: str
    request_digest: str
    attempt_id: str
    request: CrawlerDispatchRequest
    dispatch: CrawlerDispatchResult | None = None
    terminal_readback: ProviderReadbackResult | None = None
    cancel_receipt: CancelReceipt | None = None

    @property
    def attempt_ref(self) -> ProviderAttemptRef:
        """Materialize the canonical C2.3 attempt reference on demand."""

        return ProviderAttemptRef(
            attempt_id=self.attempt_id,
            request_digest=self.request_digest,
            provider=self.provider,
        )

    @property
    def terminal(self) -> bool:
        if self.cancel_receipt is not None:
            return True
        if self.terminal_readback is not None:
            return self.terminal_readback.to_plain().get("kind") == "terminal"
        # A provider label such as ``completed`` is only an observation.  The
        # C2.3 terminal proof is the typed authoritative readback (or cancel
        # receipt), which must survive the bridge boundary.
        return False


class CrawlerAttemptStore(Protocol):
    """Repository contract used by :class:`DurableCrawlerEffectBridge`."""

    def reserve(
        self,
        request: CrawlerDispatchRequest,
    ) -> CrawlerAttemptRecord | Failure | None:
        """Return a reservation or its already-lifted closed failure."""

    def save_dispatch(self, record: CrawlerAttemptRecord, dispatch: CrawlerDispatchResult) -> CrawlerAttemptRecord:
        ...

    def save_readback(
        self,
        record: CrawlerAttemptRecord,
        readback: ProviderReadbackResult,
    ) -> CrawlerAttemptRecord:
        ...

    def save_cancel(
        self,
        record: CrawlerAttemptRecord,
        receipt: CancelReceipt,
    ) -> CrawlerAttemptRecord:
        ...

    def find_by_job_id(self, provider: str, provider_job_id: str) -> CrawlerAttemptRecord | None:
        ...


class InMemoryCrawlerAttemptStore:
    """Explicitly injected durable fake; no process-global state is used."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], CrawlerAttemptRecord] = {}

    def reserve(self, request: CrawlerDispatchRequest) -> CrawlerAttemptRecord | Failure | None:
        key = (str(request.provider).strip().lower(), str(request.idempotency_key or ""))
        current = self._records.get(key)
        if current is not None:
            if current.request_digest != str(request.request_digest):
                return _failure(
                    "request_digest_mismatch",
                    "idempotency key is bound to a different request digest",
                    idempotency_key=request.idempotency_key,
                )
            if current.attempt_id != str(request.attempt_id or ""):
                return _failure(
                    "request_digest_mismatch",
                    "idempotency key is bound to a different attempt id",
                    idempotency_key=request.idempotency_key,
                )
            return current
        record = CrawlerAttemptRecord(
            provider=request.provider,
            idempotency_key=str(request.idempotency_key or ""),
            request_digest=str(request.request_digest or ""),
            attempt_id=str(request.attempt_id or request.request_digest or ""),
            request=request,
        )
        self._records[key] = record
        return record

    def save_dispatch(self, record: CrawlerAttemptRecord, dispatch: CrawlerDispatchResult) -> CrawlerAttemptRecord:
        updated = replace(record, dispatch=dispatch)
        self._records[(record.provider.lower(), record.idempotency_key)] = updated
        return updated

    def save_readback(
        self,
        record: CrawlerAttemptRecord,
        readback: ProviderReadbackResult,
    ) -> CrawlerAttemptRecord:
        updated = replace(record, terminal_readback=readback)
        self._records[(record.provider.lower(), record.idempotency_key)] = updated
        return updated

    def save_cancel(
        self,
        record: CrawlerAttemptRecord,
        receipt: CancelReceipt,
    ) -> CrawlerAttemptRecord:
        updated = replace(record, cancel_receipt=receipt)
        self._records[(record.provider.lower(), record.idempotency_key)] = updated
        return updated

    def find_by_job_id(self, provider: str, provider_job_id: str) -> CrawlerAttemptRecord | None:
        provider = str(provider).strip().lower()
        return next(
            (record for (bound_provider, _), record in self._records.items()
             if bound_provider == provider and record.dispatch is not None
             and record.dispatch.provider_job_id == provider_job_id),
            None,
        )


class RequestDigestMismatch(ValueError):
    pass


def _failure(
    code: str,
    message: str,
    *,
    public_exception: str = "RuntimeError",
    **details: object,
) -> Failure:
    reason_code = code
    if code not in crawler_runtime_failures.codes:
        code = (
            "scrapyd_response_invalid"
            if "digest" in reason_code or "identity" in reason_code
            else "scrapyd_transport"
        )
        details.setdefault("reason_code", reason_code)
    context: dict[str, object] = {
        "boundary_class": "PURE_CONTRACT_FAILURE",
        "failure_family": crawler_runtime_failures.name,
        "operation": "crawlers.durable_effect_bridge",
        "owner": "app.services.crawlers.durable_effect_bridge",
        "public_exception": public_exception,
        "public_message": message,
        "site": "app.services.crawlers.durable_effect_bridge",
        "witness": "test:test_crawler_failure_lifts",
    }
    context.update(details)
    return crawler_runtime_failures.fail(code, message, context)


def _raise_contract_failure(failure: Failure, *, cause: BaseException | None = None) -> NoReturn:
    """Preserve the bridge's public ValueError ABI at one explicit lift."""

    context = failure.context or {}
    message = str(context.get("public_message", failure.message))
    # kit:boundary owner=crawlers.durable_effect_bridge.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=crawler.runtime.failure witness=test:test_crawler_failure_lifts
    raise ValueError(message) from cause


def _cancel_status(value: object) -> Literal["CANCEL_ACCEPTED", "ALREADY_TERMINAL"] | None:
    if value == "CANCEL_ACCEPTED":
        return "CANCEL_ACCEPTED"
    if value == "ALREADY_TERMINAL":
        return "ALREADY_TERMINAL"
    return None


class DurableCrawlerEffectBridge:
    """Bind legacy dispatch/poll/cancel operations to an injected store."""

    def __init__(
        self,
        *,
        provider: CrawlerProvider,
        store: CrawlerAttemptStore | None,
        cancel_port: CrawlerCancelPort | None = None,
    ) -> None:
        if store is None:
            _raise_contract_failure(
                _failure(
                    "scrapyd_response_invalid",
                    "durable crawler bridge requires an injected attempt store",
                    public_exception="ValueError",
                    reason_code="attempt_store_required",
                )
            )
        self.provider = provider
        self.store = store
        self.cancel_port = cancel_port

    def _validate_request(self, request: CrawlerDispatchRequest) -> Failure | None:
        expected = crawler_request_digest(request)
        if str(request.request_digest or "") != expected:
            return _failure(
                "request_digest_mismatch",
                "crawler request digest does not match canonical request content",
                request_digest=request.request_digest,
                expected_digest=expected,
                idempotency_key=request.idempotency_key,
            )
        if not request.idempotency_key or not request.attempt_id:
            return _failure("attempt_identity_required", "crawler request requires idempotency_key and attempt_id")
        return None

    def dispatch(self, request: CrawlerDispatchRequest) -> CrawlerDispatchResult | Failure:
        invalid = self._validate_request(request)
        if invalid is not None:
            return invalid
        try:
            record = self.store.reserve(request)
        except RequestDigestMismatch as exc:
            return _failure("request_digest_mismatch", str(exc), idempotency_key=request.idempotency_key)
        except Exception as exc:  # repository boundary
            return _failure("attempt_store_unavailable", f"crawler attempt store reserve failed: {exc}")
        if isinstance(record, Failure):
            return record
        if record is not None and record.dispatch is not None:
            if not record.terminal and record.dispatch.provider_job_id:
                # Reconciliation is readback-only: an existing attempt may be
                # polled again after a process restart, but it is never
                # dispatched a second time.
                self.reconcile(request)
                try:
                    refreshed = self.store.reserve(request)
                    if isinstance(refreshed, Failure):
                        return refreshed
                    if refreshed is not None:
                        record = refreshed
                except Exception as exc:
                    return _failure(
                        "attempt_store_unavailable",
                        f"crawler attempt store replay readback failed: {exc}",
                    )
            persisted_dispatch = record.dispatch
            if persisted_dispatch is None:
                return _failure(
                    "attempt_store_unavailable",
                    "crawler attempt store lost the persisted dispatch",
                )
            return self._with_readback(
                persisted_dispatch,
                record.terminal_readback,
                idempotency_key=request.idempotency_key,
                attempt_id=request.attempt_id,
            )
        try:
            dispatch = self.provider.dispatch(request)
        except Exception as exc:  # provider effect boundary
            return _failure("scrapyd_transport", f"crawler provider dispatch failed: {exc}", cause=exc)
        if isinstance(dispatch, Failure):
            return dispatch
        try:
            if record is None:
                record = self.store.reserve(request)
            if isinstance(record, Failure):
                return record
            if record is None:
                return _failure("attempt_store_unavailable", "crawler attempt store did not return a reserved record")
            record = self.store.save_dispatch(record, dispatch)
        except Exception as exc:
            return _failure("attempt_store_unavailable", f"crawler attempt store dispatch write failed: {exc}")
        if record.terminal_readback is None and dispatch.provider_job_id:
            try:
                payload = self.provider.poll(
                    external_job_id=dispatch.provider_job_id,
                    project=request.project,
                    spider=request.spider,
                    options={"idempotency_key": request.idempotency_key, "attempt_id": request.attempt_id},
                )
                readback = typed_crawler_readback(
                    attempt_id=record.attempt_id,
                    provider_job_id=dispatch.provider_job_id,
                    payload=payload,
                )
                record = self.store.save_readback(record, readback)
            except Exception as exc:
                readback = typed_crawler_readback(
                    attempt_id=record.attempt_id,
                    provider_job_id=dispatch.provider_job_id,
                    payload={"status": "unknown", "reason": f"crawler provider poll failed: {exc}"},
                )
                try:
                    record = self.store.save_readback(record, readback)
                except Exception as store_exc:
                    return _failure(
                        "attempt_store_unavailable",
                        f"crawler attempt store readback write failed: {store_exc}",
                    )
        return self._with_readback(
            dispatch,
            record.terminal_readback,
            idempotency_key=request.idempotency_key,
            attempt_id=request.attempt_id,
        )

    @staticmethod
    def _with_readback(
        dispatch: CrawlerDispatchResult,
        readback: ProviderReadbackResult | None,
        *,
        idempotency_key: str | None = None,
        attempt_id: str | None = None,
    ) -> CrawlerDispatchResult:
        return replace(
            dispatch,
            terminal_readback=readback,
            idempotency_key=idempotency_key or dispatch.idempotency_key,
            attempt_id=attempt_id or dispatch.attempt_id,
        )

    def poll(
        self,
        *,
        external_job_id: str,
        project: str | None = None,
        spider: str | None = None,
        options: CrawlerJsonObject | None = None,
    ) -> SourcePlainObject | Failure:
        provider = self.provider.provider_type
        record = self.store.find_by_job_id(provider, external_job_id)
        if record is None:
            return _failure(
                "attempt_not_found",
                "crawler attempt is not bound to provider job",
                provider_job_id=external_job_id,
            )
        if record.terminal_readback is not None:
            plain = record.terminal_readback.to_plain()
            if plain.get("kind") == "terminal":
                return plain
        try:
            payload = self.provider.poll(
                external_job_id=external_job_id,
                project=project or record.request.project,
                spider=spider or record.request.spider,
                options=dict(options or {}),
            )
            readback = typed_crawler_readback(
                attempt_id=record.attempt_id,
                provider_job_id=external_job_id,
                payload=payload,
            )
            self.store.save_readback(record, readback)
            return readback.to_plain()
        except Exception as exc:
            readback = typed_crawler_readback(
                attempt_id=record.attempt_id,
                provider_job_id=external_job_id,
                payload={"status": "unknown", "reason": f"crawler provider poll failed: {exc}"},
            )
            try:
                self.store.save_readback(record, readback)
            except Exception as store_exc:
                return _failure(
                    "attempt_store_unavailable",
                    f"crawler attempt store readback write failed: {store_exc}",
                )
            plain = readback.to_plain()
            return plain

    def reconcile(
        self,
        request: CrawlerDispatchRequest,
    ) -> ProviderReadbackResult | SourcePlainObject | Failure:
        """Read back an existing attempt without ever dispatching it again."""

        invalid = self._validate_request(request)
        if invalid is not None:
            return invalid
        try:
            record = self.store.reserve(request)
        except RequestDigestMismatch as exc:
            return _failure("request_digest_mismatch", str(exc), idempotency_key=request.idempotency_key)
        if isinstance(record, Failure):
            return record
        if record is None or record.dispatch is None or not record.dispatch.provider_job_id:
            return _failure("attempt_not_found", "crawler attempt has no provider job for readback")
        if record.terminal_readback is not None:
            if record.terminal_readback.to_plain().get("kind") == "terminal":
                return record.terminal_readback
        result = self.poll(
            external_job_id=record.dispatch.provider_job_id,
            project=request.project,
            spider=request.spider,
            options={"idempotency_key": request.idempotency_key, "attempt_id": request.attempt_id},
        )
        return result

    readback = reconcile

    def cancel(self, request: CrawlerDispatchRequest) -> CancelReceipt | Failure:
        invalid = self._validate_request(request)
        if invalid is not None:
            return invalid
        try:
            record = self.store.reserve(request)
        except RequestDigestMismatch as exc:
            return _failure("request_digest_mismatch", str(exc), idempotency_key=request.idempotency_key)
        if isinstance(record, Failure):
            return record
        if record is None or record.dispatch is None:
            return _failure("attempt_not_found", "crawler attempt has not been dispatched")
        if record.cancel_receipt is not None:
            return record.cancel_receipt
        if record.terminal:
            try:
                attempt = ProviderAttemptRef(
                    attempt_id=record.attempt_id,
                    request_digest=record.request_digest,
                    provider=record.provider,
                )
                receipt = CancelReceipt(
                    cancel_receipt_id=f"cancel:crawler:{record.attempt_id}:terminal",
                    attempt_ref=attempt.as_ref_string(),
                    request_digest=record.request_digest,
                    cancel_status="ALREADY_TERMINAL",
                )
                self.store.save_cancel(record, receipt)
                return receipt
            except Exception as exc:
                return _failure("cancel_failed", f"could not create terminal cancellation receipt: {exc}")
        cancel_candidate: object = self.cancel_port or self.provider
        if not isinstance(cancel_candidate, CrawlerCancelPort):
            return _failure(
                "provider_cancel_unsupported",
                f"crawler provider does not support cancel(): {record.provider}",
            )
        try:
            attempt = ProviderAttemptRef(
                attempt_id=record.attempt_id,
                request_digest=record.request_digest,
                provider=record.provider,
            )
            raw = cancel_candidate.cancel(
                attempt_ref=attempt,
                request=request,
                external_job_id=record.dispatch.provider_job_id,
                project=request.project,
                spider=request.spider,
            )
            if isinstance(raw, CancelReceipt):
                receipt = raw
            elif isinstance(raw, Failure):
                return raw
            else:
                raw_status = raw.get("cancel_status") or "CANCEL_ACCEPTED"
                cancel_status = _cancel_status(raw_status)
                if cancel_status is None:
                    return _failure(
                        "cancel_failed",
                        f"crawler provider returned unsupported cancellation status: {raw_status}",
                    )
                receipt = CancelReceipt(
                    cancel_receipt_id=str(
                        raw.get("cancel_receipt_id")
                        or f"cancel:crawler:{record.attempt_id}"
                    ),
                    attempt_ref=attempt.as_ref_string(),
                    request_digest=record.request_digest,
                    cancel_status=cancel_status,
                )
            if receipt.request_digest != record.request_digest or receipt.attempt_ref != attempt.as_ref_string():
                return _failure(
                    "cancel_failed",
                    "crawler provider returned a cancellation receipt bound to a different attempt",
                )
            self.store.save_cancel(record, receipt)
            return receipt
        except Exception as exc:
            return _failure("cancel_failed", f"crawler provider cancellation failed: {exc}")


__all__ = [
    "CrawlerAttemptRecord",
    "CrawlerAttemptStore",
    "DurableCrawlerEffectBridge",
    "InMemoryCrawlerAttemptStore",
    "RequestDigestMismatch",
    "crawler_request_digest",
]
