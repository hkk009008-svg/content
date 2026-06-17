from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs" / "REMEDIATION-INVENTORY.md"


def _inventory_rows(text: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 13 or cells[0] in {"id", "----"}:
            continue
        rows[cells[0]] = {
            "id": cells[0],
            "status": cells[11],
        }
    return rows


def test_verified_inventory_rows_are_not_described_as_still_open() -> None:
    text = INVENTORY.read_text(encoding="utf-8")
    rows = _inventory_rows(text)
    verified_ids = {row_id for row_id, row in rows.items() if row["status"] == "verified"}

    stale_mentions = [
        row_id
        for row_id in verified_ids
        if f"`{row_id}`" in text and f"`{row_id}` above is a *separate, still-open*" in text
    ]

    assert stale_mentions == []
