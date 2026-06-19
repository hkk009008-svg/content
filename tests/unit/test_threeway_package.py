"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_package.py -q"""
import threeway


def test_schema_version_is_a_string():
    assert isinstance(threeway.SCHEMA_VERSION, str) and threeway.SCHEMA_VERSION


def test_load_bearing_kinds_are_a_subset_of_all_kinds():
    assert threeway.LOAD_BEARING_KINDS <= threeway.THREEWAY_KINDS


def test_core_kinds_present():
    for k in ("brief", "candidate", "attestation", "release_order", "cycle_go",
              "release_requested", "ci_result", "attestation_revoked",
              "candidate_aborted", "brief_superseded", "merge_completed"):
        assert k in threeway.THREEWAY_KINDS, k
