"""Historical direct-successor declarations remain read-only identity evidence."""
import copy
from types import SimpleNamespace

import pytest

from tests.successor_runtime import i1_binding_candidate_support as support

pytestmark = pytest.mark.unit


def fixture():
    binding = SimpleNamespace(path="history/c5.2-source-binding.json", role="legacy_donor_c5_2", file_sha256="old")
    row = dict(relation="C5_C6_I1_SHARED_EXACT_BINDING_SUCCESSOR", source_path=binding.path,
               binding_group="source_bindings", predecessor_sha256="old", successor_sha256="new",
               frozen_cell_sources=[dict(cell_id="C5.2", role=binding.role)],
               direct_candidate_declarations=[dict(family="I1",
                   candidate_path=str(support.CANDIDATE_PATH.relative_to(support.REPOSITORY_ROOT)),
                   candidate_sha256=support.CURRENT_CANDIDATE_SHA256, predecessor_sha256="old")])
    return binding, dict(successors=[row])


def test_direct_successor_matches_declared_cell_role_and_candidate():
    binding, registry = fixture()
    assert support._match_direct_successor(registry, "C5.2", "source_bindings", binding, "new") is registry["successors"][0]


@pytest.mark.parametrize("change", ["cell", "role", "group", "predecessor", "successor", "candidate"])
def test_direct_successor_rejects_other_binding_identity(change):
    binding, registry = fixture()
    cell, group, actual = "C5.2", "source_bindings", "new"
    if change == "cell":
        cell = "C5.3"
    elif change == "role":
        binding.role = "unrelated_role"
    elif change == "group":
        group = "rollback_bindings"
    elif change == "predecessor":
        binding.file_sha256 = "other"
    elif change == "successor":
        actual = "other"
    else:
        registry["successors"][0]["direct_candidate_declarations"][0]["candidate_sha256"] = "other"
    assert support._match_direct_successor(registry, cell, group, binding, actual) is None


def test_direct_successor_rejects_duplicate_authorizing_rows():
    binding, registry = fixture()
    registry["successors"].append(copy.deepcopy(registry["successors"][0]))
    with pytest.raises(AssertionError, match="ambiguous"):
        support._match_direct_successor(registry, "C5.2", "source_bindings", binding, "new")


def test_historical_c6_relation_is_parseable_but_not_current_identity():
    binding, registry = fixture()
    row = registry["successors"][0]
    row["frozen_cell_sources"] = [dict(cell_id="C6.1", role=binding.role)]

    assert support._match_historical_direct_successor(
        registry, "C6.1", "source_bindings", binding, "new"
    ) is row
    assert support._match_direct_successor(
        registry, "C6.1", "source_bindings", binding, "new"
    ) is None
