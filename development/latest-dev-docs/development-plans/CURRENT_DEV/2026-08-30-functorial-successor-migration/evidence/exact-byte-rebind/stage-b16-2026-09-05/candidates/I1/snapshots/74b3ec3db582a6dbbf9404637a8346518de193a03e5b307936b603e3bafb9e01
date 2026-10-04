"""C9 generalized sanctioned rollback identity pure regression tests.

A rollback receipt must bind the same exact generation/revision identity as
the active offset and the query snapshot for any persisted target generation.
The query snapshot exposes ``projection_revision == projection_generation``
and ``cursor == source_revision``; the receipt ``to`` position must match it
field-for-field or the frontend exact receipt/data binding rejects the
sanctioned rollback.  The counterexample is gen2 -> gen1 when the target gen1
candidates were persisted at canonical source revision 0: the old code wrote
``to.projection_revision = 0`` while the snapshot read ``1``.
"""

from __future__ import annotations

import pytest

from app.successor_runtime.runtime.facade_contracts import (
    rollback_transition_id,
    rollback_transition_ref,
)
from scripts.c9_projection_rebuild import rollback_position_payload


def _position(
    generation: int,
    offset_revision: int,
    source_revision: int,
    *,
    digest: str,
    offset_ref: str,
) -> dict[str, object]:
    return rollback_position_payload(
        projection_generation=generation,
        offset_revision=offset_revision,
        source_revision=source_revision,
        source_digest=digest,
        offset_ref=offset_ref,
    )


def test_position_identity_uses_generation_and_source_revision() -> None:
    position = _position(
        1,
        4,
        0,
        digest="a" * 64,
        offset_ref="value:schema:c9:generation:1:aa",
    )
    assert position == {
        "projection_generation": 1,
        "offset_revision": 4,
        "projection_revision": 1,
        "source_digest": "a" * 64,
        "cursor": 0,
        "offset_ref": "value:schema:c9:generation:1:aa",
    }


@pytest.mark.parametrize(
    ("generation", "source_revision"),
    [
        (0, 0),
        (1, 0),
        (1, 1),
        (2, 1),
        (3, 5),
    ],
)
def test_position_identity_holds_for_any_persisted_generation(
    generation: int,
    source_revision: int,
) -> None:
    position = _position(
        generation,
        offset_revision=generation + 2,
        source_revision=source_revision,
        digest="b" * 64,
        offset_ref=f"value:schema:c9:generation:{generation}:bb",
    )
    assert position["projection_revision"] == generation
    assert position["cursor"] == source_revision
    assert position["projection_generation"] == generation


def test_gen2_to_gen1_rollback_receipt_to_matches_query_snapshot() -> None:
    from_position = _position(
        2,
        offset_revision=5,
        source_revision=1,
        digest="c" * 64,
        offset_ref="value:schema:c9:generation:2:cc",
    )
    to_position = _position(
        1,
        offset_revision=6,
        source_revision=0,
        digest="a" * 64,
        offset_ref="value:schema:c9:generation:1:aa",
    )
    assert from_position["projection_revision"] == 2
    assert from_position["cursor"] == 1
    assert to_position["projection_revision"] == 1
    assert to_position["cursor"] == 0
    assert to_position["source_digest"] == "a" * 64
    assert to_position["offset_revision"] == 6


def test_rollback_transition_identity_is_deterministic_and_aba_aware() -> None:
    completeness = "e" * 64
    from_position = _position(
        2,
        offset_revision=5,
        source_revision=1,
        digest="c" * 64,
        offset_ref="value:schema:c9:generation:2:cc",
    )
    first_to = _position(
        1,
        offset_revision=6,
        source_revision=0,
        digest="a" * 64,
        offset_ref="value:schema:c9:generation:1:aa",
    )
    retry_to = _position(
        1,
        offset_revision=6,
        source_revision=0,
        digest="a" * 64,
        offset_ref="value:schema:c9:generation:1:aa",
    )
    aba_to = _position(
        1,
        offset_revision=9,
        source_revision=0,
        digest="a" * 64,
        offset_ref="value:schema:c9:generation:1:aa",
    )
    first_id = rollback_transition_id(
        from_position=from_position,
        to_position=first_to,
        generation_completeness_digest=completeness,
    )
    assert first_id == rollback_transition_id(
        from_position=from_position,
        to_position=retry_to,
        generation_completeness_digest=completeness,
    )
    aba_id = rollback_transition_id(
        from_position=from_position,
        to_position=aba_to,
        generation_completeness_digest=completeness,
    )
    assert aba_id != first_id
    assert rollback_transition_ref(first_id) == f"rollback:{first_id}"
