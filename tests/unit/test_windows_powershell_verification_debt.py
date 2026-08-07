"""Guards for the shipped Windows PowerShell surface's verification debt.

Thirteen PowerShell scripts (~2700 lines) run on a privileged Windows host: ACL
hardening, firewall rule mutation, sshd restart, scheduled-task registration. No
test in this repository has ever executed a line of them. Their "tests" assert
that substrings appear in the source text.

That gap shipped a real defect. ``Register-WorkerTask.ps1``'s
``Assert-InstalledManualTask`` read ``RunLevel``, ``Enabled``,
``StartWhenAvailable`` and ``WakeToRun`` out of ``Export-ScheduledTask`` XML as
bare properties. Task Scheduler omits default-valued elements from that XML, and
the manual-worker contract sets all four to their defaults, so the elements are
absent exactly when they hold the required values. Under
``Set-StrictMode -Version Latest`` reading an absent element is a TERMINATING
error, so the assertion was unsatisfiable on every Windows host -- while 367
assertions in that script's test file, 259 of them substring matches, all passed.

These guards do not replace executable coverage; that needs ``pwsh`` in CI and a
captured fixture from the target host. They bound the debt, make it visible, and
close the specific class that shipped.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "deploy"
TESTS = REPO / "tests" / "unit"


# Elements Task Scheduler omits from Export-ScheduledTask XML when they hold
# their default value. Reading any of these as a property under
# `Set-StrictMode -Version Latest` throws PropertyNotFoundStrict on a correctly
# configured task.
#
# Measured on the RTX 5070 Ti worker host (Windows 11, 60 registered tasks):
#   <RunLevel>   present in 16/60 tasks, and in 0 of the LeastPrivilege ones
#   <Enabled>    absent in 40/40 enabled tasks
#   <WakeToRun>  absent in 40/40 tasks
# Direct reproduction confirmed `.RunLevel` and `.WakeToRun` both throw.
SERIALIZER_OMITS_AT_DEFAULT = frozenset(
    {
        "RunLevel",  # default LeastPrivilege
        "Enabled",  # default true
        "StartWhenAvailable",  # default false
        "WakeToRun",  # default false
        "DisallowStartIfOnBatteries",  # default true
        "StopIfGoingOnBatteries",  # default true
        "RunOnlyIfNetworkAvailable",  # default false
        "Hidden",  # default false
    }
)

# Every shipped PowerShell script, and the strongest verification that currently
# exists for it. Adding a script without adding an entry fails the inventory
# guard below -- the debt may shrink, never silently grow.
#
#   "executable"  -- some test actually runs this code
#   "source-text" -- only substring assertions over the file's text
POWERSHELL_COVERAGE = {
    "windows-liveportrait-worker/Benchmark-Worker.ps1": "source-text",
    "windows-liveportrait-worker/Control-Worker.ps1": "source-text",
    "windows-liveportrait-worker/Install-Worker.ps1": "source-text",
    "windows-liveportrait-worker/Install-WorkerControl.ps1": "source-text",
    "windows-liveportrait-worker/Register-WorkerTask.ps1": "source-text",
    "windows-liveportrait-worker/Set-WorkerSecret.ps1": "source-text",
    "windows-liveportrait-worker/Start-Worker.ps1": "source-text",
    "windows-liveportrait-worker/Test-Worker.ps1": "source-text",
    "windows-flux2-klein/Benchmark-Candidate.ps1": "source-text",
    "windows-flux2-klein/Install-Candidate.ps1": "source-text",
    "windows-flux2-klein/Probe-Candidate.ps1": "source-text",
    "windows-flux2-lora/Benchmark-Candidate.ps1": "source-text",
    "windows-flux2-lora/Install-Candidate.ps1": "source-text",
}

# Substring-assertion budget: assertions that match text against another
# language's source, which can only fail when someone edits the matched string.
#
# These ceilings originally counted EVERY assert in each file, which made the
# guard dishonest in the direction that matters -- it charged a file for adding
# *behavioural* assertions. It fired on test_windows_identity_lora_gateway.py
# when two real assertions were added, a file holding 0 source-text assertions
# out of 225. A control that penalises good tests to keep a bad-test counter
# flat is the same defect class this module exists to catch, so it now counts
# only the pattern it names.
#
# Lowering a number means real coverage replaced text matching. Raising one
# means the debt grew and needs an explicit decision in the same commit.
SOURCE_TEXT_ASSERTION_BUDGET = {
    "test_windows_liveportrait_worker.py": 256,
    "test_windows_flux2_klein_candidate.py": 4,
    "test_windows_identity_lora_gateway.py": 0,
}

# `assert <expr> in <bare identifier>` -- the identifier being a variable that
# holds script source text. Deliberately excludes `in {...}` / `in [...]` /
# `in (...)`, which are membership checks over real values.
_SOURCE_TEXT_ASSERT = re.compile(
    r"^\s*assert\b.*\bin\s+[a-z_][a-z0-9_]*\s*(?:,.*)?$", re.M
)


def _powershell_scripts() -> dict[str, str]:
    return {
        path.relative_to(DEPLOY).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(DEPLOY.rglob("*.ps1"))
    }


def test_no_script_reads_a_serializer_omitted_element_as_a_property() -> None:
    """The exact class that shipped: an XML read that throws when the task is right.

    This fails on the pre-fix Register-WorkerTask.ps1 and passes on the current
    one, so it is a reversion control rather than a restatement of the source.
    """

    # `$exported.Task.Settings.WakeToRun`, `$x.Task.Principals.Principal.RunLevel`
    chain = re.compile(r"\$\w+\.Task(?:\.\w+)+")
    offenders: list[str] = []
    for name, text in _powershell_scripts().items():
        if "Set-StrictMode" not in text:
            continue
        for match in chain.finditer(text):
            leaf = match.group(0).rsplit(".", 1)[-1]
            if leaf in SERIALIZER_OMITS_AT_DEFAULT:
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{name}:{line} reads .{leaf}")

    assert not offenders, (
        "Task Scheduler omits these elements from Export-ScheduledTask XML when "
        "they hold their default value, so reading them as properties under "
        "Set-StrictMode throws exactly when the task is correctly configured. "
        "Read them from the live CIM definition instead, or use SelectNodes and "
        "treat absence as the default:\n  " + "\n  ".join(offenders)
    )


def test_every_powershell_script_declares_its_verification_level() -> None:
    """A new privileged script may not enter the repo with undeclared coverage."""

    found = set(_powershell_scripts())
    declared = set(POWERSHELL_COVERAGE)
    assert not found - declared, (
        "PowerShell scripts ship to a privileged Windows host with no declared "
        "verification level. Add them to POWERSHELL_COVERAGE, honestly: "
        f"{sorted(found - declared)}"
    )
    assert not declared - found, (
        "POWERSHELL_COVERAGE names scripts that no longer exist: "
        f"{sorted(declared - found)}"
    )


def test_source_text_assertion_debt_does_not_grow() -> None:
    """Substring assertions over another language's source are near-vacuous.

    They fail only when someone edits the matched text, never when the logic is
    wrong. Capping them keeps a passing suite total from being read as evidence
    of behaviour.
    """

    over_budget: list[str] = []
    for name, ceiling in SOURCE_TEXT_ASSERTION_BUDGET.items():
        path = TESTS / name
        if not path.exists():
            continue
        actual = len(_SOURCE_TEXT_ASSERT.findall(path.read_text(encoding="utf-8")))
        if actual > ceiling:
            over_budget.append(f"{name}: {actual} > {ceiling}")

    assert not over_budget, (
        "Source-text assertion debt grew. These assertions cannot fail when the "
        "PowerShell logic is wrong -- prefer executable coverage. If the growth "
        "is deliberate, raise the ceiling in the same commit and say why:\n  "
        + "\n  ".join(over_budget)
    )


def test_no_powershell_script_is_executed_by_any_test() -> None:
    """Pins the honest headline: zero executable coverage today.

    Delete this test in the commit that adds a `pwsh` CI job. Its failure is the
    good news -- it means the debt above finally started shrinking.
    """

    runners = [
        path.name
        for path in sorted(TESTS.glob("test_*.py"))
        if re.search(r"subprocess\.\w+\(\s*\[?\s*[\"']pwsh", path.read_text(encoding="utf-8"))
    ]
    assert not runners, (
        "A test now executes PowerShell. Update POWERSHELL_COVERAGE to mark the "
        f"covered scripts 'executable' and delete this pin: {runners}"
    )
