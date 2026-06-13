#!/usr/bin/env python3
"""Archive stale top-level docs/HANDOFF-*.md into docs/archive/<UTC-date>/.

AUDIT-2026-06-13.md H5 remediation tool (handoff doc sprawl). SAFE BY DEFAULT:

  * DRY-RUN unless you pass --yes. Run once to preview, then again with --yes.
  * You MUST preserve the ACTIVE handoff set — the MEMORY "current state"
    READ-FIRST handoff per seat, the roadmap handoff, and anything an active
    instruction doc links to (e.g. DECISIONS.md). Pass each as --keep <basename>
    (repeatable). Moving EVERY handoff breaks those READ-FIRST links, so the
    script prints a loud warning (and, with --strict, refuses) when --keep is
    empty. Filenames do NOT sort by recency, so a heuristic "latest" is unsafe;
    the keep-set is a human/MEMORY judgment passed in explicitly.
  * Uses `git mv` inside a git repo (history preserved); else shutil.move.
  * Writes/extends INDEX.md in the target archive dir.

Example (reproduces the 2026-06-14 curated archive — 7 kept):
  python scripts/archive_handoffs.py --yes \
    --keep HANDOFF-coordinator-2026-06-14.md \
    --keep HANDOFF-roadmap-2026-05-24.md \
    --keep HANDOFF-director-2026-06-13-PM7-pairA-nan-gate-landed.md \
    --keep HANDOFF-operator-2026-06-13-PM6-pairA-rife-fix-verified-2-novel-audio-siblings-reported.md \
    --keep HANDOFF-director2-2026-06-13-PM-W1-cheapfixes-verified-cascade-landed-designcalls-dispositioned.md \
    --keep HANDOFF-operator2-2026-06-13-pairB-s3-audio-sibling-LANDED-verified-2siblings-pinned.md \
    --keep HANDOFF-director-transplant-2026-06-13-overcook-structural-prod-hybrid-driver-built.md
"""
import argparse
import datetime
import glob
import os
import shutil
import subprocess


def _git_mv(repo_root, rel_src, rel_dst):
    """git mv (stages the rename, preserves history). Returns True on success."""
    try:
        subprocess.run(["git", "mv", rel_src, rel_dst], cwd=repo_root, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description="Archive stale docs/HANDOFF-*.md (AUDIT H5).")
    ap.add_argument("--keep", action="append", default=[], metavar="BASENAME",
                    help="Handoff basename to KEEP at top-level (repeatable). The active READ-FIRST set.")
    ap.add_argument("--yes", action="store_true", help="Actually move (default is a dry-run preview).")
    ap.add_argument("--strict", action="store_true", help="Refuse to run if --keep is empty.")
    args = ap.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(repo_root, "docs")
    keep = set(args.keep)

    handoffs = sorted(glob.glob(os.path.join(docs_dir, "HANDOFF-*.md")))
    if not handoffs:
        print("No top-level docs/HANDOFF-*.md found — nothing to archive.")
        return

    to_move = [p for p in handoffs if os.path.basename(p) not in keep]
    kept = [p for p in handoffs if os.path.basename(p) in keep]

    if not keep:
        msg = ("WARNING: no --keep given — this would archive ALL %d handoffs, breaking the "
               "MEMORY/CLAUDE/DECISIONS READ-FIRST links. Pass --keep <basename> for the active set." % len(handoffs))
        if args.strict:
            raise SystemExit("REFUSING (--strict): " + msg)
        print(msg)

    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    target = os.path.join(docs_dir, "archive", date_str)
    mode = "MOVE" if args.yes else "DRY-RUN (pass --yes to apply)"
    print("== archive_handoffs [%s] -> docs/archive/%s/ ==" % (mode, date_str))
    print("  keep (%d): %s" % (len(kept), ", ".join(sorted(os.path.basename(p) for p in kept)) or "(none)"))
    print("  move (%d):" % len(to_move))

    if not args.yes:
        for p in to_move:
            print("    would move %s" % os.path.basename(p))
        print("== dry-run complete; re-run with --yes to apply ==")
        return

    os.makedirs(target, exist_ok=True)
    moved = 0
    for src in to_move:
        b = os.path.basename(src)
        rel_src = os.path.relpath(src, repo_root)
        rel_dst = os.path.relpath(os.path.join(target, b), repo_root)
        if not _git_mv(repo_root, rel_src, rel_dst):
            shutil.move(src, os.path.join(target, b))
        print("    moved %s" % b)
        moved += 1

    index = os.path.join(target, "INDEX.md")
    with open(index, "w") as fh:
        fh.write("# Handoff archive — %s\n\n" % date_str)
        fh.write("Archived %d handoffs (AUDIT-2026-06-13.md H5). Kept active at docs/: %s.\n\n" %
                 (moved, ", ".join(sorted(os.path.basename(p) for p in kept)) or "(none)"))
        for src in sorted(to_move):
            b = os.path.basename(src)
            fh.write("- [%s](%s)\n" % (b, b))
    print("== archived %d handoffs; wrote %s ==" % (moved, os.path.relpath(index, repo_root)))


if __name__ == "__main__":
    main()
