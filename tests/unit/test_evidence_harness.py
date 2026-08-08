"""The evidence harness plans for free and refuses to spend on a stale price.

The register (docs/EVIDENCE-REGISTER.md) is a list of claims. This harness is
what turns them into renders, and renders cost money — so the interesting
behaviour to pin is not what it generates but what it REFUSES to.
"""

from __future__ import annotations

import pytest

from scripts.evidence_harness import build_plan, main


def test_prices_are_read_from_the_ledger_table_not_typed() -> None:
    """A number typed into the plan would be right the day it was written.

    The same rule as the character-creation estimate: the figure the operator
    authorises has to come from the table the durable ledger reserves against,
    so a price change moves the plan without anyone remembering to.
    """

    from cost_tracker import API_COST_USD

    units = {cell.engine: cell.unit_usd
             for hypothesis in build_plan() for cell in hypothesis.cells}
    assert units, "the plan has no cells"
    for engine, unit in units.items():
        assert unit == API_COST_USD[engine], engine


def test_every_hypothesis_declares_what_would_falsify_it() -> None:
    """A claim with no falsifier is not a hypothesis, it is a preference.

    And a claim whose only judge is the instrument that produced it cannot be
    tested by it — which is exactly how ADR-092 happened.
    """

    for hypothesis in build_plan():
        assert hypothesis.falsifier.strip(), hypothesis.id
        assert hypothesis.decided_by.strip(), hypothesis.id
        assert hypothesis.cells, hypothesis.id


def test_no_off_angle_cell_is_decided_by_the_identity_scorer() -> None:
    """ADR-092 removed GhostFaceNet as an instrument for these readings.

    Re-admitting it under another name would be the same error with better
    branding, so the register is checked rather than trusted.
    """

    for hypothesis in build_plan():
        decided = hypothesis.decided_by.lower()
        if "ghostfacenet" in decided:
            assert "not ghostfacenet" in decided, hypothesis.id


def test_every_hypothesis_has_at_least_two_arms() -> None:
    """One arm measures nothing. A number with no control is a number."""

    for hypothesis in build_plan():
        arms = {cell.arm for cell in hypothesis.cells}
        assert len(arms) >= 2, f"{hypothesis.id} has arms {arms}"


def test_planning_spends_nothing_and_succeeds(capsys) -> None:
    assert main(["--plan", "--skip-instrument-check"]) == 0
    output = capsys.readouterr().out
    assert "nothing below has been spent" in output
    assert "TOTAL:" in output


def test_running_without_an_authorised_amount_is_refused(capsys) -> None:
    assert main(["--run", "H4", "--skip-instrument-check"]) == 1
    assert "REFUSED" in capsys.readouterr().out


def test_an_amount_that_does_not_match_the_plan_is_refused(capsys) -> None:
    """The guard that matters. An authorisation priced against an older plan
    must be re-read, not re-approved — otherwise editing a cell silently widens
    a spend the operator already agreed to."""

    assert main([
        "--run", "H4", "--authorize-usd", "5.00", "--skip-instrument-check",
    ]) == 1
    output = capsys.readouterr().out
    assert "authorised $5.00" in output
    assert "must match exactly" in output


def test_an_unknown_hypothesis_id_is_refused_rather_than_ignored(capsys) -> None:
    """Silently planning nothing for a typo would report success and spend
    nothing, which reads identically to a plan that ran."""

    assert main(["--run", "NOPE", "--skip-instrument-check"]) == 2
    assert "unknown hypothesis ids" in capsys.readouterr().out


def test_the_instrument_check_can_refuse(monkeypatch, capsys) -> None:
    """Without --skip-instrument-check the harness runs the metric validation
    first, and a failure there stops planning as well as running.

    An unvalidated metric is how a harness confirms whatever it was built to
    confirm.
    """

    import scripts.evidence_harness as harness

    monkeypatch.setattr(
        harness, "_metrics_are_validated", lambda: (False, "2 failed"),
    )
    assert harness.main(["--plan"]) == 2
    assert "Refusing to plan or run on unvalidated instruments" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Money rounds UP to the cent, and the printed figure is the one compared
# ---------------------------------------------------------------------------

def test_the_printed_total_is_the_amount_that_will_be_accepted(capsys) -> None:
    """A real defect this pinned: the plan printed "$1.13" while comparing
    against 1.134, so following its own printed instruction was REFUSED — with
    a message claiming both numbers were $1.13.

    Money is denominated in cents. The total is ceilinged to the cent so the
    authorised amount can never be LESS than what the run may spend, and the
    comparison uses that same number.
    """

    import re

    main(["--plan", "--skip-instrument-check"])
    printed = capsys.readouterr().out
    match = re.search(r"--authorize-usd (\d+\.\d{2})", printed)
    assert match, printed
    quoted = float(match.group(1))

    # The exact amount the plan told the operator to pass must be accepted.
    assert main([
        "--run", "H4", "--authorize-usd", f"{_h4_total():.2f}",
        "--skip-instrument-check", "--dry-run",
    ]) == 0
    assert quoted >= _raw_total() - 1e-9, "quoted less than the true cost"


def _raw_total() -> float:
    return sum(h.usd for h in build_plan())


def _h4_total() -> float:
    import math
    h4 = next(h for h in build_plan() if h.id == "H4")
    return math.ceil(h4.usd * 100) / 100


def test_a_cent_under_the_ceilinged_total_is_still_refused() -> None:
    """Ceiling is a safety direction, not a slack allowance."""

    assert main([
        "--run", "H4", "--authorize-usd", f"{_h4_total() - 0.01:.2f}",
        "--skip-instrument-check",
    ]) == 1


def test_an_unwired_hypothesis_refuses_instead_of_silently_doing_nothing(capsys) -> None:
    """Exiting 0 with no render would read exactly like a run that happened."""

    h3 = next(h for h in build_plan() if h.id == "H3")
    import math
    assert main([
        "--run", "H3", "--authorize-usd", f"{math.ceil(h3.usd * 100) / 100:.2f}",
        "--skip-instrument-check",
    ]) == 3
    assert "have no render path yet" in capsys.readouterr().out


def test_the_dry_run_resolves_real_assets_and_spends_nothing(capsys) -> None:
    """Proves the wiring reaches real references BEFORE any money moves —
    a run that fails on a missing asset after paying for keyframes is the
    expensive way to learn the project was not ready."""

    assert main([
        "--run", "H4", "--authorize-usd", f"{_h4_total():.2f}",
        "--skip-instrument-check", "--dry-run",
    ]) == 0
    output = capsys.readouterr().out
    assert "no provider call made" in output
    assert '"references_available"' in output


# ---------------------------------------------------------------------------
# The H4 verdict must be able to disagree with the change it is testing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rows,expected", [
    ([{"led": 0.85, "withheld": 0.12, "floor": 0.10}], "SUPPORTS"),
    ([{"led": 0.85, "withheld": 0.80, "floor": 0.10}], "REFUTES"),
    ([{"led": 0.85, "withheld": 0.45, "floor": 0.10}], "PARTIAL"),
    ([{"led": 0.85, "withheld": 0.84, "floor": 0.83}], "INCONCLUSIVE"),
])
def test_the_verdict_can_reach_every_outcome(rows, expected) -> None:
    """A verdict function that can only agree with its author proves nothing.

    REFUTES is the one that matters: it fires when the withheld arm scores close
    to the keyframe-led arm, which would mean reference ORDER is not what
    carries composition and the ADR-098 fix is inert.
    """

    from evidence_cells.h4_veo_keyframe import verdict

    assert verdict(rows)["reading"].startswith(expected)
