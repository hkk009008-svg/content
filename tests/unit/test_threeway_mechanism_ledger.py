"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_mechanism_ledger.py -q"""

from threeway import LOAD_BEARING_KINDS
from scripts import threeway_mechanism_ledger as ledger


def test_ledger_covers_every_load_bearing_kind():
    rows = ledger.collect_mechanisms()
    assert set(rows) == set(LOAD_BEARING_KINDS)
    assert {row.status for row in rows.values()} == {"live"}
    assert rows["co_sign"].status == "live"
    assert rows["human_approval"].status == "live"
    assert rows["brief"].status == "live"


def test_ledger_render_names_verifier_command_for_each_kind():
    rendered = ledger.render_markdown(ledger.collect_mechanisms())
    for kind in sorted(LOAD_BEARING_KINDS):
        assert f"| `{kind}` |" in rendered
    assert ".venv/bin/python scripts/threeway_mechanism_ledger.py --check" in rendered
