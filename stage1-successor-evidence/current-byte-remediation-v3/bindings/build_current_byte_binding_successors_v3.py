#!/usr/bin/env python3
# ruff: noqa: E501, TRY003
"""Build the create-only additive v3 current-byte binding bundle."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BINDINGS_REL = Path("stage1-successor-evidence/current-byte-remediation-v3/bindings")
V2_REL = Path("stage1-successor-evidence/current-byte-remediation-v2/bindings")
REGISTRY_REL = BINDINGS_REL / "current-byte-binding-successors.v3.json"
MANIFEST_REL = BINDINGS_REL / "artifact-manifest.v3.json"
V2_REGISTRY_REL = V2_REL / "current-byte-binding-successors.v2.json"
V2_REGISTRY_SHA256 = "8527402a0715a9540a0e1d1247f3015e3611059b0e16582b543d6848eb05fa7b"
V2_CONTENT_DIGEST = "0d7eedc8d552a64637c5a06dbe5a729a6f7a48a20b3dbf6d39629ec7d64cfb0d"
V2_MEMBER_HASHES = {
    V2_REL / "artifact-manifest.v2.json": "d8ad8870531ad3cf7c91b351ea7b8de07df9f375a2d5820be66e1e4637c07e7f",
    V2_REL / "build_current_byte_binding_successors_v2.py": "af3b5cbed636493ef724db0b8e287cd30df514760a3e3af7208a11e40aef9259",
    V2_REL / "check_current_byte_binding_successors_v2.py": "ac52e926d1d31218b6a5f39059d3f5e4a4c02a40d537ccfebd3ea5a38ce1730a",
    V2_REGISTRY_REL: V2_REGISTRY_SHA256,
    V2_REL / "snapshots/1daddedc2fe8a435c062fa66019e00db2b47aeb2e88d8fce97e7dfe3e8bd4cf5": "1daddedc2fe8a435c062fa66019e00db2b47aeb2e88d8fce97e7dfe3e8bd4cf5",
    V2_REL / "test_current_byte_binding_successors_v2.py": "e170f5ebf8c9a15846be9b72c0c9422830fe6fe423f63366154bc2339e413497",
}

AUTHORITY = {
    "candidate_promotion": False,
    "cutover": False,
    "deployment": False,
    "external_delivery": False,
    "legacy_retirement": False,
    "live_provider": False,
    "production_canonical_write": False,
    "production_release": False,
}
AUTHORITY_CEILING = (
    "EXACT_BYTE_CORRESPONDENCE_ONLY_NO_CANDIDATE_PROMOTION_NO_STAGE0_REWRITE_"
    "NO_PRODUCTION_AUTHORITY"
)

RUN_LOOP_PATH = "main/backend/app/services/agent_runtime/run_loop.py"
PREDECESSOR_SHA256 = "9c11c49cf985d9e5d5563e6111a6084def841875e584c80f7ffd5c7a5ff934c5"
SUCCESSOR_SHA256 = "f7d9aa9eff608adcf89b1afa98fb19c6f36520a7a2a96ea25aa31d76e851e89a"
SUCCESSOR_BYTES = 31203
SUCCESSOR_LINES = 684
SUCCESSOR_GIT_BLOB_SHA1 = "43ca6a027cbd28a0750e22a31348175da3b6475b"

PROVIDER_TEST_PATH = "tests/test_provider_port_failure_registration.py"
PROVIDER_TEST_PREDECESSOR_SHA256 = "dc1127564039987d7a422056dfd30e15d9b162a07562ee282aaf24e96fc62588"
PROVIDER_TEST_SUCCESSOR_SHA256 = "5453860c91064f06058e0f4857cb142aa6e14890ed63fc30ad4644dd3c799b0f"
PROVIDER_TEST_SUCCESSOR_BYTES = 11276
PROVIDER_TEST_SUCCESSOR_LINES = 308
PROVIDER_TEST_SUCCESSOR_GIT_BLOB_SHA1 = "8f2ceed27b9ccd154e7b24f8905d9d56303bf010"
PROVIDER_TEST_PREDECESSORS = {
    PROVIDER_TEST_PREDECESSOR_SHA256: {
        "bytes": 10337,
        "lines": 280,
        "git_blob_sha1": "cbbee92f47e2125dac358fefdb270da026525366",
        "role": "immediate_frozen_candidate_source",
    },
}

P = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/"
    "exact-byte-rebind/stage-b23-2026-09-05"
)
CANDIDATE_DECLARATIONS = (
    {
        "family": "C5",
        "candidate_path": f"{P}/candidates/C5/candidate.v2.json",
        "candidate_sha256": "919bbbbf66f7b5959b2407bbf7a488efecbd781844599d5b5ad945180f7dbc47",
        "json_pointer": "/sources/10",
        "predecessor_sha256": PREDECESSOR_SHA256,
    },
    {
        "family": "C6",
        "candidate_path": f"{P}/candidates/C6/candidate.v2.json",
        "candidate_sha256": "ffdb0020e8a3617a8693f10657a97787f11c6c759bc9afe96e7d06dcb876f87a",
        "json_pointer": "/sources/8",
        "predecessor_sha256": PREDECESSOR_SHA256,
    },
    {
        "family": "I1",
        "candidate_path": f"{P}/candidates/I1/candidate.v2.json",
        "candidate_sha256": "bb4fc787fbc0d1959f04797e45a99b3da1d00a544501ab30abcc5ff017af0e7e",
        "json_pointer": "/sources/111",
        "predecessor_sha256": PREDECESSOR_SHA256,
    },
)
FROZEN_CELL_SOURCES = ({'family': 'C5',
  'cell_id': 'C5.2',
  'fragment_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/fragments/C5.json',
  'fragment_sha256': '0b3d83914cf7de356e28a51dbfb5e7836d09266f315b4c26f8eab8bcbf26e30f',
  'json_pointer': '/source_bindings/7',
  'role': 'legacy_donor_c5_2',
  'spec_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/capability-specs/C5.2.v1.json',
  'spec_sha256': '797be2f9801e2722599e2e2c9fd9ae16c42a40fbdef1a5c43afec9a3e9caff96',
  'spec_json_pointer': '/source_bindings/2'},
 {'family': 'C6',
  'cell_id': 'C6.1',
  'fragment_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/fragments/C6.json',
  'fragment_sha256': 'b41f5c2dbbdfd268a86886c9ffc27fe78cfa3fb5914db44272b3dfece65e52bc',
  'json_pointer': '/source_bindings/8',
  'role': 'legacy_donor_c6_3',
  'spec_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/capability-specs/C6.1.v1.json',
  'spec_sha256': 'a7da8f3ad74f1bdd0b7aa9900d45f7556811e3968698346ca2a3bf955acafbd4',
  'spec_json_pointer': '/source_bindings/8'},
 {'family': 'C6',
  'cell_id': 'C6.3',
  'fragment_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/fragments/C6.json',
  'fragment_sha256': 'b41f5c2dbbdfd268a86886c9ffc27fe78cfa3fb5914db44272b3dfece65e52bc',
  'json_pointer': '/source_bindings/8',
  'role': 'legacy_donor_c6_3',
  'spec_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/capability-specs/C6.3.v1.json',
  'spec_sha256': 'c7e1f89b4e717ff67e4e11ec9939352d13eaf30fa2407fb7dedf198e90217ad5',
  'spec_json_pointer': '/source_bindings/3'})
PREDECESSOR_SNAPSHOT_REL = Path(
    f"{P}/candidates/C5/snapshots/{PREDECESSOR_SHA256}"
)

PROVIDER_TEST_CANDIDATE_DECLARATIONS = (
    *(
        {
            "family": "C2",
            "stage": stage,
            "candidate_path": f"development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/{stage}/candidates/C2/candidate.v2.json",
            "candidate_sha256": candidate_sha256,
            "json_pointer": "/tests/14",
            "predecessor_sha256": PROVIDER_TEST_PREDECESSOR_SHA256,
        }
        for stage, candidate_sha256 in (
            ("stage-b13-2026-09-05", "a5f9f704091d9c8baee4a4f0ce3ccf6da4bedab666d427d4b3d50510c136dcf0"),
            ("stage-b15-2026-09-05", "de0e01a13efe6aa220a163fb996bb9bddd86800fd1b4579cc5a9fd4a36b87394"),
            ("stage-b16-2026-09-05", "54e4aa88777795adc2390c0111f50501b1bd7c2fa4e3a3cea433371edcf024b5"),
            ("stage-b17-2026-09-05", "4a74faab9d757a442ad1e3745b664f984d5394df37801800e1e7e787d78b6ceb"),
            ("stage-b18-2026-09-05", "ee9b22d2f3631a050c24023860f414a86732d45f722bd1cc62177ac753eb45d4"),
            ("stage-b19-2026-09-05", "4ccc431f4eb7caebbdb91acd8146960c5a6e400c498a31a50f80251cfdfa4045"),
            ("stage-b23-2026-09-05", "2536206e80e002515b57ae131962db3cdd1cdd9a5eff64392731138c62b4f269"),
        )
    ),
)


# Exact contract-repair inputs; extending this set requires a new explicit byte review.
CONTRACT_REPAIRS = ({'source_path': 'main/backend/app/api/agent_sessions.py',
  'predecessor_sha256': '9c185595c6990055877f3dee47c615070ca3ff8b89b592e4991ab4c49fbefacd',
  'successor_sha256': '2a074d509523da9a33008929bc577c16b384ea23b7dba77060eba19fae5a0708',
  'bytes': 13724,
  'lines': 355,
  'declarations': [{'family': 'C9',
                    'candidate_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/C9/candidate.v2.json',
                    'candidate_sha256': 'bb7abb42d622828eddb599c72bc0974f22ca0fefb47c70a23a7dbddc3ec67329',
                    'json_pointer': '/sources/7',
                    'predecessor_sha256': '9c185595c6990055877f3dee47c615070ca3ff8b89b592e4991ab4c49fbefacd',
                    'snapshot_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/C9/snapshots/9c185595c6990055877f3dee47c615070ca3ff8b89b592e4991ab4c49fbefacd'}],
  'successor_id': 'c9-session-api-failure-refinement-v3',
  'change_class': 'TYPED_FAILURE_TO_HTTP_NOT_FOUND_REFINEMENT'},
 {'source_path': 'main/backend/app/services/agent_sessions/service.py',
  'predecessor_sha256': '49b2037874d51234c83836ac33121cff68ae30163b5ba3facfc171ca68d3d868',
  'successor_sha256': '453529a29d37d696be60e936426e9558808bead7ef7247809a020498251d0c07',
  'bytes': 99005,
  'lines': 2239,
  'declarations': [{'family': 'C5',
                    'candidate_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/C5/candidate.v2.json',
                    'candidate_sha256': '919bbbbf66f7b5959b2407bbf7a488efecbd781844599d5b5ad945180f7dbc47',
                    'json_pointer': '/sources/11',
                    'predecessor_sha256': '49b2037874d51234c83836ac33121cff68ae30163b5ba3facfc171ca68d3d868',
                    'snapshot_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/C5/snapshots/49b2037874d51234c83836ac33121cff68ae30163b5ba3facfc171ca68d3d868'},
                   {'family': 'C9',
                    'candidate_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/C9/candidate.v2.json',
                    'candidate_sha256': 'bb7abb42d622828eddb599c72bc0974f22ca0fefb47c70a23a7dbddc3ec67329',
                    'json_pointer': '/sources/11',
                    'predecessor_sha256': '49b2037874d51234c83836ac33121cff68ae30163b5ba3facfc171ca68d3d868',
                    'snapshot_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/C9/snapshots/49b2037874d51234c83836ac33121cff68ae30163b5ba3facfc171ca68d3d868'},
                   {'family': 'I1',
                    'candidate_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/candidate.v2.json',
                    'candidate_sha256': 'bb4fc787fbc0d1959f04797e45a99b3da1d00a544501ab30abcc5ff017af0e7e',
                    'json_pointer': '/sources/112',
                    'predecessor_sha256': '49b2037874d51234c83836ac33121cff68ae30163b5ba3facfc171ca68d3d868',
                    'snapshot_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/snapshots/49b2037874d51234c83836ac33121cff68ae30163b5ba3facfc171ca68d3d868'}],
  'successor_id': 'c5-c9-i1-session-service-failure-refinement-v3',
  'change_class': 'TYPED_FAILURE_APPROVAL_PROJECTION_REFINEMENT',
  'spec_bindings': [{'cell_id': 'C5.1',
                     'spec_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/capability-specs/C5.1.v1.json',
                     'spec_sha256': '95d89862c2caae37f0f549894b444f82b28f5cccc1bd9ddbe089f38b521e50fb',
                     'json_pointer': '/source_bindings/3',
                     'role': 'legacy_donor_c5_1_c5_3',
                     'prior_spec_predecessor_sha256': '56e5f4cf696bcdd1ceb31883e88b2829597dcc8f25d9a23287073c85cde21852'},
                    {'cell_id': 'C5.3',
                     'spec_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/capability-specs/C5.3.v1.json',
                     'spec_sha256': 'dc30062093443cf0af7c7fbbf8431e3f752169c7604f30d91667a6c83451e7ad',
                     'json_pointer': '/source_bindings/2',
                     'role': 'legacy_donor_c5_1_c5_3',
                     'prior_spec_predecessor_sha256': '56e5f4cf696bcdd1ceb31883e88b2829597dcc8f25d9a23287073c85cde21852'}]},
 {'source_path': 'main/backend/tests/successor_runtime/test_p3_c2_evidence_generator.py',
  'predecessor_sha256': '4b0457ad66f29d54e73cf4330347b4819855b0c2101fa24be81cef7fd4bc5f09',
  'successor_sha256': 'cbd81b05412f975cdf4b0d91d51e12263b5ad70033417867ba17f4694dc81fb7',
  'bytes': 6360,
  'lines': 187,
  'declarations': [{'family': 'C2',
                    'candidate_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/C2/candidate.v2.json',
                    'candidate_sha256': '2536206e80e002515b57ae131962db3cdd1cdd9a5eff64392731138c62b4f269',
                    'json_pointer': '/tests/9',
                    'predecessor_sha256': '4b0457ad66f29d54e73cf4330347b4819855b0c2101fa24be81cef7fd4bc5f09',
                    'snapshot_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/C2/snapshots/4b0457ad66f29d54e73cf4330347b4819855b0c2101fa24be81cef7fd4bc5f09'}],
  'successor_id': 'c2-historical-stage-selector-v3',
  'relation': 'C2_EXACT_TEST_BINDING_SUCCESSOR',
  'change_class': 'HISTORICAL_STAGE_SELECTOR_RETARGETED_TO_TRACKED_B23',
  'preservation_scope': 'EXACT_STAGE_PATH_UPDATE_ONLY_TEST_SEMANTICS_UNCHANGED_NO_AUTHORITY'},
 {'source_path': 'main/backend/tests/successor_runtime/test_p3_c5_0_evidence_generator.py',
  'predecessor_sha256': '284fb952da78d28d03b6f8dc16b9cfb8cbe500f6d8a14a9ef92aa6ad63906319',
  'successor_sha256': 'dea6b74abfdb2b70fabfbe3f598fa5bc87c3d655617085875ad5fc7c3bd6c387',
  'bytes': 9988,
  'lines': 274,
  'declarations': [{'family': 'C5',
                    'candidate_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/C5/candidate.v2.json',
                    'candidate_sha256': '919bbbbf66f7b5959b2407bbf7a488efecbd781844599d5b5ad945180f7dbc47',
                    'json_pointer': '/tests/0',
                    'predecessor_sha256': '284fb952da78d28d03b6f8dc16b9cfb8cbe500f6d8a14a9ef92aa6ad63906319',
                    'snapshot_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/C5/snapshots/284fb952da78d28d03b6f8dc16b9cfb8cbe500f6d8a14a9ef92aa6ad63906319'},
                   {'family': 'I1',
                    'candidate_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/candidate.v2.json',
                    'candidate_sha256': 'bb4fc787fbc0d1959f04797e45a99b3da1d00a544501ab30abcc5ff017af0e7e',
                    'json_pointer': '/sources/244',
                    'predecessor_sha256': '284fb952da78d28d03b6f8dc16b9cfb8cbe500f6d8a14a9ef92aa6ad63906319',
                    'snapshot_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/snapshots/284fb952da78d28d03b6f8dc16b9cfb8cbe500f6d8a14a9ef92aa6ad63906319'}],
  'successor_id': 'c5-historical-stage-selector-v3',
  'relation': 'C5_EXACT_TEST_BINDING_SUCCESSOR',
  'change_class': 'HISTORICAL_STAGE_SELECTOR_RETARGETED_TO_TRACKED_B23',
  'preservation_scope': 'EXACT_STAGE_PATH_UPDATE_ONLY_TEST_SEMANTICS_UNCHANGED_NO_AUTHORITY'},
 {'source_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/semantic-movement/P1P3LegacyDonorSemanticMovementInventory.v1.json',
  'predecessor_sha256': 'b4ae38c055ee2135daca0f276d30336483b920692d5c5b9d5c03dfa499c5db25',
  'successor_sha256': '40fea5ab8d9526ec1c085ab353e9acf12564c5c348dcb826cc46557ea6b81bd0',
  'bytes': 25944,
  'lines': 1,
  'declarations': [{'family': 'I1',
                    'candidate_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/candidate.v2.json',
                    'candidate_sha256': 'bb4fc787fbc0d1959f04797e45a99b3da1d00a544501ab30abcc5ff017af0e7e',
                    'json_pointer': '/sources/88',
                    'predecessor_sha256': 'b4ae38c055ee2135daca0f276d30336483b920692d5c5b9d5c03dfa499c5db25',
                    'snapshot_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/snapshots/b4ae38c055ee2135daca0f276d30336483b920692d5c5b9d5c03dfa499c5db25'}],
  'successor_id': 'i1-semantic-movement-inventory-candidate-binding-v3',
  'relation': 'I1_EXACT_CANDIDATE_BINDING_SUCCESSOR',
  'change_class': 'SEMANTIC_MOVEMENT_DERIVED_ARTIFACT_REBUILD',
  'preservation_scope': 'EXACT_SEMANTIC_DERIVED_ARTIFACT_BYTES_ONLY_NO_AUTHORITY'},
 {'source_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/semantic-movement/P1P3SemanticMovementGate.v1.json',
  'predecessor_sha256': '9d54a449aba89bf04197737764568984b0f9cc9aeb823445bbd17ae515f9e35e',
  'successor_sha256': '7936419d8fe94475640ec133198dec2db8c24af00e1d75d716425a8696d93514',
  'bytes': 7597,
  'lines': 1,
  'declarations': [{'family': 'I1',
                    'candidate_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/candidate.v2.json',
                    'candidate_sha256': 'bb4fc787fbc0d1959f04797e45a99b3da1d00a544501ab30abcc5ff017af0e7e',
                    'json_pointer': '/sources/89',
                    'predecessor_sha256': '9d54a449aba89bf04197737764568984b0f9cc9aeb823445bbd17ae515f9e35e',
                    'snapshot_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/snapshots/9d54a449aba89bf04197737764568984b0f9cc9aeb823445bbd17ae515f9e35e'}],
  'successor_id': 'i1-semantic-movement-gate-candidate-binding-v3',
  'relation': 'I1_EXACT_CANDIDATE_BINDING_SUCCESSOR',
  'change_class': 'SEMANTIC_MOVEMENT_DERIVED_ARTIFACT_REBUILD',
  'preservation_scope': 'EXACT_SEMANTIC_DERIVED_ARTIFACT_BYTES_ONLY_NO_AUTHORITY'},
 {'source_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/semantic-movement/P1P3SuccessorMovementMatrix.v1.json',
  'predecessor_sha256': 'a292ebfec63457d04a0671f15095ca4f371059c977f45146c3945919e046e523',
  'successor_sha256': '776ae30af7d5224bbff17006909e52efcd8384cd041fef01e2d169a3dc1fe440',
  'bytes': 250677,
  'lines': 1,
  'declarations': [{'family': 'I1',
                    'candidate_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/candidate.v2.json',
                    'candidate_sha256': 'bb4fc787fbc0d1959f04797e45a99b3da1d00a544501ab30abcc5ff017af0e7e',
                    'json_pointer': '/sources/90',
                    'predecessor_sha256': 'a292ebfec63457d04a0671f15095ca4f371059c977f45146c3945919e046e523',
                    'snapshot_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/snapshots/a292ebfec63457d04a0671f15095ca4f371059c977f45146c3945919e046e523'}],
  'successor_id': 'i1-semantic-movement-matrix-candidate-binding-v3',
  'relation': 'I1_EXACT_CANDIDATE_BINDING_SUCCESSOR',
  'change_class': 'SEMANTIC_MOVEMENT_DERIVED_ARTIFACT_REBUILD',
  'preservation_scope': 'EXACT_SEMANTIC_DERIVED_ARTIFACT_BYTES_ONLY_NO_AUTHORITY'},
 {'source_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/semantic-movement/fragments/C1.v1.json',
  'predecessor_sha256': 'fc26123aea12acf8705e600170620c247309f035378cb6146962d6ddfd682c15',
  'successor_sha256': '8c6814d0c21e7957bfc3d84a1fcf47d0598e81959768adcd5be5662a32af460f',
  'bytes': 23291,
  'lines': 1,
  'declarations': [{'family': 'I1',
                    'candidate_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/candidate.v2.json',
                    'candidate_sha256': 'bb4fc787fbc0d1959f04797e45a99b3da1d00a544501ab30abcc5ff017af0e7e',
                    'json_pointer': '/sources/91',
                    'predecessor_sha256': 'fc26123aea12acf8705e600170620c247309f035378cb6146962d6ddfd682c15',
                    'snapshot_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/snapshots/fc26123aea12acf8705e600170620c247309f035378cb6146962d6ddfd682c15'}],
  'successor_id': 'i1-semantic-movement-c1-fragment-candidate-binding-v3',
  'relation': 'I1_EXACT_CANDIDATE_BINDING_SUCCESSOR',
  'change_class': 'SEMANTIC_MOVEMENT_DERIVED_ARTIFACT_REBUILD',
  'preservation_scope': 'EXACT_SEMANTIC_DERIVED_ARTIFACT_BYTES_ONLY_NO_AUTHORITY'},
 {'source_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/semantic-movement/fragments/C9.v1.json',
  'predecessor_sha256': 'b918073cb449c11511392b7ee799f119a702e24d319331b8f8cd7e8d1b6cfc89',
  'successor_sha256': '0b9ba3f993c8577902052243bda4dfc6b382abdf53d5ed6e84b6cb78c95512e8',
  'bytes': 32274,
  'lines': 1,
  'declarations': [{'family': 'I1',
                    'candidate_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/candidate.v2.json',
                    'candidate_sha256': 'bb4fc787fbc0d1959f04797e45a99b3da1d00a544501ab30abcc5ff017af0e7e',
                    'json_pointer': '/sources/92',
                    'predecessor_sha256': 'b918073cb449c11511392b7ee799f119a702e24d319331b8f8cd7e8d1b6cfc89',
                    'snapshot_path': 'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/stage-b23-2026-09-05/candidates/I1/snapshots/b918073cb449c11511392b7ee799f119a702e24d319331b8f8cd7e8d1b6cfc89'}],
  'successor_id': 'i1-semantic-movement-c9-fragment-candidate-binding-v3',
  'relation': 'I1_EXACT_CANDIDATE_BINDING_SUCCESSOR',
  'change_class': 'SEMANTIC_MOVEMENT_DERIVED_ARTIFACT_REBUILD',
  'preservation_scope': 'EXACT_SEMANTIC_DERIVED_ARTIFACT_BYTES_ONLY_NO_AUTHORITY'})

def contract_repair_rows(root: Path) -> list[dict[str, Any]]:
    rows = []
    for repair in CONTRACT_REPAIRS:
        payload = (root / repair["source_path"]).read_bytes()
        if (sha256(payload), len(payload), payload.count(b"\n")) != (
            repair["successor_sha256"], repair["bytes"], repair["lines"]
        ):
            raise ValueError("contract repair source identity drift")
        declarations = []
        predecessors = []
        for declaration in repair["declarations"]:
            raw = (root / declaration["candidate_path"]).read_bytes()
            if sha256(raw) != declaration["candidate_sha256"]:
                raise ValueError("contract repair candidate identity drift")
            ref = resolve_pointer(json.loads(raw), declaration["json_pointer"])
            snapshot = (root / declaration["snapshot_path"]).read_bytes()
            if (ref["path"] != repair["source_path"]
                    or ref["file_sha256"] != repair["predecessor_sha256"]
                    or sha256(snapshot) != repair["predecessor_sha256"]
                    or ref["bytes"] != len(snapshot)
                    or Path(declaration["candidate_path"]).parent / ref["snapshot_path"] != Path(declaration["snapshot_path"])):
                raise ValueError("contract repair frozen declaration drift")
            declarations.append({key: value for key, value in declaration.items() if key != "snapshot_path"})
            predecessors.append({"artifact": declaration["candidate_path"],
                                 "artifact_sha256": declaration["candidate_sha256"],
                                 "json_pointer": declaration["json_pointer"],
                                 "hash_field": "file_sha256",
                                 "bound_sha256": repair["predecessor_sha256"]})
        specs = repair.get("spec_bindings", [])
        for spec in specs:
            raw = (root / spec["spec_path"]).read_bytes()
            if sha256(raw) != spec["spec_sha256"] or resolve_pointer(json.loads(raw), spec["json_pointer"]) != {
                "path": repair["source_path"], "file_sha256": spec["prior_spec_predecessor_sha256"], "role": spec["role"]
            }:
                raise ValueError("contract repair owning specification drift")
        row = {key: repair[key] for key in ("successor_id", "source_path", "predecessor_sha256", "successor_sha256", "bytes", "lines", "change_class")}
        row.update({"relation": repair.get(
                        "relation",
                        "I1_SHARED_EXACT_BINDING_SUCCESSOR" if specs else "C9_EXACT_BINDING_SUCCESSOR",
                    ),
                    "families": list(dict.fromkeys(item["family"] for item in declarations)),
                    "cell_ids": [item["cell_id"] for item in specs],
                    "binding_group": "source_bindings",
                    "snapshot_path": "snapshots/" + repair["successor_sha256"],
                    "direct_candidate_declarations": declarations,
                    "predecessor_declarations": predecessors,
                    "spec_bindings": specs,
                    "ordered_sha256_chain": [repair["predecessor_sha256"], repair["successor_sha256"]],
                    "preservation_scope": repair.get(
                        "preservation_scope",
                        "EXACT_BYTE_REFINEMENT_ONLY_FAILURE_BEHAVIOR_CHANGED_NO_AUTHORITY",
                    ),
                    "qualification": "EXACT_BYTES_ONLY_NOT_AUTHORITY"})
        if specs:
            row["role"] = specs[0]["role"]
            row["prior_spec_predecessor_sha256"] = specs[0]["prior_spec_predecessor_sha256"]
        rows.append(row)
    return rows


def _load_v2_builder():
    path = REPOSITORY_ROOT / V2_REL / "build_current_byte_binding_successors_v2.py"
    spec = importlib.util.spec_from_file_location("build_current_byte_binding_successors_v2_for_v3", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load v2 current-byte successor builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V2_BUILDER = _load_v2_builder()
sha256 = V2_BUILDER.sha256
canonical_json = V2_BUILDER.canonical_json
pretty_json = V2_BUILDER.pretty_json
with_content_digest = V2_BUILDER.with_content_digest
load_object = V2_BUILDER.load_object
resolve_pointer = V2_BUILDER.resolve_pointer


def _git_blob_sha1(payload: bytes) -> str:
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()  # noqa: S324


def _type_checking_successor(predecessor: bytes) -> bytes:
    text = predecessor.decode("utf-8")
    old_execution_import = (
        "from .tool_execution import ToolCallExecutionRecord, ToolExecutionHooks, "
        "ToolExecutionPolicy, is_abort_requested\n\n\nAgentRunLoopEventSink"
    )
    new_execution_import = (
        "from .tool_execution import ToolCallExecutionRecord, ToolExecutionHooks, "
        "ToolExecutionPolicy, is_abort_requested\n\nif TYPE_CHECKING:\n"
        "    from .read_only_tools import ReadOnlyAgentToolRuntime\n\n\nAgentRunLoopEventSink"
    )
    replacements = (
        ("from typing import Any, Protocol\n", "from typing import TYPE_CHECKING, Any, Protocol\n"),
        ("from .read_only_tools import ReadOnlyAgentToolRuntime\n", ""),
        (old_execution_import, new_execution_import),
    )
    for old, new in replacements:
        if text.count(old) != 1:
            raise ValueError("run_loop TYPE_CHECKING predecessor shape drift")
        text = text.replace(old, new, 1)
    return text.encode("utf-8")


def _provider_fixture_successor(predecessor: bytes) -> bytes:
    text = predecessor.decode("utf-8")
    import_anchor = "import json\nimport sys\nfrom pathlib import Path\n"
    import_replacement = "import json\nimport sys\nfrom collections.abc import Iterator\nfrom pathlib import Path\n"
    fixture_anchor = "}\n\n\ndef _parse(relative_path: str) -> ast.Module:\n"
    fixture_replacement = '''}


@pytest.fixture(scope="module", autouse=True)
def _isolate_llm_cache_effect(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Keep import-time LLM cache initialization inside the test temp root."""
    from app.settings.config import settings
    from langchain_core.globals import get_llm_cache, set_llm_cache

    previous_cache = get_llm_cache()
    previous_env = settings.env
    settings.env = "prod"
    try:
        from app.services.llm import cache as llm_cache
    finally:
        settings.env = previous_env

    previous_cache_file = llm_cache._CACHE_FILE
    llm_cache._CACHE_FILE = (
        tmp_path_factory.mktemp("provider-port-llm-cache") / "langchain-cache.db"
    )
    try:
        llm_cache.setup_cache()
        yield
    finally:
        set_llm_cache(previous_cache)
        llm_cache._CACHE_FILE = previous_cache_file
        settings.env = previous_env


def _parse(relative_path: str) -> ast.Module:
'''
    for old, new in (
        (import_anchor, import_replacement),
        (fixture_anchor, fixture_replacement),
    ):
        if text.count(old) != 1:
            raise ValueError("provider test fixture predecessor shape drift")
        text = text.replace(old, new, 1)
    return text.encode("utf-8")


def provider_test_predecessor_declarations() -> list[dict[str, Any]]:
    return [
        {
            "artifact": item["candidate_path"],
            "artifact_sha256": item["candidate_sha256"],
            "json_pointer": item["json_pointer"],
            "hash_field": "file_sha256",
            "bound_sha256": item["predecessor_sha256"],
        }
        for item in PROVIDER_TEST_CANDIDATE_DECLARATIONS
    ]


def provider_test_frozen_source_snapshots() -> list[dict[str, Any]]:
    snapshots = []
    for item in PROVIDER_TEST_CANDIDATE_DECLARATIONS:
        predecessor = PROVIDER_TEST_PREDECESSORS[item["predecessor_sha256"]]
        snapshots.append(
            {
                "candidate_path": item["candidate_path"],
                "snapshot_path": str(Path(item["candidate_path"]).parent / "snapshots" / item["predecessor_sha256"]),
                "sha256": item["predecessor_sha256"],
                "bytes": predecessor["bytes"],
                "lines": predecessor["lines"],
                "git_blob_sha1": predecessor["git_blob_sha1"],
                "role": predecessor["role"],
            }
        )
    return snapshots


def validate_inputs(root: Path) -> tuple[dict[str, Any], bytes, bytes]:
    for relative, expected in V2_MEMBER_HASHES.items():
        if sha256((root / relative).read_bytes()) != expected:
            raise ValueError(f"v2 predecessor bundle drift: {relative}")
    v2 = load_object(root / V2_REGISTRY_REL)
    if (
        v2.get("schema") != "mrw.current_byte_binding_successors.v2"
        or v2.get("record_id") != "current-byte-binding-successors-v2"
        or v2.get("content_digest") != V2_CONTENT_DIGEST
        or v2.get("authoritative") is not False
        or len(v2.get("successors", [])) != 11
    ):
        raise ValueError("v2 predecessor registry identity drift")

    payload = (root / RUN_LOOP_PATH).read_bytes()
    if sha256(payload) != SUCCESSOR_SHA256:
        raise ValueError("run_loop current source hash mismatch")
    if len(payload) != SUCCESSOR_BYTES or payload.count(b"\n") != SUCCESSOR_LINES:
        raise ValueError("run_loop current source size mismatch")
    if _git_blob_sha1(payload) != SUCCESSOR_GIT_BLOB_SHA1:
        raise ValueError("run_loop current git blob mismatch")
    predecessor = (root / PREDECESSOR_SNAPSHOT_REL).read_bytes()
    if sha256(predecessor) != PREDECESSOR_SHA256:
        raise ValueError("run_loop predecessor snapshot drift")
    if _type_checking_successor(predecessor) != payload:
        raise ValueError("run_loop change exceeds TYPE_CHECKING preservation scope")

    expected_candidate_source = {
        "bytes": 31165,
        "file_sha256": PREDECESSOR_SHA256,
        "path": RUN_LOOP_PATH,
        "snapshot_path": f"snapshots/{PREDECESSOR_SHA256}",
    }
    for declaration in CANDIDATE_DECLARATIONS:
        artifact = (root / declaration["candidate_path"]).read_bytes()
        if sha256(artifact) != declaration["candidate_sha256"]:
            raise ValueError(f"candidate artifact drift: {declaration['family']}")
        bound = resolve_pointer(json.loads(artifact), declaration["json_pointer"])
        if bound != expected_candidate_source:
            raise ValueError(f"candidate declaration pointer drift: {declaration['family']}")

    for source in FROZEN_CELL_SOURCES:
        artifact = (root / source["fragment_path"]).read_bytes()
        if sha256(artifact) != source["fragment_sha256"]:
            raise ValueError(f"frozen fragment drift: {source['family']}")
        fragment = json.loads(artifact)
        if not any(cell.get("cell_id") == source["cell_id"] for cell in fragment.get("cells", [])):
            raise ValueError(f"frozen cell missing: {source['cell_id']}")
        expected = {
            "bytes": 31165,
            "lines": 682,
            "path": RUN_LOOP_PATH,
            "role": source["role"],
            "sha256": PREDECESSOR_SHA256,
        }
        if resolve_pointer(fragment, source["json_pointer"]) != expected:
            raise ValueError(f"frozen cell source pointer drift: {source['cell_id']}")
        spec_raw = (root / source["spec_path"]).read_bytes()
        if sha256(spec_raw) != source["spec_sha256"] or resolve_pointer(json.loads(spec_raw), source["spec_json_pointer"]) != {
            "path": RUN_LOOP_PATH, "file_sha256": PREDECESSOR_SHA256, "role": source["role"]
        }:
            raise ValueError(f"frozen cell specification binding drift: {source['cell_id']}")

    provider_payload = (root / PROVIDER_TEST_PATH).read_bytes()
    if sha256(provider_payload) != PROVIDER_TEST_SUCCESSOR_SHA256:
        raise ValueError("provider test current source hash mismatch")
    if (
        len(provider_payload) != PROVIDER_TEST_SUCCESSOR_BYTES
        or provider_payload.count(b"\n") != PROVIDER_TEST_SUCCESSOR_LINES
    ):
        raise ValueError("provider test current source size mismatch")
    if _git_blob_sha1(provider_payload) != PROVIDER_TEST_SUCCESSOR_GIT_BLOB_SHA1:
        raise ValueError("provider test current git blob mismatch")

    immediate_predecessor: bytes | None = None
    for declaration in PROVIDER_TEST_CANDIDATE_DECLARATIONS:
        artifact = (root / declaration["candidate_path"]).read_bytes()
        if sha256(artifact) != declaration["candidate_sha256"]:
            raise ValueError(f"provider test candidate artifact drift: {declaration['stage']}")
        predecessor = PROVIDER_TEST_PREDECESSORS[declaration["predecessor_sha256"]]
        expected_candidate_test = {
            "bytes": predecessor["bytes"],
            "file_sha256": declaration["predecessor_sha256"],
            "path": PROVIDER_TEST_PATH,
            "snapshot_path": f"snapshots/{declaration['predecessor_sha256']}",
        }
        bound = resolve_pointer(json.loads(artifact), declaration["json_pointer"])
        if bound != expected_candidate_test:
            raise ValueError(f"provider test candidate declaration pointer drift: {declaration['stage']}")
        snapshot_path = Path(declaration["candidate_path"]).parent / bound["snapshot_path"]
        snapshot = (root / snapshot_path).read_bytes()
        if (
            sha256(snapshot) != declaration["predecessor_sha256"]
            or len(snapshot) != predecessor["bytes"]
            or snapshot.count(b"\n") != predecessor["lines"]
            or _git_blob_sha1(snapshot) != predecessor["git_blob_sha1"]
        ):
            raise ValueError(f"provider test frozen snapshot drift: {declaration['stage']}")
        if declaration["predecessor_sha256"] == PROVIDER_TEST_PREDECESSOR_SHA256:
            if immediate_predecessor is None:
                immediate_predecessor = snapshot
            elif snapshot != immediate_predecessor:
                raise ValueError("provider test immediate predecessor snapshots diverge")
    if immediate_predecessor is None:
        raise ValueError("provider test immediate predecessor snapshot missing")
    if _provider_fixture_successor(immediate_predecessor) != provider_payload:
        raise ValueError("provider test change exceeds isolated fixture preservation scope")
    return v2, payload, provider_payload


def shared_run_loop_successor() -> dict[str, Any]:
    predecessor_declarations = [
        {
            "artifact": item["candidate_path"],
            "artifact_sha256": item["candidate_sha256"],
            "json_pointer": item["json_pointer"],
            "hash_field": "file_sha256",
            "bound_sha256": item["predecessor_sha256"],
        }
        for item in CANDIDATE_DECLARATIONS
    ]
    return {
        "successor_id": "c5-c6-i1-run-loop-current-bytes-v3",
        "relation": "C5_C6_I1_SHARED_EXACT_BINDING_SUCCESSOR",
        "families": ["C5", "C6", "I1"],
        "cell_ids": [item["cell_id"] for item in FROZEN_CELL_SOURCES],
        "binding_group": "source_bindings",
        "source_path": RUN_LOOP_PATH,
        "predecessor_sha256": PREDECESSOR_SHA256,
        "successor_sha256": SUCCESSOR_SHA256,
        "bytes": SUCCESSOR_BYTES,
        "lines": SUCCESSOR_LINES,
        "git_blob_sha1_working_tree": SUCCESSOR_GIT_BLOB_SHA1,
        "snapshot_path": f"snapshots/{SUCCESSOR_SHA256}",
        "predecessor_declarations": predecessor_declarations,
        "direct_candidate_declarations": [dict(item) for item in CANDIDATE_DECLARATIONS],
        "frozen_cell_sources": [dict(item) for item in FROZEN_CELL_SOURCES],
        "ordered_sha256_chain": [
            {"stage": "FROZEN_CANDIDATE_PREDECESSOR", "sha256": PREDECESSOR_SHA256},
            {"stage": "CURRENT_WORKING_TREE_SUCCESSOR", "sha256": SUCCESSOR_SHA256},
        ],
        "change_class": "TYPE_CHECKING_ONLY_IMPORT_RELOCATION",
        "preservation_scope": {
            "runtime_import_removed": "read_only_tools.ReadOnlyAgentToolRuntime",
            "type_checking_import_retained": "read_only_tools.ReadOnlyAgentToolRuntime",
            "runtime_behavior_claim": "PRESERVED_BY_EXACT_TEXTUAL_TRANSFORMATION_ONLY",
        },
        "qualification": "EXACT_BYTES_ONLY_NOT_AUTHORITY",
    }


def shared_provider_test_successor() -> dict[str, Any]:
    return {
        "successor_id": "c2-provider-port-failure-registration-current-bytes-v3",
        "relation": "C2_SHARED_EXACT_TEST_BINDING_SUCCESSOR",
        "families": ["C2"],
        "cell_ids": [],
        "binding_group": "tests",
        "source_path": PROVIDER_TEST_PATH,
        "predecessor_sha256": PROVIDER_TEST_PREDECESSOR_SHA256,
        "successor_sha256": PROVIDER_TEST_SUCCESSOR_SHA256,
        "bytes": PROVIDER_TEST_SUCCESSOR_BYTES,
        "lines": PROVIDER_TEST_SUCCESSOR_LINES,
        "git_blob_sha1_working_tree": PROVIDER_TEST_SUCCESSOR_GIT_BLOB_SHA1,
        "snapshot_path": f"snapshots/{PROVIDER_TEST_SUCCESSOR_SHA256}",
        "predecessor_declarations": provider_test_predecessor_declarations(),
        "direct_candidate_declarations": [dict(item) for item in PROVIDER_TEST_CANDIDATE_DECLARATIONS],
        "frozen_source_snapshots": provider_test_frozen_source_snapshots(),
        "ordered_sha256_chain": [
            {"stage": "IMMEDIATE_FROZEN_CANDIDATE_PREDECESSOR", "sha256": PROVIDER_TEST_PREDECESSOR_SHA256},
            {"stage": "CURRENT_WORKING_TREE_SUCCESSOR", "sha256": PROVIDER_TEST_SUCCESSOR_SHA256},
        ],
        "change_class": "TEST_FIXTURE_IMPORT_EFFECT_ISOLATION",
        "preservation_scope": {
            "fixture_name": "_isolate_llm_cache_effect",
            "fixture_scope": "module",
            "fixture_autouse": True,
            "effect_path": "pytest.TempPathFactory.mktemp/provider-port-llm-cache/langchain-cache.db",
            "restored_state": ["langchain_global_llm_cache", "llm_cache._CACHE_FILE", "settings.env"],
            "test_functions_changed": False,
            "test_assertions_changed": False,
            "production_sources_changed": False,
            "alias_or_provider_binding_changed": False,
            "runtime_behavior_claim": "TEST_IMPORT_EFFECT_ISOLATED_BY_EXACT_TEXTUAL_TRANSFORMATION_ONLY",
        },
        "qualification": "EXACT_BYTES_ONLY_NOT_AUTHORITY",
    }


def build_documents(root: Path) -> dict[Path, bytes]:
    v2, payload, provider_payload = validate_inputs(root)
    registry = with_content_digest(
        {
            "schema": "mrw.current_byte_binding_successors.v3",
            "record_id": "current-byte-binding-successors-v3",
            "status": "CURRENT_BYTES_BOUND_BY_ADDITIVE_SUCCESSORS_NOT_AUTHORITY",
            "authoritative": False,
            "authority": AUTHORITY,
            "authority_ceiling": AUTHORITY_CEILING,
            "extends": {
                "path": V2_REGISTRY_REL.as_posix(),
                "sha256": V2_REGISTRY_SHA256,
                "content_digest": V2_CONTENT_DIGEST,
                "schema": "mrw.current_byte_binding_successors.v2",
                "record_id": "current-byte-binding-successors-v2",
                "mutation": False,
            },
            "inherited_successor_count": 11,
            "successors": [
                *v2["successors"],
                shared_run_loop_successor(),
                shared_provider_test_successor(),
                *contract_repair_rows(root),
            ],
            "limits": [
                "The v2 registry and all eleven v2 successor rows remain byte-for-byte and value-for-value unchanged.",
                "One shared v3 row binds three exact run_loop candidate declarations and three exact frozen specification references.",
                "A second shared v3 row binds the seven currently projected frozen C2 candidate references to the provider test and records their common immediate predecessor snapshot identity.",
                "Historical C2 candidates outside the current intake projection are not included and are not claimed as rebound.",
                "The run_loop change is limited to TYPE_CHECKING import relocation by exact predecessor transformation.",
                "The provider test change is limited to module-scoped temporary cache-effect isolation by exact predecessor transformation; test assertions, production sources, aliases, and provider bindings are unchanged.",
                "Nine explicit contract-repair rows refine typed failure behavior, retarget the C2 and C5 historical-stage selectors, or project exact I1 semantic-derived bytes while preserving every frozen predecessor byte.",
                "Exact-byte correspondence grants no candidate promotion or production authority.",
                "PRODUCTION_RELEASE_NOT_AUTHORIZED",
            ],
        }
    )
    return {
        **{BINDINGS_REL / "snapshots" / row["successor_sha256"]: (root / row["source_path"]).read_bytes() for row in CONTRACT_REPAIRS},
        REGISTRY_REL: pretty_json(registry),
        BINDINGS_REL / "snapshots" / SUCCESSOR_SHA256: payload,
        BINDINGS_REL / "snapshots" / PROVIDER_TEST_SUCCESSOR_SHA256: provider_payload,
    }


def build_manifest(root: Path, documents: dict[Path, bytes]) -> bytes:
    static = tuple(BINDINGS_REL / name for name in (
        "build_current_byte_binding_successors_v3.py",
        "check_current_byte_binding_successors_v3.py",
        "test_current_byte_binding_successors_v3.py",
    ))
    members = [
        {"path": path.as_posix(), "bytes": len(payload), "sha256": sha256(payload)}
        for path, payload in documents.items()
    ]
    for path in static:
        payload = (root / path).read_bytes()
        members.append({"path": path.as_posix(), "bytes": len(payload), "sha256": sha256(payload)})
    members.sort(key=lambda item: item["path"])
    return pretty_json(with_content_digest({
        "schema": "mrw.current_byte_binding_successor_manifest.v3",
        "status": "COMPLETE_NOT_AUTHORITY",
        "authoritative": False,
        "authority": AUTHORITY,
        "authority_ceiling": AUTHORITY_CEILING,
        "member_count": len(members),
        "members": members,
    }))


def expected_documents(root: Path) -> dict[Path, bytes]:
    documents = build_documents(root)
    documents[MANIFEST_REL] = build_manifest(root, documents)
    return documents


def check(root: Path) -> dict[str, Any]:
    documents = expected_documents(root)
    static = {BINDINGS_REL / name for name in (
        "build_current_byte_binding_successors_v3.py",
        "check_current_byte_binding_successors_v3.py",
        "test_current_byte_binding_successors_v3.py",
    )}
    actual = {
        path.relative_to(root)
        for path in (root / BINDINGS_REL).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    if actual != set(documents) | static:
        raise ValueError("v3 binding bundle contains missing or unexpected files")
    for relative, expected in documents.items():
        if (root / relative).read_bytes() != expected:
            raise ValueError(f"generated v3 artifact drift: {relative}")
    registry = load_object(root / REGISTRY_REL)
    return {
        "status": "PASS",
        "source_count": len({row["source_path"] for row in registry["successors"]}),
        "successor_count": len(registry["successors"]),
        "direct_candidate_declaration_count": sum(
            len(row.get("direct_candidate_declarations", []))
            for row in registry["successors"][11:]
        ),
        "run_loop_direct_candidate_declaration_count": len(
            registry["successors"][11]["direct_candidate_declarations"]
        ),
        "provider_test_direct_candidate_declaration_count": len(
            registry["successors"][12]["direct_candidate_declarations"]
        ),
        "authority_ceiling": AUTHORITY_CEILING,
    }


def write_create_only(root: Path) -> None:
    documents = expected_documents(root)
    for relative in documents:
        target = root / relative
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"create-only target exists: {relative}")

    for relative, payload in documents.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(payload)
        if target.parent.name == "snapshots":
            os.chmod(target, 0o444)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    if args.write:
        write_create_only(root)
    print(json.dumps(check(root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
