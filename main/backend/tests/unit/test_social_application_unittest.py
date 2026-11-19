from __future__ import annotations

import re

import pytest
from functorial_kit import Failure

from app.services.ingest import social_application
from app.services.ingest.social_application import (
    SocialIngestApplicationService,
    try_parse_social_collect_result,
)
from mrw_functorial_kit.core.provider_port_failures import ingest_operation_failures

pytestmark = pytest.mark.unit


def _result() -> dict[str, object]:
    return {
        "inserted": 2,
        "skipped": 1,
        "links": ["https://example.test/one"],
        "material_type": "social_sentiment",
        "extraction_stats": {
            "enabled": True,
            "ok": 1,
            "empty": 0,
            "fallback": 1,
        },
    }


def test_collect_data_api_forwards_explicit_arguments_and_returns_native_dto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def collect(**kwargs: object) -> dict[str, object]:
        calls.append(dict(kwargs))
        return _result()

    monkeypatch.setattr(social_application, "collect_user_social_sentiment", collect)

    result = SocialIngestApplicationService().collect_data_api(
        keywords=["markets"],
        platforms=["reddit"],
        limit=7,
        enable_extraction=False,
        enable_subreddit_discovery=False,
        base_subreddits=["economics"],
    )

    assert calls == [
        {
            "keywords": ["markets"],
            "platforms": ["reddit"],
            "limit": 7,
            "enable_extraction": False,
            "enable_subreddit_discovery": False,
            "base_subreddits": ["economics"],
        }
    ]
    assert result == _result()


def _malformed_social_results() -> tuple[
    tuple[object, str, str, str, str],
    ...,
]:
    malformed_keys: dict[object, object] = dict(_result())
    malformed_keys[1] = "value"

    invalid_integer = _result()
    invalid_integer["inserted"] = True
    invalid_boolean = _result()
    invalid_boolean["extraction_stats"] = {
        "enabled": 1,
        "ok": 1,
        "empty": 0,
        "fallback": 1,
    }
    invalid_string = _result()
    invalid_string["material_type"] = 1
    invalid_list = _result()
    invalid_list["links"] = "https://example.test/not-a-list"
    invalid_list_item = _result()
    invalid_list_item["links"] = ["ok", 3]

    return (
        (
            [],
            "social collect result",
            "object",
            "list",
            "social collect result must be an object",
        ),
        (
            malformed_keys,
            "social collect result",
            "string keys",
            "int",
            "social collect result keys must be strings",
        ),
        (
            invalid_integer,
            "social collect result.inserted",
            "integer",
            "bool",
            "social collect result.inserted must be an integer",
        ),
        (
            invalid_boolean,
            "social collect result.extraction_stats.enabled",
            "boolean",
            "int",
            "social collect result.extraction_stats.enabled must be a boolean",
        ),
        (
            invalid_string,
            "social collect result.material_type",
            "string",
            "int",
            "social collect result.material_type must be a string",
        ),
        (
            invalid_list,
            "social collect result.links",
            "list",
            "str",
            "social collect result.links must be a list",
        ),
        (
            invalid_list_item,
            "social collect result.links[1]",
            "string",
            "int",
            "social collect result.links[1] must be a string",
        ),
    )


def test_social_collect_result_parser_classifies_all_malformed_branches() -> None:
    for value, path, expected_type, actual_type, message in _malformed_social_results():
        failure = try_parse_social_collect_result(value)

        assert isinstance(failure, Failure)
        assert ingest_operation_failures.matches(failure)
        assert failure.code == "social_collect_result_invalid"
        assert failure.message == message
        assert failure.context == {
            "owner": "ingest.social_application.result_parser",
            "operation": "parse_social_collect_result",
            "path": path,
            "expected_type": expected_type,
            "actual_type": actual_type,
            "public_exception": "TypeError",
            "public_message": message,
            "witness": "test:test_social_collect_result_parser_classifies_all_malformed_branches",
        }


def test_social_collect_result_parser_preserves_type_error_abi_and_cause() -> None:
    for value, _path, _expected_type, _actual_type, message in _malformed_social_results():
        with pytest.raises(TypeError, match=f"^{re.escape(message)}$") as captured:
            social_application._social_collect_result(value)

        assert isinstance(captured.value.__cause__, TypeError)
        assert str(captured.value.__cause__) == message


def test_collect_data_api_preserves_service_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("provider failure")

    def collect(**kwargs: object) -> dict[str, object]:
        raise failure

    monkeypatch.setattr(social_application, "collect_user_social_sentiment", collect)

    with pytest.raises(RuntimeError) as caught:
        SocialIngestApplicationService().collect_data_api(keywords=["markets"])

    assert caught.value is failure
