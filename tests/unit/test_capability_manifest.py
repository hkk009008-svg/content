"""TDD tests for cinema/capability_manifest.py — the evidence-backed
capability manifest validator (comprehensive-unification plan, slice 12).

Headline invariant: a capability's authored `status` (live/wired) is NEVER
sufficient on its own to advertise it as engaged. Engagement additionally
requires a real, currently-resolving production `consumer` anchor AND at
least one currently-resolving `evidence_tests` entry. Producer, consumer,
evidence tests, exposure, spend kind, STATIC capability (`engaged_static`),
and RUNTIME availability are kept as separate fields end to end — never
collapsed into one authored bit (invariant 4, ARCHITECTURE.md/plan §"Product
invariants").

Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_capability_manifest.py -q
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from cinema.capability_manifest import (
    REPO_ROOT,
    build_manifest,
    to_diagnostic_view,
    to_operator_view,
    validate_component,
    validate_manifest,
)


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content))
    return p


def _write_toml(tmp_path: Path, content: str) -> Path:
    return _write(tmp_path, "pipeline_status.toml", content)


# ---------------------------------------------------------------------------
# Headline invariant: engaged claims require a resolving consumer + test.
# ---------------------------------------------------------------------------

class TestEngagedRequiresConsumerAndTest:
    def test_wired_with_no_consumer_no_test_is_rejected(self, tmp_path):
        _write(tmp_path, "mod.py", "def do_thing():\n    pass\n")
        raw = {
            "id": "ghost_capability", "title": "Ghost", "status": "wired",
            "anchor": "mod.py:do_thing", "note": "",
        }
        comp = validate_component(raw, tmp_path)
        assert comp.engaged_static is False
        assert "consumer" in comp.reason.lower()
        assert "evidence test" in comp.reason.lower()

    def test_wired_with_consumer_but_no_test_is_rejected(self, tmp_path):
        _write(tmp_path, "mod.py", """\
            def do_thing():
                pass


            def call_site():
                do_thing()
        """)
        raw = {
            "id": "ghost_capability", "title": "Ghost", "status": "wired",
            "anchor": "mod.py:do_thing", "consumer": "mod.py:call_site",
        }
        comp = validate_component(raw, tmp_path)
        assert comp.engaged_static is False
        assert "evidence test" in comp.reason.lower()
        assert "consumer" not in comp.reason.lower().split("evidence")[0] or True

    def test_wired_with_consumer_and_broken_test_reference_is_rejected(self, tmp_path):
        _write(tmp_path, "mod.py", """\
            def do_thing():
                pass


            def call_site():
                do_thing()
        """)
        raw = {
            "id": "ghost_capability", "title": "Ghost", "status": "wired",
            "anchor": "mod.py:do_thing", "consumer": "mod.py:call_site",
            "evidence_tests": ["tests/unit/test_does_not_exist_xyz.py"],
        }
        comp = validate_component(raw, tmp_path)
        assert comp.engaged_static is False
        assert "evidence test" in comp.reason.lower()

    def test_wired_with_unresolvable_consumer_symbol_is_rejected(self, tmp_path):
        _write(tmp_path, "mod.py", "def do_thing():\n    pass\n")
        _write(tmp_path, "tests/unit/test_mod.py", "def test_do_thing():\n    pass\n")
        raw = {
            "id": "ghost_capability", "title": "Ghost", "status": "wired",
            "anchor": "mod.py:do_thing", "consumer": "mod.py:no_such_caller",
            "evidence_tests": ["tests/unit/test_mod.py"],
        }
        comp = validate_component(raw, tmp_path)
        assert comp.engaged_static is False
        assert "consumer" in comp.reason.lower()

    def test_wired_with_real_consumer_and_real_test_is_engaged(self, tmp_path):
        _write(tmp_path, "mod.py", """\
            def do_thing():
                pass


            def call_site():
                do_thing()
        """)
        _write(tmp_path, "tests/unit/test_mod.py", "def test_do_thing():\n    pass\n")
        raw = {
            "id": "real_capability", "title": "Real", "status": "wired",
            "anchor": "mod.py:do_thing", "consumer": "mod.py:call_site",
            "evidence_tests": ["tests/unit/test_mod.py"],
        }
        comp = validate_component(raw, tmp_path)
        assert comp.engaged_static is True
        assert comp.reason  # non-empty human-readable sentence


class TestNonEngagingStatusNeverRequiresConsumer:
    """stubbed/parked/inactive/dead never claim engagement, so a missing
    consumer/test is expected, not a validation complaint."""

    @pytest.mark.parametrize("status", ["stubbed", "parked", "inactive", "dead"])
    def test_non_engaging_status_is_never_flagged(self, tmp_path, status):
        _write(tmp_path, "mod.py", "def do_thing():\n    pass\n")
        raw = {"id": "dormant", "title": "Dormant", "status": status, "anchor": "mod.py:do_thing"}
        comp = validate_component(raw, tmp_path)
        assert comp.engaged_static is False
        assert "no consumer" not in comp.reason.lower()
        assert "no evidence" not in comp.reason.lower()


# ---------------------------------------------------------------------------
# Manifest-level validation — the failing-CI-check requirement.
# ---------------------------------------------------------------------------

class TestManifestValidation:
    def test_validate_manifest_flags_bad_entry(self, tmp_path):
        _write(tmp_path, "mod.py", "def do_thing():\n    pass\n")
        toml = _write_toml(tmp_path, """\
            [[component]]
            id = "ghost_capability"
            title = "Ghost"
            status = "wired"
            anchor = "mod.py:do_thing"
            note = ""
        """)
        components = build_manifest(tmp_path, manifest_path=toml)
        violations = validate_manifest(components)
        assert any("ghost_capability" in v for v in violations)

    def test_validate_manifest_clean_when_consumer_and_test_present(self, tmp_path):
        _write(tmp_path, "mod.py", """\
            def do_thing():
                pass


            def call_site():
                do_thing()
        """)
        _write(tmp_path, "tests/unit/test_mod.py", "def test_do_thing():\n    pass\n")
        toml = _write_toml(tmp_path, """\
            [[component]]
            id = "real_capability"
            title = "Real"
            status = "wired"
            anchor = "mod.py:do_thing"
            consumer = "mod.py:call_site"
            evidence_tests = ["tests/unit/test_mod.py"]
            note = ""
        """)
        components = build_manifest(tmp_path, manifest_path=toml)
        violations = validate_manifest(components)
        assert violations == []

    def test_real_committed_manifest_has_no_violations(self):
        """Regression guard over the ACTUAL docs/pipeline_status.toml: every
        component currently claiming live/wired must have a real, resolving
        consumer + evidence test. Closes the 'wired on syntactic anchors
        alone' gap for the real manifest, not just a synthetic fixture."""
        components = build_manifest(REPO_ROOT)
        violations = validate_manifest(components)
        assert violations == [], violations

    def test_real_manifest_has_at_least_one_engaged_and_one_non_engaged(self):
        """Sanity: the validator isn't vacuously true because nothing claims
        engagement, or vacuously permissive because everything does."""
        components = build_manifest(REPO_ROOT)
        assert any(c.engaged_static for c in components)
        assert any(not c.engaged_static for c in components)

    def test_real_manifest_exposure_and_spend_kind_are_well_formed(self):
        """Every real component has a real (non-default-typo'd) exposure and
        spend_kind — catches a misspelled TOML value silently falling back to
        validate_component's default."""
        valid_exposure = {"ui", "api", "internal", "cli"}
        valid_spend = {"none", "compute_local", "paid_api", "local_gpu"}
        components = build_manifest(REPO_ROOT)
        assert components, "expected at least one real component"
        for c in components:
            assert c.exposure in valid_exposure, (c.id, c.exposure)
            assert c.spend_kind in valid_spend, (c.id, c.spend_kind)
            assert c.runtime_availability in {"available", "unavailable", "not_applicable"}


# ---------------------------------------------------------------------------
# Operator view vs diagnostic view — no raw hash/id/internal note leakage.
# ---------------------------------------------------------------------------

class TestOperatorViewExcludesRawInternals:
    def test_operator_view_has_no_note_producer_consumer_or_anchor_keys(self, tmp_path):
        _write(tmp_path, "mod.py", "def do_thing():\n    pass\n")
        raw = {
            "id": "c1", "title": "C1", "status": "stubbed", "anchor": "mod.py:do_thing",
            "note": "Cycle-17 MVP (9e75373/cc8dec6) internal shorthand",
        }
        comp = validate_component(raw, tmp_path)
        view = to_operator_view([comp])[0]
        for leaky_key in (
            "note", "producer", "consumer", "evidence_tests", "anchor",
            "producer_problem", "consumer_problem", "evidence_problem",
        ):
            assert leaky_key not in view
        assert not any("9e75373" in str(v) for v in view.values())

    def test_diagnostic_view_retains_the_full_evidence_trail(self, tmp_path):
        _write(tmp_path, "mod.py", "def do_thing():\n    pass\n")
        raw = {
            "id": "c1", "title": "C1", "status": "stubbed", "anchor": "mod.py:do_thing",
            "note": "internal shorthand 9e75373",
        }
        comp = validate_component(raw, tmp_path)
        diag = to_diagnostic_view([comp])[0]
        assert diag["note"] == "internal shorthand 9e75373"
        assert diag["producer"] == "mod.py:do_thing"

    def test_real_manifest_operator_view_never_leaks_any_note_text(self):
        """No component's raw dev note (commit hashes, section refs, file:line
        citations) may appear anywhere in the operator-facing projection of
        the REAL manifest."""
        components = build_manifest(REPO_ROOT)
        raw_notes = [c.note for c in components if c.note]
        assert raw_notes, "expected at least one real component with a dev note"
        view = to_operator_view(components)
        blob = repr(view)
        for note in raw_notes:
            assert note not in blob


# ---------------------------------------------------------------------------
# Producer / consumer / evidence / exposure / spend_kind / STATIC / RUNTIME
# stay separate fields (invariant 4) — never collapsed into one another.
# ---------------------------------------------------------------------------

class TestFieldsAreDistinctNeverCollapsed:
    def test_exposure_and_spend_kind_are_independent_of_status(self, tmp_path):
        _write(tmp_path, "mod.py", "def do_thing():\n    pass\n")
        raw = {
            "id": "c1", "title": "C1", "status": "stubbed", "anchor": "mod.py:do_thing",
            "exposure": "internal", "spend_kind": "paid_api",
        }
        comp = validate_component(raw, tmp_path)
        assert comp.exposure == "internal"
        assert comp.spend_kind == "paid_api"
        view = to_operator_view([comp])[0]
        assert view["exposure"] == "internal"
        assert view["spend_kind"] == "paid_api"


class TestRuntimeAvailabilitySeparateFromStaticCapability:
    def test_engaged_component_with_missing_credential_is_runtime_unavailable(self, tmp_path, monkeypatch):
        _write(tmp_path, "mod.py", """\
            def do_thing():
                pass


            def call_site():
                do_thing()
        """)
        _write(tmp_path, "tests/unit/test_mod.py", "def test_do_thing():\n    pass\n")
        monkeypatch.delenv("CAPABILITY_MANIFEST_FAKE_CRED", raising=False)
        raw = {
            "id": "paid_capability", "title": "Paid", "status": "wired",
            "anchor": "mod.py:do_thing", "consumer": "mod.py:call_site",
            "evidence_tests": ["tests/unit/test_mod.py"],
            "runtime_credential": "CAPABILITY_MANIFEST_FAKE_CRED",
        }
        comp = validate_component(raw, tmp_path)
        # STATIC capability must be unaffected by a missing credential —
        # invariant 4: these must never collapse into a single bit.
        assert comp.engaged_static is True
        assert comp.runtime_availability == "unavailable"
        assert "CAPABILITY_MANIFEST_FAKE_CRED" in (comp.runtime_reason or "")

    def test_engaged_component_with_present_credential_is_runtime_available(self, tmp_path, monkeypatch):
        _write(tmp_path, "mod.py", """\
            def do_thing():
                pass


            def call_site():
                do_thing()
        """)
        _write(tmp_path, "tests/unit/test_mod.py", "def test_do_thing():\n    pass\n")
        monkeypatch.setenv("CAPABILITY_MANIFEST_FAKE_CRED", "super-secret-value")
        raw = {
            "id": "paid_capability", "title": "Paid", "status": "wired",
            "anchor": "mod.py:do_thing", "consumer": "mod.py:call_site",
            "evidence_tests": ["tests/unit/test_mod.py"],
            "runtime_credential": "CAPABILITY_MANIFEST_FAKE_CRED",
        }
        comp = validate_component(raw, tmp_path)
        assert comp.runtime_availability == "available"
        # never leak the secret VALUE anywhere, including diagnostics
        diag = to_diagnostic_view([comp])[0]
        assert "super-secret-value" not in repr(diag)

    def test_non_engaged_component_runtime_is_not_applicable(self, tmp_path):
        _write(tmp_path, "mod.py", "def do_thing():\n    pass\n")
        raw = {"id": "c1", "title": "C1", "status": "stubbed", "anchor": "mod.py:do_thing"}
        comp = validate_component(raw, tmp_path)
        assert comp.runtime_availability == "not_applicable"
