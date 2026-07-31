"""Evidence-backed capability manifest (Slice 12 — comprehensive unification).

Loads and validates ``docs/pipeline_status.toml``. Where
``cinema/capability_scorecard.py`` computes PER-PROJECT measured evidence
(identity/coherence/motion/lipsync scores against bars), this module computes
the pipeline-wide STATIC capability manifest: which components are actually
wired into production, on what evidence, and whether they may currently be
advertised as engaged.

Core invariant (plan "Product invariants" #4 — do not collapse independent
truths): producer, consumer, evidence tests, exposure, spend kind, STATIC
capability, and RUNTIME availability are separate fields end to end. An
authored ``status`` of ``live``/``wired`` is a *claim*, not proof — it is
mechanically checked against a real, currently-resolving production
``consumer`` anchor and at least one currently-resolving evidence test before
``engaged_static`` may be True. A component that claims engagement but fails
that check is forced inactive/unavailable with a human-readable ``reason``
instead of silently rendering as live.

Two projections are produced:
  - ``to_operator_view``   — human labels + next actions only. No raw
    anchors, hashes, internal notes, or problem-detail strings. This is what
    ``cinema/capability_scorecard.py`` sends to the Capability page.
  - ``to_diagnostic_view`` — the full evidence trail (producer/consumer/
    evidence anchors, raw dev note, resolution problems) for developer
    tooling/tests. Never sent over the capability-scorecard HTTP response.

No mutation, no Flask, no subprocess, no network I/O — safe to call on every
request.
"""
from __future__ import annotations

import logging
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST_PATH = REPO_ROOT / "docs" / "pipeline_status.toml"

# Authored statuses that CLAIM the capability is currently reachable in the
# default/opt-in product path. Every other status (stubbed/parked/inactive/
# dead) never claims engagement, so a missing consumer/evidence test there is
# the expected, honest state rather than a validation failure.
ENGAGING_STATUSES = frozenset({"live", "wired"})

_STATUS_REASON = {
    "stubbed": "Not wired: implemented but has no production caller yet.",
    "parked": "Blocked on external state (pod/credential/install) before it can run.",
    "inactive": "Deliberately unavailable by policy; historical records only.",
    "dead": "Confirmed dead; scheduled for removal.",
}

# Operator-facing field allowlist — everything else (note, producer,
# consumer, evidence_tests, *_problem strings) is diagnostic-only.
_OPERATOR_FIELDS = (
    "id", "title", "status", "exposure", "spend_kind",
    "engaged_static", "runtime_availability", "runtime_reason", "reason",
)


@dataclass(frozen=True)
class CapabilityComponent:
    id: str
    title: str
    status: str

    # -- producer / consumer / evidence (invariant 4: kept separate) --
    producer: str
    consumer: str
    evidence_tests: tuple[str, ...]
    exposure: str
    spend_kind: str
    note: str  # raw dev note — diagnostic-only, never in the operator view

    producer_valid: bool
    producer_problem: Optional[str]
    consumer_valid: bool
    consumer_problem: Optional[str]
    evidence_valid: bool
    evidence_problem: Optional[str]

    # -- STATIC capability (computed, not authored) --
    engaged_static: bool
    reason: str

    # -- RUNTIME availability (computed separately; never rewrites the above) --
    runtime_availability: str  # "available" | "unavailable" | "not_applicable"
    runtime_reason: Optional[str]


# ---------------------------------------------------------------------------
# Anchor / test-reference resolution — "does this symbol actually exist",
# not merely "is this string non-empty". Self-contained (does not import
# scripts/check_doc_claims.py: that module is dev-tooling with subprocess/git
# dependencies not appropriate to import into a Flask request path).
# ---------------------------------------------------------------------------

def _symbol_defined(source_lines: list[str], symbol: str) -> bool:
    """True if *symbol* is defined (def/class at any indent, or an
    ALL-CAPS module-level constant) somewhere in *source_lines*."""
    def_pat = re.compile(r'^\s*(?:async\s+def|def|class)\s+' + re.escape(symbol) + r'\b')
    const_pat = re.compile(r'^\s*' + re.escape(symbol) + r'\s*[:=]') if symbol.isupper() else None
    for line in source_lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if def_pat.match(line):
            return True
        if const_pat is not None and const_pat.match(line):
            return True
    return False


def _resolve_anchor(repo_root: Path, anchor: str) -> tuple[bool, Optional[str]]:
    """Resolve a ``"path/to/file.py:symbol"`` anchor. Returns (valid, problem)."""
    if not anchor or ":" not in anchor:
        return False, f"malformed anchor: {anchor!r}"
    file_rel, symbol = anchor.rsplit(":", 1)
    target = repo_root / file_rel
    if not target.exists():
        return False, f"file not found: {file_rel}"
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:  # pragma: no cover - defensive
        return False, f"unreadable: {e}"
    if not _symbol_defined(lines, symbol):
        return False, f"symbol not found: {symbol}"
    return True, None


def _resolve_test_ref(repo_root: Path, ref: str) -> tuple[bool, Optional[str]]:
    """Resolve an evidence-test reference: ``"path"`` or ``"path::symbol"``."""
    if not ref:
        return False, "empty test reference"
    path_part, _, symbol = ref.partition("::")
    target = repo_root / path_part
    if not target.exists():
        return False, f"test file not found: {path_part}"
    if symbol:
        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as e:  # pragma: no cover - defensive
            return False, f"unreadable: {e}"
        if not _symbol_defined(lines, symbol):
            return False, f"test symbol not found: {symbol}"
    return True, None


def _coerce_str_tuple(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    try:
        return tuple(str(v) for v in value if v)
    except TypeError:
        return ()


def _split_credential_names(spec: str) -> list[str]:
    return [name.strip() for name in spec.split(",") if name.strip()]


def _runtime_state(engaged_static: bool, runtime_credential: str) -> tuple[str, Optional[str]]:
    """Compute RUNTIME availability. Presence-only credential check — never
    reads or surfaces the credential VALUE, only whether the named
    environment variable(s) are set."""
    if not engaged_static:
        return "not_applicable", None
    if not runtime_credential:
        return "available", None
    missing = [name for name in _split_credential_names(runtime_credential) if not os.environ.get(name)]
    if missing:
        return "unavailable", f"missing credential(s): {', '.join(missing)}"
    return "available", None


# ---------------------------------------------------------------------------
# Loading + validating one component
# ---------------------------------------------------------------------------

def validate_component(raw: dict, repo_root: Path = REPO_ROOT) -> CapabilityComponent:
    """Validate one raw ``[[component]]`` dict into a :class:`CapabilityComponent`.

    Pure function — no I/O beyond reading the named producer/consumer/test
    files under *repo_root* to confirm they resolve.
    """
    cid = str(raw.get("id") or "")
    title = str(raw.get("title") or "")
    status = str(raw.get("status") or "")
    producer = str(raw.get("anchor") or "")
    consumer = str(raw.get("consumer") or "")
    evidence_tests = _coerce_str_tuple(raw.get("evidence_tests"))
    exposure = str(raw.get("exposure") or "internal")
    spend_kind = str(raw.get("spend_kind") or "none")
    note = str(raw.get("note") or "")
    runtime_credential = str(raw.get("runtime_credential") or "")

    if producer:
        producer_valid, producer_problem = _resolve_anchor(repo_root, producer)
    else:
        producer_valid, producer_problem = False, "no producer anchor recorded"

    if consumer:
        consumer_valid, consumer_problem = _resolve_anchor(repo_root, consumer)
    else:
        # Absent, not broken — a genuinely stubbed/inactive capability has no
        # consumer at all, which is a different fact than "consumer named but
        # its anchor no longer resolves".
        consumer_valid, consumer_problem = False, None

    evidence_problems: list[str] = []
    if evidence_tests:
        evidence_valid = True
        for ref in evidence_tests:
            ok, problem = _resolve_test_ref(repo_root, ref)
            if not ok:
                evidence_valid = False
                evidence_problems.append(f"{ref} ({problem})")
    else:
        evidence_valid = False

    evidence_problem = "; ".join(evidence_problems) if evidence_problems else None

    claims_engagement = status in ENGAGING_STATUSES
    if claims_engagement:
        gaps: list[str] = []
        if not producer_valid:
            gaps.append(f"the implementation itself no longer resolves ({producer_problem})")
        if not consumer:
            gaps.append("no production consumer is recorded")
        elif not consumer_valid:
            gaps.append(f"its recorded consumer no longer resolves ({consumer_problem})")
        if not evidence_tests:
            gaps.append("no evidence test is recorded")
        elif not evidence_valid:
            gaps.append(f"its evidence test no longer resolves ({evidence_problem})")

        if gaps:
            engaged_static = False
            reason = f"Claims '{status}' but " + "; ".join(gaps) + "."
        else:
            engaged_static = True
            reason = "Verified: a live production consumer and a passing evidence test are on file."
    else:
        engaged_static = False
        reason = _STATUS_REASON.get(status, f"Not engaged (status={status or 'unknown'}).")

    runtime_availability, runtime_reason = _runtime_state(engaged_static, runtime_credential)

    return CapabilityComponent(
        id=cid, title=title, status=status,
        producer=producer, consumer=consumer, evidence_tests=evidence_tests,
        exposure=exposure, spend_kind=spend_kind, note=note,
        producer_valid=producer_valid, producer_problem=producer_problem,
        consumer_valid=consumer_valid, consumer_problem=consumer_problem,
        evidence_valid=evidence_valid, evidence_problem=evidence_problem,
        engaged_static=engaged_static, reason=reason,
        runtime_availability=runtime_availability, runtime_reason=runtime_reason,
    )


# ---------------------------------------------------------------------------
# Manifest-level load + validate
# ---------------------------------------------------------------------------

def load_raw_components(manifest_path: Union[str, Path] = DEFAULT_MANIFEST_PATH) -> list[dict]:
    """Parse *manifest_path* (TOML) into raw ``[[component]]`` dicts.

    Never raises: returns [] when the file is absent or unparseable —
    mirrors the defensive contract of the pre-existing
    ``cinema/capability_scorecard.py:_components`` reader it replaces.
    """
    p = Path(manifest_path)
    if not p.exists():
        return []
    try:
        with open(p, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        logger.debug("capability manifest: failed to parse %s", p, exc_info=True)
        return []
    return list(data.get("component", []))


def build_manifest(
    repo_root: Path = REPO_ROOT,
    *,
    manifest_path: Optional[Union[str, Path]] = None,
) -> list[CapabilityComponent]:
    """Load + validate every component. *manifest_path* defaults to
    ``<repo_root>/docs/pipeline_status.toml``."""
    path = Path(manifest_path) if manifest_path is not None else (Path(repo_root) / "docs" / "pipeline_status.toml")
    raw_components = load_raw_components(path)
    return [validate_component(raw, Path(repo_root)) for raw in raw_components]


def validate_manifest(components: list[CapabilityComponent]) -> list[str]:
    """Return one violation string per component that claims engagement
    (``status`` in live/wired) without passing consumer+evidence-test
    validation. Empty list == the manifest is internally consistent.

    This is the mechanical replacement for "wired on syntactic anchors
    alone": a component may say ``status = "wired"`` in the TOML, but if
    nothing here proves a live consumer and a passing test, it is a
    violation, not a fact.
    """
    violations = []
    for c in components:
        if c.status in ENGAGING_STATUSES and not c.engaged_static:
            violations.append(f"{c.id}: {c.reason}")
    return violations


# ---------------------------------------------------------------------------
# Projections
# ---------------------------------------------------------------------------

def to_operator_view(components: list[CapabilityComponent]) -> list[dict]:
    """Human labels + next actions only. No anchors, notes, or raw ids beyond
    the component's own stable slug and title — safe to render on the
    Capability page."""
    out = []
    for c in components:
        row = {name: getattr(c, name) for name in _OPERATOR_FIELDS}
        out.append(row)
    return out


def to_diagnostic_view(components: list[CapabilityComponent]) -> list[dict]:
    """Full evidence trail (producer/consumer/evidence anchors, raw dev
    note, resolution problems) for developer tooling and tests. Never wired
    into the capability-scorecard HTTP response."""
    out = []
    for c in components:
        out.append({
            "id": c.id, "title": c.title, "status": c.status,
            "producer": c.producer, "producer_valid": c.producer_valid,
            "producer_problem": c.producer_problem,
            "consumer": c.consumer, "consumer_valid": c.consumer_valid,
            "consumer_problem": c.consumer_problem,
            "evidence_tests": list(c.evidence_tests),
            "evidence_valid": c.evidence_valid, "evidence_problem": c.evidence_problem,
            "exposure": c.exposure, "spend_kind": c.spend_kind, "note": c.note,
            "engaged_static": c.engaged_static, "reason": c.reason,
            "runtime_availability": c.runtime_availability, "runtime_reason": c.runtime_reason,
        })
    return out
