#!/usr/bin/env python3
"""Does the character LoRA hold identity where reference conditioning fails?

WHY
---
The prompt battery (ADR-091) found that reference conditioning holds identity
only when the target pose matches the reference pose: 0.791 on a frontal
prompt, 0.56-0.65 on every realistic shot, with BOTH the one-reference and
multi-reference arms failing the 0.70 gate on all four non-portrait cases.

The character LoRA was filed as the loser at 0.676 against one reference's
0.791 -- but that comparison happened in the single condition where reference
conditioning is strongest. A LoRA carries identity in weights rather than in a
reference image, so it has no frontal-only limitation by construction, and it
has never been measured off-angle. If it holds near 0.65-0.70 where reference
conditioning sits at 0.56, the correct rule becomes "one reference for frontal
close-ups, LoRA elsewhere".

DESIGN
------
Three arms per case, all at 1024x1024, seed 0, four steps -- identical
resolution, because the LoRA graph is fixed at 1:1 and comparing across aspect
ratios would confound the face-crop size the scorer sees.

  1ref          reference conditioning, the ADR-089 default, plain prompt
  lora          the trained adapter, trigger-token prompt
  lora_control  the SAME trigger-token prompt with the adapter REMOVED

The control arm is what makes the LoRA number readable. The trigger token
changes the text conditioning on its own, so `lora` versus `1ref` alone cannot
separate the adapter's contribution from the prompt's. `lora - lora_control`
isolates the adapter; `lora` versus `1ref` answers the practical question.

The first case re-runs the lab's own prompt at 1:1 as a calibration row. Its
1ref score will NOT equal the battery's 0.791 -- that was 16:9 -- so read it as
the within-run anchor, not as a cross-run comparison.

THIS IS A PROBE, NOT BENCHMARK EVIDENCE
---------------------------------------
`run_flux2_lora_image_job` deliberately refuses any prompt but the fixed
benchmark, because its output IS the published control/adapter evidence. This
script builds the same hash-bound graph through the same pinned builder but
submits arbitrary scene prompts, so it produces measurements and NOT evidence.
Nothing here writes to the LoRA job state or the published evidence chain.

    env -u GIT_INDEX_FILE .venv/bin/python scripts/adr089_lora_arm_probe.py --job-id <id>
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import web_server  # noqa: E402,F401  (TF before PyArrow; see ADR on the Abseil collision)

import argparse  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402

import requests  # noqa: E402

from cinema.shots.strategy import (  # noqa: E402
    CharIdentitySpec,
    allocate_flux2_references,
)
from config.settings import settings  # noqa: E402
from cost_tracker import CostTracker  # noqa: E402
from domain.character_manager import (  # noqa: E402
    _resolve_stored_media_path,
    get_character,
)
from identity.lora_inference import _lora_modules  # noqa: E402
from identity.protocols import BENCHMARK_PROMPT  # noqa: E402
from identity.types import get_threshold_for_shot  # noqa: E402
from paid_provider import (  # noqa: E402
    paid_attempt_id,
    request_fingerprint,
    run_durable_comfy_job,
)
from performance.comfyui_endpoint import resolve_performance_comfyui  # noqa: E402
from performance.flux2_klein import run_flux2_klein_image_job  # noqa: E402
from comfyui_client import ComfyUIClient  # noqa: E402


DEFAULT_PROJECT = "42c74e230519"
DEFAULT_CHARACTER = "hkkperson"
LORA_DEPLOY_ROOT = Path("deploy/windows-flux2-lora")
TRIGGER = "hkkperson"


@dataclass(frozen=True)
class Case:
    key: str
    plain: str      # for the reference arm
    trigger: str    # same shot, carrying the trigger token exactly once
    shot_type: str  # the gate follows the shot; see ADR-091's correction
    why: str


def _t(text: str) -> str:
    """Assert the trigger token appears exactly once, as the builder demands."""
    if text.split().count(TRIGGER) != 1:
        raise ValueError(f"trigger token must appear exactly once: {text!r}")
    return text


CASES = (
    Case(
        "anchor",
        BENCHMARK_PROMPT,
        _t(BENCHMARK_PROMPT.replace("portrait of the same person",
                                    "portrait of hkkperson person")),
        "portrait",
        "The lab's prompt, re-run at 1:1 as this run's internal calibration.",
    ),
    Case(
        "medium_action",
        "Medium shot of a man in a charcoal wool coat stepping out of a "
        "bookshop doorway onto a wet city street, late afternoon, overcast "
        "light, shallow depth of field.",
        _t("Medium shot of hkkperson person in a charcoal wool coat stepping "
           "out of a bookshop doorway onto a wet city street, late afternoon, "
           "overcast light, shallow depth of field."),
        "medium",
        "Reference conditioning scored 0.648/0.679 here. The ordinary case.",
    ),
    Case(
        "profile_angled",
        "Close profile shot of a man looking off to his left, side lighting "
        "from a window, dark background, sharp focus on the eye and jawline.",
        _t("Close profile shot of hkkperson person looking off to his left, "
           "side lighting from a window, dark background, sharp focus on the "
           "eye and jawline."),
        "portrait",
        "The largest reference-arm reversal (+0.040). Off-angle geometry the "
        "frontal canonical does not carry -- the LoRA's best chance.",
    ),
    Case(
        "low_light_motion",
        "Handheld night shot of a man turning quickly toward the camera under "
        "a streetlight, rain in the air, motion blur, high contrast.",
        _t("Handheld night shot of hkkperson person turning quickly toward the "
           "camera under a streetlight, rain in the air, motion blur, high "
           "contrast."),
        "action",
        "Compound stress. Both reference arms bottomed out near 0.56.",
    ),
)


def _fetch_adapter_metadata(job_id: str) -> dict:
    """Read the published adapter metadata straight from the gateway.

    Deliberately a raw read rather than LoraTrainingClient._evidence, which
    requires reconstructing the full training plan. This probe only needs the
    metadata the graph builder validates.
    """

    endpoint = resolve_performance_comfyui(settings)
    response = requests.get(
        f"{endpoint.server_url}/api/identity-lora/jobs/{job_id}/evidence",
        headers={"Authorization": f"Bearer {endpoint.api_key}"},
        timeout=(5.0, 60.0),
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("state") != "succeeded":
        raise SystemExit(f"job {job_id} is not succeeded: {payload.get('state')}")
    metadata = payload.get("adapter_metadata")
    if not isinstance(metadata, dict):
        raise SystemExit(f"job {job_id} carries no adapter metadata")
    return metadata


def _score(
    image: Path, reference: Path, character_id: str, shot_type: str
) -> tuple[float | None, str, float]:
    """Score against THIS shot type's gate, not a fixed 0.70 (ADR-091)."""

    from identity import validator as validator_module

    gate = get_threshold_for_shot(shot_type)
    if not validator_module.DEEPFACE_AVAILABLE:
        return None, "unavailable", gate
    validator = validator_module.IdentityValidator(vision_fallback=None)
    result = validator.validate_image(
        str(image), str(reference), character_id=character_id,
        shot_type=shot_type, threshold=gate,
    )
    if result.skipped or result.overall_score is None:
        return None, "unknown", gate
    return float(result.overall_score), "passed" if result.passed else "failed", gate


def _run_lora_arm(
    *, metadata: dict, prompt: str, with_adapter: bool, out: Path,
    tracker, request_id: str,
) -> None:
    """Build and submit the pinned LoRA graph with an arbitrary scene prompt."""

    contract, inference = _lora_modules(LORA_DEPLOY_ROOT)
    builder = (
        inference.build_inference_workflow if with_adapter
        else inference.build_control_workflow
    )
    workflow = builder(metadata=metadata, prompt=prompt)

    endpoint = resolve_performance_comfyui(settings)
    client = ComfyUIClient(
        endpoint.server_url, auth_token=endpoint.api_key,
        connect_timeout=5.0, read_timeout=30.0,
    )
    fingerprint = request_fingerprint(
        "adr089-lora-probe", "adapter" if with_adapter else "control",
        prompt, request_id,
    )
    history = run_durable_comfy_job(
        client=client,
        workflow=workflow,
        attempt_id=paid_attempt_id("adr089-lora-probe", "", "", fingerprint),
        engine="FLUX2_KLEIN_LORA_LOCAL",
        provider="local_gpu",
        operation="identity_inference",
        estimated_cost_usd=0.0,
        request_fingerprint_value=fingerprint,
        cost_tracker=tracker,
        poll_timeout_s=600.0,
    )
    # The history is keyed by prompt_id at the top level, then outputs["14"]
    # (the SaveImage node). Mirrors identity.lora_inference._first_lora_output.
    if not isinstance(history, dict) or len(history) != 1:
        raise RuntimeError(f"unexpected history shape: {list(history)[:4]}")
    record = history[next(iter(history))]
    images = (record.get("outputs") or {}).get("14", {}).get("images") or []
    if len(images) != 1:
        raise RuntimeError(f"expected exactly one image, got {len(images)}")
    first = images[0]
    # download_image validates and atomically publishes to `destination`; it
    # does not return bytes.
    client.download_image(
        first["filename"],
        first.get("subfolder", ""),
        first.get("type", "output"),
        str(out),
        expected_dimensions=(1024, 1024),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True, help="succeeded LoRA training job id")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--character", default=DEFAULT_CHARACTER)
    parser.add_argument("--out", default="logs/adr089-lora-arm")
    parser.add_argument("--only", default="")
    args = parser.parse_args()

    project = json.loads(
        (Path("domain/projects") / args.project / "project.json").read_text("utf-8")
    )
    character = get_character(project, args.character)
    canonical = _resolve_stored_media_path(project, character.get("canonical_reference", ""))
    angles = tuple(
        _resolve_stored_media_path(project, v)
        for v in (character.get("multi_angle_refs") or [])
    )
    spec = CharIdentitySpec(
        char_id=args.character, reference=canonical,
        identity_anchor="", multi_angle_refs=angles,
    )

    metadata = _fetch_adapter_metadata(args.job_id)
    print(f"adapter: {metadata.get('adapter', {}).get('filename', '?')}")
    print(f"subject: {args.character}   canonical: {Path(canonical).name}")
    print("all arms at 1024x1024 (the LoRA graph's fixed size), seed 0, 4 steps\n")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    selected = {k.strip() for k in args.only.split(",") if k.strip()}
    cases = [c for c in CASES if not selected or c.key in selected]

    tracker = CostTracker(db_path=str(out_dir / "probe.db"), budget_usd=1.0)
    rows: list[dict] = []
    try:
        for case in cases:
            for arm in ("1ref", "lora", "lora_control"):
                target = out_dir / f"{case.key}__{arm}.png"
                print(f"→ {case.key} / {arm}")
                started = time.monotonic()
                try:
                    if arm == "1ref":
                        allocation = allocate_flux2_references(primary=spec, secondaries=())
                        run_flux2_klein_image_job(
                            prompt=case.plain,
                            reference_image_paths=list(allocation.reference_paths),
                            output_path=str(target), seed=0, aspect_ratio="1:1",
                            cost_tracker=tracker,
                            request_id=f"adr089-lora-probe-{case.key}-{arm}",
                            filename_prefix=f"adr089-lora-{case.key}-{arm}",
                            poll_timeout_s=600.0,
                        )
                    else:
                        _run_lora_arm(
                            metadata=metadata, prompt=case.trigger,
                            with_adapter=(arm == "lora"), out=target,
                            tracker=tracker,
                            request_id=f"adr089-lora-probe-{case.key}-{arm}",
                        )
                except Exception as exc:  # noqa: BLE001 - report, keep going
                    print(f"   FAILED: {type(exc).__name__}: {exc}")
                    rows.append({"case": case.key, "arm": arm, "score": None,
                                 "verdict": "render_failed",
                                 "error": f"{type(exc).__name__}: {exc}"})
                    continue
                elapsed = time.monotonic() - started
                score, verdict, gate = _score(
                    target, Path(canonical), args.character, case.shot_type
                )
                shown = "—" if score is None else f"{score:.3f}"
                print(
                    f"   {elapsed:5.1f}s  score={shown}  gate={gate:.2f}"
                    f" ({case.shot_type})  {verdict}"
                )
                rows.append({"case": case.key, "arm": arm,
                             "shot_type": case.shot_type, "gate": gate,
                             "seconds": round(elapsed, 1), "score": score,
                             "verdict": verdict, "output": target.name})
    finally:
        tracker.close()

    (out_dir / "probe.json").write_text(
        json.dumps({"job_id": args.job_id,
                    "cases": {c.key: {"plain": c.plain, "trigger": c.trigger,
                                      "shot_type": c.shot_type,
                                      "gate": get_threshold_for_shot(c.shot_type),
                                      "why": c.why} for c in cases},
                    "results": rows}, indent=2) + "\n", "utf-8")

    print(f"\n{'case':<20} {'1ref':>7} {'lora':>7} {'control':>8}   reading")
    print("-" * 62)
    for case in cases:
        by = {r["arm"]: r.get("score") for r in rows if r["case"] == case.key}
        one, lora, ctrl = by.get("1ref"), by.get("lora"), by.get("lora_control")
        fmt = lambda v: "—" if v is None else f"{v:.3f}"  # noqa: E731
        if lora is None or ctrl is None or one is None:
            reading = "incomplete"
        elif lora - ctrl < 0.02:
            reading = "adapter inert here"
        elif lora > one:
            reading = "LORA WINS"
        else:
            reading = "1ref still ahead"
        print(f"{case.key:<20} {fmt(one):>7} {fmt(lora):>7} {fmt(ctrl):>8}   {reading}")

    print(
        "\nRead `lora` against `control`, not against `1ref` alone: the trigger "
        "token changes text conditioning by itself, so a LoRA that beats 1ref "
        "while matching its own control has proven nothing about the adapter."
    )
    print("Probe only — one subject, one seed, one render per cell.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
