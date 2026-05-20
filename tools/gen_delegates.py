#!/usr/bin/env python3
"""Auto-generate the CinemaPipeline forwarder + delegate section.

V1.1 #2 of REFACTOR_HANDOFF.md. Replaces the hand-written block of
RunState property forwarders + ShotController / ReviewController /
CheckpointStore delegate methods with an auto-generated section
between marker comments in ``cinema_pipeline.py``.

The script is idempotent: running it twice produces the same output.
The marker block in ``cinema_pipeline.py`` is delimited by:

    # GENERATED BEGIN -- tools/gen_delegates.py
    ...
    # GENERATED END

Anything between those markers is rewritten on each run. Hand-edits
inside the block are lost. Hand-edits outside the block are preserved.

Usage
=====

    python tools/gen_delegates.py            # rewrite cinema_pipeline.py in place
    python tools/gen_delegates.py --check    # exit non-zero if regen would change the file
    python tools/gen_delegates.py --print    # print the generated section to stdout

The --check mode is useful as a pre-commit hook to ensure the file
stays in sync with the controllers + RunState.

What gets generated
===================

1. RunState forwarders -- one @property + setter pair per field in
   ``cinema/runstate.py``'s RunState dataclass. CinemaPipeline reads
   pipeline.shot_results / pipeline.scene_clips / etc. via these.

   Special case: completed_scene_indices on RunState is exposed as
   _completed_scene_indices on CinemaPipeline (legacy underscore name
   that the orchestrator + checkpoint code use).

2. ShotController delegates -- the 6 public methods + 2 cross-
   controller private helpers (_find_take, _mutate_shot) that
   ReviewController calls via host.

3. ReviewController delegates -- 3 public operator API methods
   (approve_shot_plan, approve_take, proceed_to_assembly) +
   8 gate-machinery / per-shot-query helpers that the orchestrator
   or ShotController call via host or via direct CinemaPipeline access.

4. CheckpointStore delegates -- 2 public methods + 3 internal lifecycle
   methods (_save_checkpoint, _restore_from_checkpoint, _clear_checkpoint).

The lists are HARD-CODED below (CONTROLLER_DELEGATES). Adding a new
controller method that other components call externally requires
editing this script. Methods that are purely internal to a controller
don't need delegates.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration -- which methods get delegated on CinemaPipeline.
# Adding a new externally-called controller method? Add it here.
# ---------------------------------------------------------------------------

CONTROLLER_DELEGATES = {
    "_shot_ctrl": [
        # Public operator API (called from web_server endpoints + tests)
        "generate_keyframe_take",
        "generate_motion_take",
        "regenerate_shot",
        "diagnose_clip",
        "apply_correction",
        "generate_scene_preview",
        # Cross-controller helpers (called by ReviewController via host)
        "_find_take",
        "_mutate_shot",
    ],
    "_review_ctrl": [
        # Public operator API
        "approve_shot_plan",
        "approve_take",
        "proceed_to_assembly",
        # Gate machinery (called from CinemaPipeline.generate() + get_state)
        "_project_gate_status",
        "_gate_satisfied",
        "_wait_for_gate",
        "_rebuild_review_clips",
        # Per-shot helpers (called by ShotController via host + orchestrator)
        "_all_shots",
        "_latest_take",
        "_resolve_take_path",
        "_candidate_take",
    ],
    "_checkpoint": [
        # Public API
        "has_checkpoint",
        "resume_info",
        # Lifecycle (called from CinemaPipeline.generate())
        "_save_checkpoint",
        "_restore_from_checkpoint",
        "_clear_checkpoint",
    ],
}

# Special name mapping: CinemaPipeline-exposed name -> RunState field name.
# Used for the one case where the orchestrator uses a different name than
# the RunState field (legacy underscore convention).
RUNSTATE_NAME_OVERRIDES = {
    "completed_scene_indices": "_completed_scene_indices",  # RunState -> CinemaPipeline
}


# ---------------------------------------------------------------------------
# AST inspection helpers.
# ---------------------------------------------------------------------------


def get_runstate_fields(runstate_path: Path) -> list[tuple[str, str]]:
    """Return [(field_name, type_str), ...] from RunState dataclass."""
    tree = ast.parse(runstate_path.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RunState")
    fields = []
    for node in cls.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            type_str = ast.unparse(node.annotation)
            fields.append((node.target.id, type_str))
    return fields


def verify_controller_methods_exist(controllers: dict[str, Path]) -> None:
    """Sanity check: every method in CONTROLLER_DELEGATES exists on its controller."""
    errors = []
    attr_to_class = {
        "_shot_ctrl": "ShotController",
        "_review_ctrl": "ReviewController",
        "_checkpoint": "CheckpointStore",
    }
    for attr, methods in CONTROLLER_DELEGATES.items():
        cls_name = attr_to_class[attr]
        path = controllers[attr]
        tree = ast.parse(path.read_text())
        cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name), None)
        if cls is None:
            errors.append(f"{cls_name} not found in {path}")
            continue
        defined = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
        for m in methods:
            if m not in defined:
                errors.append(f"{cls_name}.{m} missing (configured in CONTROLLER_DELEGATES)")
    if errors:
        print("ERROR: gen_delegates configuration is out of sync with controllers:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(2)


# ---------------------------------------------------------------------------
# Code emitters.
# ---------------------------------------------------------------------------


def emit_runstate_forwarder(field_name: str, type_str: str) -> str:
    """Emit @property + setter pair for a RunState field.

    Handles the legacy-underscore override (completed_scene_indices on
    RunState -> _completed_scene_indices on CinemaPipeline).
    """
    cinema_name = RUNSTATE_NAME_OVERRIDES.get(field_name, field_name)
    return (
        f"    @property\n"
        f"    def {cinema_name}(self) -> {type_str}:\n"
        f"        return self._runstate.{field_name}\n"
        f"    @{cinema_name}.setter\n"
        f"    def {cinema_name}(self, value: {type_str}) -> None:\n"
        f"        self._runstate.{field_name} = value\n"
    )


def emit_delegate(method_name: str, controller_attr: str) -> str:
    """Emit a delegate method forwarding *args/**kwargs to the controller."""
    return (
        f"    def {method_name}(self, *args, **kwargs):\n"
        f"        return self.{controller_attr}.{method_name}(*args, **kwargs)\n"
    )


def generate_section(runstate_fields: list[tuple[str, str]]) -> str:
    """Generate the full marker-delimited section as a string."""
    lines: list[str] = []
    lines.append("    # GENERATED BEGIN -- tools/gen_delegates.py")
    lines.append("    # DO NOT EDIT BY HAND. Run `python tools/gen_delegates.py` to regenerate.")
    lines.append("    # ------------------------------------------------------------------")
    lines.append("    # RunState forwarders (one @property + setter pair per field).")
    lines.append("    # Lets pipeline.shot_results / pipeline.scene_clips / etc. read +")
    lines.append("    # write through to the shared self._runstate instance.")
    lines.append("    # ------------------------------------------------------------------")
    lines.append("")

    for field_name, type_str in runstate_fields:
        lines.append(emit_runstate_forwarder(field_name, type_str))

    for controller_attr, methods in CONTROLLER_DELEGATES.items():
        lines.append("    # ------------------------------------------------------------------")
        lines.append(f"    # Delegates -> self.{controller_attr}")
        lines.append("    # ------------------------------------------------------------------")
        lines.append("")
        for m in methods:
            lines.append(emit_delegate(m, controller_attr))

    lines.append("    # GENERATED END")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Marker block rewrite in cinema_pipeline.py.
# ---------------------------------------------------------------------------

BEGIN_MARKER = "    # GENERATED BEGIN -- tools/gen_delegates.py"
END_MARKER = "    # GENERATED END"


def replace_marker_block(src: str, new_section: str) -> str:
    """Replace the marker-delimited region in cinema_pipeline.py with new_section.

    Raises RuntimeError if the markers aren't present or aren't paired.
    """
    begin = src.find(BEGIN_MARKER)
    end = src.find(END_MARKER)
    if begin == -1 or end == -1:
        raise RuntimeError(
            f"Marker block not found. Expected {BEGIN_MARKER!r} and {END_MARKER!r} "
            f"both present in cinema_pipeline.py."
        )
    if end < begin:
        raise RuntimeError("END marker appears before BEGIN marker.")
    # End-line-end so we replace the entire END marker line.
    end_lineend = src.find("\n", end)
    if end_lineend == -1:
        end_lineend = len(src)
    return src[:begin] + new_section.rstrip("\n") + src[end_lineend:]


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true",
        help="Exit non-zero if regeneration would change cinema_pipeline.py.",
    )
    parser.add_argument(
        "--print", action="store_true",
        help="Print the generated section to stdout instead of writing.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    runstate_path = repo_root / "cinema" / "runstate.py"
    pipeline_path = repo_root / "cinema_pipeline.py"
    controllers = {
        "_shot_ctrl": repo_root / "cinema" / "shots" / "controller.py",
        "_review_ctrl": repo_root / "cinema" / "review" / "controller.py",
        "_checkpoint": repo_root / "cinema" / "checkpoint.py",
    }

    # Sanity: every configured method exists on its controller.
    verify_controller_methods_exist(controllers)

    fields = get_runstate_fields(runstate_path)
    new_section = generate_section(fields)

    if args.print:
        sys.stdout.write(new_section)
        return 0

    current = pipeline_path.read_text()
    updated = replace_marker_block(current, new_section)

    if args.check:
        if current != updated:
            print(
                "ERROR: cinema_pipeline.py is OUT OF SYNC with tools/gen_delegates.py.\n"
                "       Run `python tools/gen_delegates.py` to regenerate.",
                file=sys.stderr,
            )
            return 1
        print("OK: cinema_pipeline.py is in sync.")
        return 0

    if current == updated:
        print("No changes; cinema_pipeline.py is already in sync.")
        return 0

    pipeline_path.write_text(updated)
    print(f"Regenerated marker block in {pipeline_path.relative_to(repo_root)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
