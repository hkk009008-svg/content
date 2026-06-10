# P1-1 Slice 1 — Identity-Strategy Router + Multi-Character Kontext Keyframes

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Condition keyframe generation on EVERY in-frame character with a registered
reference (today: first character only), on the live FAL Kontext path, with
generation-promise metadata the validator and scorecard can hold generation
accountable to.

**Architecture:** A pure decision function in `cinema/shots/controller.py` resolves an
`IdentityStrategy` (new dataclass module `cinema/shots/strategy.py`) per keyframe take
and records it in take metadata before generation. `enhance_shot_prompt` gains a
`secondary_chars` list in `continuity_config`. `_fal_flux_fallback` gains a
multi-character branch behind a structural early-return (single-char path byte-untouched);
a slot allocator partitions the 6-ref Kontext budget and the prompt addresses each
character via its own `@ImageN` block. Post-generation validation loops over the
conditioned characters (mirroring the motion-take `identity_per_char` convention) and
the capability scorecard surfaces an `identity_multi` sub-field. Spike S1 gates the
Kontext multi-char branch (Tasks 7–8); everything else lands regardless of S1's verdict.

**Tech Stack:** Python 3.13, pytest (`env -u GIT_INDEX_FILE .venv/bin/python -m pytest`),
`fal_client` 1.0.0 (generic transport — no endpoint schema), GhostFaceNet via the shared
`IdentityValidator` singleton.

**Spec:** docs/SPEC-P1-1-multichar-generation-identity-2026-06-10.md (REVIEWED). Read
§1–§3 before starting. Citations below were verified at HEAD `fa3bf8c`, 2026-06-10.
**Lane-V disposition folded 2026-06-11** (operator report 2026-06-10T16:25:00Z,
commit `7878d62`): V-5 `multi_angle_refs` carried through `CharIdentitySpec`
(Tasks 4/5/6), V-2 derived `mechanism_actually_used` (Task 6), V-3/V-4 S1
criteria (Task 2), V-6 provenance-test step (Task 8), M-3/M-4/M-5 corrections.

**Session discipline (repo-specific, read first):**
- The operator seat may be LIVE in the same worktree. Before every commit:
  `git diff --cached --name-only`, then commit with an explicit **pathspec**
  (`git commit -m "..." -- <your files>`; `-m` BEFORE `--`). Never bare `git commit`.
- Run pytest as `env -u GIT_INDEX_FILE .venv/bin/python -m pytest …` (per-seat
  GIT_INDEX_FILE breaks temp-repo tests otherwise).
- If `git status` shows changes you didn't make: STOP, run `git log --oneline -3`
  and check `coordination/presence/` before attributing or proceeding.
- Suite baseline: **2021 passed / 0 failed / 2 skipped** (operator full run at
  `5d7353e`; the original "2020" here predated the pin test added in `fa3bf8c` —
  Lane-V M-3); smoke `.venv/bin/python scripts/ci_smoke.py` → OK. Both must hold
  after every task.

---

## Chunk 1: Regression armor + the S1 spike

### Task 1: Golden snapshot of today's single-char Kontext prompt

The multi-char work must not move a byte of the single-char prompt. Capture today's
exact prompt FIRST so every later task is checked against it.

**Files:**
- Create: `tests/unit/test_kontext_prompt_snapshot.py`
- Reference (do not modify): `phase_c_assembly.py:439-546` (`_fal_flux_fallback`),
  `tests/unit/test_phase_c_assembly_provenance.py` (existing monkeypatch pattern —
  mirror its fixture approach per R-BRIEF; if its pattern differs from the code below,
  the sibling file wins. The settings patch below already uses the sibling's
  `dataclasses.replace` pattern (Lane-V M-4). Remaining known divergence: the
  sibling injects a MagicMock via `monkeypatch.setitem(sys.modules, "fal_client",
  …)` while the code below monkeypatches the real `fal_client` module's
  attributes — both work; pick the sibling's if they conflict).

- [ ] **Step 1: Write the failing test**

```python
"""Golden snapshot of the single-character Kontext prompt.

P1-1 slice 1 adds a multi-character branch to _fal_flux_fallback behind an
early-return. This snapshot pins the single-char prompt so the branch cannot
drift it by a byte. Captured from phase_c_assembly.py:493-529 at fa3bf8c.
"""
import dataclasses
import os

import pytest

import phase_c_assembly


@pytest.fixture
def fal_capture(monkeypatch, tmp_path):
    """Intercept the FAL transport; record the kontext arguments."""
    captured = {}

    def fake_subscribe(endpoint, client_timeout=None, arguments=None):
        captured["endpoint"] = endpoint
        captured["arguments"] = arguments
        return {"images": [{"url": "http://fake/img.jpg"}]}

    def fake_upload(path):
        return f"url://{os.path.basename(path)}"

    import fal_client
    monkeypatch.setattr(fal_client, "subscribe", fake_subscribe)
    monkeypatch.setattr(fal_client, "upload_file", fake_upload)
    monkeypatch.setattr(
        "urllib.request.urlretrieve", lambda url, fn: open(fn, "wb").close()
    )
    monkeypatch.setattr(
        phase_c_assembly, "settings",
        dataclasses.replace(phase_c_assembly.settings, fal_key="test-key"),
    )
    return captured


def test_single_char_kontext_prompt_snapshot(fal_capture, tmp_path):
    ref = tmp_path / "aria.jpg"
    ref.write_bytes(b"jpg")
    out = tmp_path / "out.jpg"

    result = phase_c_assembly._fal_flux_fallback(
        "A quiet rooftop at dusk",
        str(out),
        character_image=str(ref),
        identity_anchor="a woman with auburn hair and green eyes",
    )

    assert result is not None and result.api_name == "FLUX_KONTEXT"
    assert fal_capture["endpoint"] == "fal-ai/flux-pro/kontext/max/multi"
    # GOLDEN: byte-exact reproduction of phase_c_assembly.py:493-529 for this input.
    expected = (
        "PRESERVE IDENTITY: The person from @Image1 is a woman with auburn hair "
        "and green eyes. Keep this EXACT face, hair, glasses, eye color, skin tone "
        "unchanged. "
        "CHANGE BACKGROUND: A quiet rooftop at dusk. "
        "SET POSE: facing the camera. "
        "SET CAMERA: Medium shot, 85mm lens. "
        "CONSTRAINTS: Do NOT alter facial features, hairstyle, glasses, or skin. "
        "Do NOT generate a different person. "
        "The face in the output MUST match @Image1 exactly. "
        "QUALITY: Photorealistic, visible skin pores and subsurface scattering, "
        "shallow depth of field with circular bokeh, natural film grain ISO 400, "
        "volumetric atmospheric lighting, micro-detail in fabric texture, "
        "no AI artifacts, no smooth plastic skin, no over-saturated colors."
    )
    assert fal_capture["arguments"]["prompt"] == expected
    assert fal_capture["arguments"]["image_urls"] == ["url://aria.jpg"]
```

Define `expected` as a MODULE-LEVEL constant (e.g. `GOLDEN_SINGLE_CHAR_PROMPT`) —
Task 8's byte-equivalence test imports it from this module instead of duplicating
the string.

- [ ] **Step 2: Run it — it must PASS already (snapshot of current behavior)**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_kontext_prompt_snapshot.py -v`
Expected: PASS. **If it fails, the expected string was transcribed wrong — fix the
test against the live output (print `fal_capture["arguments"]["prompt"]`), never the
production code.** This test is the regression armor, so its first green must come
from zero production changes.

- [ ] **Step 3: Commit (pathspec)**

```bash
git add tests/unit/test_kontext_prompt_snapshot.py
git diff --cached --name-only   # must list ONLY the new test file
git commit -m "test(p1-1): golden snapshot of the single-char Kontext prompt" -- tests/unit/test_kontext_prompt_snapshot.py
```

### Task 2: S1 spike script (dry-run by default; live run is user-gated)

**Files:**
- Create: `scripts/_test_kontext_multi_char.py`
- Reference: spec §6 (S1 go/no-go), `identity/__init__.py:62`
  (`get_shared_validator`), `cinema/fal_limits.py:39` (`FAL_TIMEOUT_IMAGE_S` — any
  new FAL call site MUST import and pass this constant; a guard test rejects inline
  timeout literals).

- [ ] **Step 1: Write the script**

```python
"""S1 spike — does fal-ai/flux-pro/kontext/max/multi separate two identities?

Five calls sharing one scene (spec §6; criteria revised per Lane-V V-3/V-4):
  1. baseline : primary face only, today's single-char prompt shape
  2. control  : NO secondary ref — both characters text-described (the floor)
  3-5. multi_a/b/c : both faces in image_urls, @Image1/@Image2 PRESERVE blocks
       (N=3 — this tier is unseeded; N=1-2 can NO-GO on output variance alone)

Scores every output against both refs with the shared GhostFaceNet validator and
prints the verdict. Per-arm GO:
  GO     : secondary >= control_secondary + 0.10
           AND secondary >= 0.45 (S1_SECONDARY_FLOOR — the bottom of spec
           §3(a)'s projected 0.45-0.60 band; the per-shot-type lenient
           threshold is printed as ADVISORY context, never gated on — V-3)
           AND |primary - baseline_primary| <= 0.05
           AND no blend signal (both faces of the arm in the 0.40-0.50 band;
           blend deliberately OVERRIDES the floor in the [0.45, 0.50) overlap —
           both-faces-in-band means the lift is an averaging artifact)
Overall S1 verdict = MAJORITY of the three multi arms (>= 2/3 GO).

DRY-RUN by default (prints the five payloads, no spend). --live costs ~5 x $0.04
~= $0.20 (flat-rate assumption unverified; the control call rides
fal-ai/flux-pro/v1.1-ultra whose price may differ — read the real per-call
prices off the FAL dashboard while the calls are visible there, spec §4).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cinema.fal_limits import FAL_TIMEOUT_IMAGE_S
from identity.types import get_threshold_for_shot

# V-3: absolute go-floor — bottom of spec §3(a)'s projected band (numerically the
# wide-shot lenient threshold, identity/types.py:98). The --shot-type lenient
# threshold sits INSIDE the projected band and would false-veto a real lift.
S1_SECONDARY_FLOOR = 0.45


def build_prompts(scene: str, anchor_a: str, anchor_b: str) -> dict:
    quality = (
        "QUALITY: Photorealistic, visible skin pores and subsurface scattering, "
        "shallow depth of field with circular bokeh, natural film grain ISO 400."
    )
    single = (
        f"PRESERVE IDENTITY: The person from @Image1 is {anchor_a}. "
        f"Keep this EXACT face, hair, eye color, skin tone unchanged. "
        f"CHANGE BACKGROUND: {scene}. SET POSE: both people talking, facing each "
        f"other. SET CAMERA: Medium two-shot, 50mm lens. "
        f"CONSTRAINTS: The face in the output MUST match @Image1 exactly. {quality}"
    )
    control = (
        f"Two people in {scene}: on the left, {anchor_a}; on the right, {anchor_b}. "
        f"Medium two-shot, 50mm lens, both talking, facing each other. {quality}"
    )
    multi = (
        f"PRESERVE IDENTITY: The person from @Image1 is {anchor_a}. Keep this EXACT "
        f"face, hair, eye color, skin tone unchanged. "
        f"PRESERVE IDENTITY: The person from @Image2 is {anchor_b}. Keep this EXACT "
        f"face, hair, eye color, skin tone unchanged. "
        f"CHANGE BACKGROUND: {scene}. SET POSE: both people talking, facing each "
        f"other; the person from @Image1 on the left, the person from @Image2 on "
        f"the right. SET CAMERA: Medium two-shot, 50mm lens. "
        f"CONSTRAINTS: Do NOT blend or average the two faces. Each output face MUST "
        f"match its own reference image exactly. {quality}"
    )
    return {"baseline": single, "control": control, "multi": multi}


def score(img_path: str, ref_path: str, char_id: str) -> float:
    from identity import get_shared_validator
    r = get_shared_validator().validate_image(
        img_path, ref_path, character_id=char_id, threshold=0.0
    )
    return r.overall_score


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--char-a", required=True, help="primary reference image path")
    ap.add_argument("--char-b", required=True, help="secondary reference image path")
    ap.add_argument("--anchor-a", default="the woman in the first reference photo")
    ap.add_argument("--anchor-b", default="the man in the second reference photo")
    ap.add_argument("--scene", default="a quiet rooftop cafe at dusk")
    ap.add_argument("--shot-type", default="medium",
                    choices=["portrait", "medium", "wide", "action"])
    ap.add_argument("--outdir", default="logs/s1_kontext_multichar")
    ap.add_argument("--live", action="store_true",
                    help="actually call FAL (~5 x $0.04 ~= $0.20). Default: dry-run.")
    args = ap.parse_args()

    prompts = build_prompts(args.scene, args.anchor_a, args.anchor_b)
    calls = [
        ("baseline", prompts["baseline"], [args.char_a]),
        ("control", prompts["control"], []),
        ("multi_a", prompts["multi"], [args.char_a, args.char_b]),
        ("multi_b", prompts["multi"], [args.char_a, args.char_b]),
        ("multi_c", prompts["multi"], [args.char_a, args.char_b]),
    ]

    if not args.live:
        for name, prompt, refs in calls:
            print(f"--- {name} (refs: {len(refs)}) ---\n{prompt}\n")
        print("DRY RUN — re-run with --live to spend (~$0.20).")
        return 0

    import fal_client
    os.makedirs(args.outdir, exist_ok=True)
    results = {}
    for name, prompt, refs in calls:
        arguments = {
            "prompt": prompt,
            "guidance_scale": 3.5,
            "aspect_ratio": "16:9",
            "output_format": "jpeg",
            "num_images": 1,
        }
        if refs:
            arguments["image_urls"] = [fal_client.upload_file(r) for r in refs]
            endpoint = "fal-ai/flux-pro/kontext/max/multi"
        else:
            endpoint = "fal-ai/flux-pro/v1.1-ultra"
            arguments.pop("guidance_scale")
        out = os.path.join(args.outdir, f"{name}.jpg")
        res = fal_client.subscribe(endpoint, client_timeout=FAL_TIMEOUT_IMAGE_S,
                                   arguments=arguments)
        import urllib.request
        urllib.request.urlretrieve(res["images"][0]["url"], out)
        results[name] = {
            "path": out,
            "score_a": score(out, args.char_a, "spike_char_a"),
            "score_b": score(out, args.char_b, "spike_char_b"),
        }
        print(f"{name}: a={results[name]['score_a']:.3f} "
              f"b={results[name]['score_b']:.3f}  {out}")

    lenient = get_threshold_for_shot(args.shot_type, mode="lenient")
    base_a = results["baseline"]["score_a"]
    ctrl_b = results["control"]["score_b"]
    verdicts = []
    for name in ("multi_a", "multi_b", "multi_c"):
        a, b = results[name]["score_a"], results[name]["score_b"]
        blend = 0.40 <= a <= 0.50 and 0.40 <= b <= 0.50
        go = (b >= ctrl_b + 0.10) and (b >= S1_SECONDARY_FLOOR) \
            and (abs(a - base_a) <= 0.05) and not blend
        verdicts.append(go)
        print(f"{name}: {'GO' if go else 'NO-GO'}"
              f" (b vs control+0.10: {b:.3f} vs {ctrl_b + 0.10:.3f};"
              f" floor={S1_SECONDARY_FLOOR};"
              f" advisory lenient[{args.shot_type}]={lenient} — not gated;"
              f" |a-base|={abs(a - base_a):.3f}; blend={blend})")
    print(json.dumps(results, indent=1))
    spread = [round(results[n]["score_b"], 3)
              for n in ("multi_a", "multi_b", "multi_c")]
    print("S1 VERDICT:", "GO" if sum(verdicts) >= 2 else "NO-GO",
          f"(majority of 3 arms; secondary spread {spread} — V-4: N=3 has power"
          " for separation-vs-blend, not fine threshold effects)",
          "— record in spec §6 + ARCHITECTURE-adjacent ADR per spec AC5")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Dry-run it (no spend)**

Run: `.venv/bin/python scripts/_test_kontext_multi_char.py --char-a logs/s1_a.jpg --char-b logs/s1_b.jpg`
(any two existing face image paths work for the dry-run; it only prints prompts)
Expected: five prompt payloads printed (multi_a/b/c carry the same prompt string —
N=3 runs of one design); exits 0; "DRY RUN" line.

- [ ] **Step 3: Commit the script (pathspec)**

```bash
git add scripts/_test_kontext_multi_char.py
git commit -m "feat(p1-1): S1 spike script — Kontext multi-identity go/no-go (dry-run default)" -- scripts/_test_kontext_multi_char.py
```

- [ ] **Step 4: LIVE run — STOP: user-gated spend (~$0.20)**

Confirm the user has approved S1 (spec §10 Q1 / the Session-4 go). Pick two refs of
DIFFERENT people: char A = Aria's canonical from project `cfd3f0967eb3`; char B = any
other photoreal reference on disk. Run with `--live`, paste the verdict block into
spec §6 (S1 row) and note the real per-call price from the FAL dashboard in spec §4.
**If NO-GO: skip Tasks 7–8 entirely** (spec §6 no-go path); Tasks 3–6 and 9–12 land
regardless.

**DONE 2026-06-10:** ran live (user "s1 go ahead"); pair = Aria + 정연
(bf1a4e9e8a9a — the Mara-lineage canonicals are the SAME face as Aria, visually
confirmed; 정연 is the only distinct registered person on disk). Verdict +
per-face re-score (`scripts/_s1_rescore_crops.py`) + validity analysis +
disposition (Tasks 7–8 proceed) recorded in spec §6 "S1 RESULT". Dashboard
price read still pending (no CLI access).

## Chunk 2: Data flow + the router

### Task 3: `secondary_chars` in `continuity_config`

**Files:**
- Modify: `domain/continuity_engine.py:548-575` (`enhance_shot_prompt` config block)
- Test: `tests/unit/test_continuity_engine.py` (extend)

> Fixture reality check: at plan time `test_continuity_engine.py` tests only
> `TemporalConsistencyManager` — there is NO existing `ContinuityEngine` fixture to
> mirror. `ContinuityEngine.__init__` pulls in `get_project_dir` and the validator;
> build the fixture by `unittest.mock.patch`-ing those (or constructing with a stub
> project dict and monkeypatched `character_tracker`). The tests below only need
> `character_tracker.get_reference_for_pulid/get_multi_angle_refs` and
> `get_identity_anchor` to return canned values — patch at that level rather than
> standing up a full engine if construction fights back.

- [ ] **Step 1: Write the failing tests** (adapt fixture names to the file's existing style)

```python
def test_secondary_chars_populated_for_registered_second_char(engine_two_chars):
    """chars_in_frame[1:] with a registered reference appear in secondary_chars."""
    enhanced = engine_two_chars.enhance_shot_prompt(
        {"characters_in_frame": ["char_a", "char_b"], "prompt": "p"},
        {"id": "s1", "shots": []}, None, 0,
    )
    sec = enhanced["continuity_config"]["secondary_chars"]
    assert [c["char_id"] for c in sec] == ["char_b"]
    assert sec[0]["reference"]            # the registered ref path
    assert "identity_anchor" in sec[0] and "multi_angle_refs" in sec[0]


def test_secondary_chars_skips_unregistered(engine_two_chars_b_unregistered):
    enhanced = engine_two_chars_b_unregistered.enhance_shot_prompt(
        {"characters_in_frame": ["char_a", "char_b"], "prompt": "p"},
        {"id": "s1", "shots": []}, None, 0,
    )
    assert enhanced["continuity_config"]["secondary_chars"] == []


def test_secondary_chars_empty_for_single_char(engine_two_chars):
    enhanced = engine_two_chars.enhance_shot_prompt(
        {"characters_in_frame": ["char_a"], "prompt": "p"},
        {"id": "s1", "shots": []}, None, 0,
    )
    assert enhanced["continuity_config"]["secondary_chars"] == []
```

- [ ] **Step 2: Run — expect FAIL** (`KeyError: 'secondary_chars'`)

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_continuity_engine.py -q -k secondary`

- [ ] **Step 3: Implement**

In the `continuity_config` literal (domain/continuity_engine.py:548-563) add
`"secondary_chars": [],` after `"approved_anchor_image"`. After the primary block
(:566-575) add:

```python
        # P1-1: per-character identity assets for chars beyond the primary.
        # Same existence guard as validation (validate_shot skips unregistered
        # chars at :606-610) — generation mirrors the skip, never fails on it.
        for cid in chars_in_frame[1:]:
            ref = self.character_tracker.get_reference_for_pulid(cid)
            if not ref:
                continue
            continuity_config["secondary_chars"].append({
                "char_id": cid,
                "reference": ref,
                "multi_angle_refs": self.character_tracker.get_multi_angle_refs(cid),
                "identity_anchor": get_identity_anchor(self.project, cid),
            })
```

- [ ] **Step 4: Run the file's full suite — all green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_continuity_engine.py -q`

- [ ] **Step 5: Commit (pathspec)**

```bash
git commit -m "feat(p1-1): continuity_config gains secondary_chars (registered-ref chars beyond primary)" -- domain/continuity_engine.py tests/unit/test_continuity_engine.py
```

### Task 4: `IdentityStrategy` dataclass module

**Files:**
- Create: `cinema/shots/strategy.py`
- Test: `tests/unit/test_identity_strategy_router.py` (new — this file grows through
  Tasks 4–6)

- [ ] **Step 1: Write the failing test**

```python
from cinema.shots.strategy import (
    IdentityStrategy, CharIdentitySpec,
    PRIMARY_ONLY, KONTEXT_MULTI_CHAR, MAX_TIER_PRIMARY_ONLY, NO_IDENTITY_ASSET,
)


def test_to_metadata_dict_is_json_safe_and_complete():
    s = IdentityStrategy(
        mechanism_tag=KONTEXT_MULTI_CHAR,
        primary_char_id="char_a",
        char_lora_path=None,
        char_lora_strength=None,
        conditioned_chars=[
            CharIdentitySpec(char_id="char_a", reference="/r/a.jpg",
                             identity_anchor="anchor a", fidelity="reference"),
            CharIdentitySpec(char_id="char_b", reference="/r/b.jpg",
                             identity_anchor="anchor b", fidelity="reference",
                             multi_angle_refs=("/r/b1.jpg",)),
        ],
        unconditioned_chars=["char_c"],
    )
    import json
    md = s.to_metadata_dict()
    json.dumps(md)  # must not raise
    assert md["mechanism_tag"] == "KONTEXT_MULTI_CHAR"
    assert [c["char_id"] for c in md["conditioned_chars"]] == ["char_a", "char_b"]
    assert md["unconditioned_chars"] == ["char_c"]
    # V-5 pin: multi_angle_refs must survive the to_dict chain — Task 7's
    # allocator reads it off these dicts via Task 6's kwarg; without it,
    # secondaries can never fill their allocated slots.
    assert md["conditioned_chars"][1]["multi_angle_refs"] == ["/r/b1.jpg"]
```

- [ ] **Step 2: Run — expect FAIL** (ModuleNotFoundError)

- [ ] **Step 3: Implement `cinema/shots/strategy.py`**

```python
"""Generation-promise types for per-shot identity conditioning (P1-1, spec §3d).

The router (cinema/shots/controller.py::_resolve_identity_strategy) emits one
IdentityStrategy per keyframe take BEFORE generation; the validator and the
capability scorecard hold generation accountable to it. Only tags whose
mechanism is implemented are ever emitted (slice 1: the four below; slice 2
adds MAX_TIER_MULTI_LORA / MAX_TIER_DUAL_PULID).
"""
from dataclasses import dataclass, field
from typing import List, Optional

PRIMARY_ONLY = "PRIMARY_ONLY"
KONTEXT_MULTI_CHAR = "KONTEXT_MULTI_CHAR"
MAX_TIER_PRIMARY_ONLY = "MAX_TIER_PRIMARY_ONLY"
NO_IDENTITY_ASSET = "NO_IDENTITY_ASSET"


@dataclass(frozen=True)
class CharIdentitySpec:
    char_id: str
    reference: str
    identity_anchor: str = ""
    fidelity: str = "reference"  # slice 1: reference | pulid; slice 2 adds lora
    # V-5: angle refs ride the spec through to_dict() -> generate_ai_broll ->
    # the slot allocator; a tuple (not list) keeps the frozen dataclass hashable.
    multi_angle_refs: tuple = ()

    def to_dict(self) -> dict:
        return {"char_id": self.char_id, "reference": self.reference,
                "identity_anchor": self.identity_anchor, "fidelity": self.fidelity,
                "multi_angle_refs": list(self.multi_angle_refs)}


@dataclass
class IdentityStrategy:
    mechanism_tag: str
    primary_char_id: str = ""
    char_lora_path: Optional[str] = None
    char_lora_strength: Optional[float] = None
    conditioned_chars: List[CharIdentitySpec] = field(default_factory=list)
    unconditioned_chars: List[str] = field(default_factory=list)

    @property
    def secondary_specs(self) -> List[CharIdentitySpec]:
        return [c for c in self.conditioned_chars if c.char_id != self.primary_char_id]

    def to_metadata_dict(self) -> dict:
        return {
            "mechanism_tag": self.mechanism_tag,
            "primary_char_id": self.primary_char_id,
            "conditioned_chars": [c.to_dict() for c in self.conditioned_chars],
            "unconditioned_chars": list(self.unconditioned_chars),
        }
```

- [ ] **Step 4: Run — PASS**, then commit (pathspec)

```bash
git commit -m "feat(p1-1): IdentityStrategy promise types (cinema/shots/strategy.py)" -- cinema/shots/strategy.py tests/unit/test_identity_strategy_router.py
```

### Task 5: `_resolve_identity_strategy` — the decision matrix

**Files:**
- Modify: `cinema/shots/controller.py` (new module-level function near the top-level
  helpers; import the strategy module)
- Test: `tests/unit/test_identity_strategy_router.py` (extend)

- [ ] **Step 1: Write the failing matrix tests** (spec §8.6: in_frame × tier × assets)

```python
from cinema.shots.controller import _resolve_identity_strategy

SETTINGS_NO_LORA = {"quality_tier": "production"}
CC_TWO_REGISTERED = {
    "primary_reference": "/r/a.jpg", "identity_anchor": "anchor a",
    "secondary_chars": [{"char_id": "char_b", "reference": "/r/b.jpg",
                         "multi_angle_refs": ["/r/b1.jpg"],
                         "identity_anchor": "anchor b"}],
}
CC_PRIMARY_ONLY = {"primary_reference": "/r/a.jpg", "identity_anchor": "anchor a",
                   "secondary_chars": []}


def _shot(chars, primary=""):
    return {"characters_in_frame": chars, "primary_character": primary}


def test_single_char_with_ref_is_primary_only_and_matches_todays_bundle():
    s = _resolve_identity_strategy(
        _shot(["char_a"]), "production",
        {"char_lora_paths": {"char_a": "/l/a.safetensors"},
         "char_lora_strengths": {"char_a": 0.55}},
        CC_PRIMARY_ONLY,
    )
    assert s.mechanism_tag == "PRIMARY_ONLY"
    # zero-regression invariant: identical to today's controller.py:544-549 derivation
    assert s.primary_char_id == "char_a"
    assert s.char_lora_path == "/l/a.safetensors"
    assert s.char_lora_strength == 0.55
    assert [c.char_id for c in s.conditioned_chars] == ["char_a"]
    assert s.unconditioned_chars == []


def test_two_char_production_with_refs_is_kontext_multi():
    s = _resolve_identity_strategy(_shot(["char_a", "char_b"]), "production",
                                   SETTINGS_NO_LORA, CC_TWO_REGISTERED)
    assert s.mechanism_tag == "KONTEXT_MULTI_CHAR"
    assert [c.char_id for c in s.conditioned_chars] == ["char_a", "char_b"]
    # V-5: the router must carry the secondary's angle refs into the spec —
    # they feed the slot allocator downstream.
    assert s.conditioned_chars[1].multi_angle_refs == ("/r/b1.jpg",)


def test_two_char_max_tier_is_max_primary_only_with_secondary_unconditioned():
    s = _resolve_identity_strategy(_shot(["char_a", "char_b"]), "max",
                                   SETTINGS_NO_LORA, CC_TWO_REGISTERED)
    assert s.mechanism_tag == "MAX_TIER_PRIMARY_ONLY"
    assert [c.char_id for c in s.conditioned_chars] == ["char_a"]
    assert s.unconditioned_chars == ["char_b"]


def test_secondary_without_ref_is_unconditioned():
    s = _resolve_identity_strategy(_shot(["char_a", "char_b"]), "production",
                                   SETTINGS_NO_LORA, CC_PRIMARY_ONLY)
    assert s.mechanism_tag == "PRIMARY_ONLY"
    assert s.unconditioned_chars == ["char_b"]


def test_kontext_secondary_cap_is_two():
    cc = dict(CC_TWO_REGISTERED)
    cc["secondary_chars"] = [
        {"char_id": f"char_{i}", "reference": f"/r/{i}.jpg",
         "multi_angle_refs": [], "identity_anchor": ""} for i in "bcd"
    ]
    s = _resolve_identity_strategy(_shot(["char_a", "char_b", "char_c", "char_d"]),
                                   "production", SETTINGS_NO_LORA, cc)
    assert len(s.conditioned_chars) == 3          # primary + 2 (Kontext-tier cap)
    assert s.unconditioned_chars == ["char_d"]


def test_no_chars_or_no_primary_ref_is_no_identity_asset():
    s = _resolve_identity_strategy(_shot([]), "production", SETTINGS_NO_LORA,
                                   {"primary_reference": None, "secondary_chars": []})
    assert s.mechanism_tag == "NO_IDENTITY_ASSET"
    assert s.conditioned_chars == []
```

- [ ] **Step 2: Run — expect FAIL** (ImportError)

- [ ] **Step 3: Implement in `cinema/shots/controller.py`**

```python
def _resolve_identity_strategy(shot, quality_tier, settings, cc):
    """Resolve the per-shot identity-conditioning promise (P1-1 spec §3d).

    Pure decision function: replaces the primary-only asset derivation
    (formerly inline at the MAX-TIER WIRE-UP block) and names which characters
    are promised identity conditioning under which mechanism. quality_tier and
    style_reference remain the caller's concern — inputs, not outputs.
    """
    from cinema.shots.strategy import (
        IdentityStrategy, CharIdentitySpec,
        PRIMARY_ONLY, KONTEXT_MULTI_CHAR, MAX_TIER_PRIMARY_ONLY, NO_IDENTITY_ASSET,
    )
    in_frame = shot.get("characters_in_frame") or []
    primary_char_id = shot.get("primary_character") or (in_frame[0] if in_frame else "")
    char_lora_paths = settings.get("char_lora_paths", {}) or {}
    char_lora_path = char_lora_paths.get(primary_char_id) or None
    char_lora_strength = (settings.get("char_lora_strengths", {}) or {}).get(primary_char_id)
    primary_ref = cc.get("primary_reference")
    secondary = cc.get("secondary_chars") or []

    if not in_frame or not primary_ref:
        return IdentityStrategy(
            mechanism_tag=NO_IDENTITY_ASSET,
            primary_char_id=primary_char_id,
            char_lora_path=char_lora_path,
            char_lora_strength=char_lora_strength,
            unconditioned_chars=list(in_frame),
        )

    conditioned = [CharIdentitySpec(
        char_id=primary_char_id, reference=primary_ref,
        identity_anchor=cc.get("identity_anchor", ""),
        multi_angle_refs=tuple(cc.get("multi_angle_refs") or ()),
        fidelity="pulid" if quality_tier == "max" else "reference",
    )]
    conditioned_ids = {primary_char_id}

    if quality_tier == "max":
        tag = MAX_TIER_PRIMARY_ONLY          # slice 2 lifts this to MULTI_LORA
    elif secondary:
        # Kontext-tier cap: 2 secondaries (spec §3a); overflow degrades to text-only.
        for entry in secondary[:2]:
            conditioned.append(CharIdentitySpec(
                char_id=entry["char_id"], reference=entry["reference"],
                identity_anchor=entry.get("identity_anchor", ""),
                # V-5: without this, the Task-7 allocator's
                # entry.get("multi_angle_refs") is ALWAYS empty via this path
                # and secondaries can never fill their 2 slots.
                multi_angle_refs=tuple(entry.get("multi_angle_refs") or ()),
                fidelity="reference",
            ))
            conditioned_ids.add(entry["char_id"])
        tag = KONTEXT_MULTI_CHAR if len(conditioned) > 1 else PRIMARY_ONLY
    else:
        tag = PRIMARY_ONLY

    return IdentityStrategy(
        mechanism_tag=tag,
        primary_char_id=primary_char_id,
        char_lora_path=char_lora_path,
        char_lora_strength=char_lora_strength,
        conditioned_chars=conditioned,
        unconditioned_chars=[c for c in in_frame if c not in conditioned_ids],
    )
```

- [ ] **Step 4: Run the matrix — all PASS**, full file green, then commit (pathspec)

```bash
git commit -m "feat(p1-1): _resolve_identity_strategy decision matrix (router, spec 3d)" -- cinema/shots/controller.py tests/unit/test_identity_strategy_router.py
```

### Task 6: Controller integration — promise written, assets routed, actual recorded

**Files:**
- Modify: `cinema/shots/controller.py:534-551` (the MAX-TIER WIRE-UP block) and
  `:643-662` (the `generate_ai_broll` call), `:663+` (after the result)
- Test: `tests/unit/test_identity_strategy_router.py` (extend with integration tests)

- [ ] **Step 1: Write the failing integration tests.** Fixture reality check
(verified at plan time): `tests/unit/test_cross_controller.py`'s WiredHost/FakeCore
pattern is the construction template for `ShotController`, **but it sets
`core.continuity = None` and never calls `generate_keyframe_take`** — copied as-is,
these tests crash at `self.continuity.enhance_shot_prompt`. The delta you must add
on top of that pattern (R-BRIEF: read the sibling's FakeCore first; its field names
win over this sketch):

```python
class StubContinuity:
    """enhance_shot_prompt stand-in: returns a canned continuity_config."""
    def __init__(self, secondary_chars):
        self._sec = secondary_chars

    def enhance_shot_prompt(self, shot, scene, prev_shot, shot_index,
                            approved_anchor_image=None):
        return {"prompt": "stub prompt", "continuity_config": {
            "primary_reference": "/r/a.jpg", "identity_anchor": "anchor a",
            "multi_angle_refs": [], "secondary_chars": self._sec,
            "scene_seed": 1, "use_img2img": False, "identity_threshold": 0.65,
        }}


@pytest.fixture
def captured(monkeypatch, tmp_path):
    """Record generate_ai_broll kwargs; return a fake success."""
    box = {}

    def fake_broll(prompt, output_filename, **kwargs):
        box["kwargs"] = kwargs
        open(output_filename, "wb").close()      # satisfy the exists() guard
        from phase_c_assembly import ImageGenResult
        return ImageGenResult(output_filename, "FLUX_KONTEXT")

    monkeypatch.setattr("cinema.shots.controller.generate_ai_broll", fake_broll)
    return box


def _latest_keyframe_take(host, shot_id):
    for scene in host.project["scenes"]:
        for shot in scene["shots"]:
            if shot["id"] == shot_id:
                return shot["keyframe_takes"][-1]
    raise AssertionError(f"no keyframe take on {shot_id}")
```

`controller_one_char` / `controller_two_chars` = the sibling's WiredHost/FakeCore
construction with `core.continuity = StubContinuity([])` /
`StubContinuity([{"char_id": "char_b", "reference": "/r/b.jpg",
"multi_angle_refs": [], "identity_anchor": "anchor b"}])`, a project containing one
scene + one shot with `characters_in_frame` of `["char_a"]` / `["char_a", "char_b"]`.
Three requirements the sibling's pattern makes easy to miss (each crashes the test
if skipped — verified against the real code paths):
1. `generate_keyframe_take` → `_mutate_shot(save=True)` → `mutate_project` does
   DISK I/O under `PROJECTS_DIR`. Note the sibling's `_project_on_disk` is a plain
   context manager taking `(tmpdir, project)` — two params
   (test_cross_controller.py:441-442; characterization corrected per Lane-V M-5),
   NOT a pytest fixture — in a pytest-fixture file the simpler route is a direct
   `monkeypatch.setattr(domain.project_manager, "PROJECTS_DIR", str(tmp_path /
   "projects"))` with the project JSON pre-written there. Pick that.
2. `_mutate_shot` runs `Project.model_validate(self.project)` first — copy the
   sibling's `_sample_project` shot dict VERBATIM (its fields are known
   schema-valid; unlisted fields default), trimmed to one scene + one shot, with
   `characters_in_frame` set per fixture. Set `core.continuity = StubContinuity(…)`
   AFTER constructing FakeCore (its `__init__` sets continuity to None).
3. Monkeypatch `phase_c_vision._get_shared_validator` with a stub whose
   `validate_image(...)` returns an object exposing `overall_score=0.8`,
   `passed=True`, `character_results={}` — the validation block runs on the
   success path (Task 9 extends these same fixtures).

The tests:

```python
def test_single_char_take_metadata_and_kwargs_unchanged(controller_one_char, captured):
    res = controller_one_char.generate_keyframe_take("scene_1", "shot_1")
    assert res["success"]
    take = _latest_keyframe_take(controller_one_char, "shot_1")
    assert take["metadata"]["identity_strategy"]["mechanism_tag"] == "PRIMARY_ONLY"
    assert take["metadata"]["mechanism_actually_used"] == "FLUX_KONTEXT"
    # exact same kwargs today's code sends — zero regression
    assert captured["kwargs"]["char_lora_path"] is None
    assert "secondary_char_refs" not in captured["kwargs"] or \
        captured["kwargs"]["secondary_char_refs"] is None


def test_two_char_take_promises_kontext_multi_and_forwards_refs(
        controller_two_chars, captured):
    controller_two_chars.generate_keyframe_take("scene_1", "shot_1")
    take = _latest_keyframe_take(controller_two_chars, "shot_1")
    md = take["metadata"]["identity_strategy"]
    assert md["mechanism_tag"] == "KONTEXT_MULTI_CHAR"
    sent = captured["kwargs"]["secondary_char_refs"]
    assert [c["char_id"] for c in sent] == ["char_b"]
    assert "multi_angle_refs" in sent[0]   # V-5: field survives the to_dict chain
    # V-2: derived actual — multi-char emission on a successful Kontext call
    assert take["metadata"]["mechanism_actually_used"] == "FLUX_KONTEXT_MULTI_CHAR"
```

- [ ] **Step 2: Run — expect FAIL** (no `identity_strategy` key)

- [ ] **Step 3: Implement.** In the MAX-TIER WIRE-UP block, replace the
primary-only derivation (`in_frame` / `primary_char_id` / `char_lora_path` /
`char_lora_strength` lines — currently :544-549) with:

```python
        strategy = _resolve_identity_strategy(shot, quality_tier, settings, cc)
        primary_char_id = strategy.primary_char_id
        char_lora_path = strategy.char_lora_path
        char_lora_strength = strategy.char_lora_strength
        take["metadata"]["identity_strategy"] = strategy.to_metadata_dict()
```

(`quality_tier` at :539 and `style_refs` at :550-551 stay exactly where they are.
DELETE the `char_lora_paths = settings.get(...)` line at :540 — the resolver
re-reads it from `settings` internally; leaving it behind is a dead assignment.)
At the `generate_ai_broll` call (:643) add one kwarg:

```python
            secondary_char_refs=[c.to_dict() for c in strategy.secondary_specs] or None,
```

NOTE: `generate_ai_broll` does not accept this kwarg until Task 8. To keep the
suite green between Tasks 6 and 8, add the kwarg to `generate_ai_broll`'s signature
NOW as an accepted-and-unused passthrough (`secondary_char_refs=None` in
`phase_c_assembly.py:75-81`, docstring "P1-1 slice 1: consumed by the Kontext
fallback — wiring lands behind the S1 gate"), and forward it to nothing yet.
After the result returns (:663):

```python
        actual = result.api_name if result else None
        if actual == "FLUX_KONTEXT" and strategy.secondary_specs:
            # V-2 / spec §3(d): api_name is backend-granular — a successful
            # Kontext call looks identical for multi-char and primary-only, so
            # derive the actual from api_name x what the strategy emitted.
            # This records EMISSION, not server honoring; S1 + per-char
            # validation cover the latter.
            actual = "FLUX_KONTEXT_MULTI_CHAR"
        take["metadata"]["mechanism_actually_used"] = actual
```

(Place it after the existing `if not result` early-return so the failure path is
unchanged.)

- [ ] **Step 4: Run the new tests + the controller + snapshot suites — green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_identity_strategy_router.py tests/unit/test_cross_controller.py tests/unit/test_kontext_prompt_snapshot.py -q`

- [ ] **Step 5: Full suite + smoke, then commit (pathspec)**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/ -q
.venv/bin/python scripts/ci_smoke.py
git commit -m "feat(p1-1): keyframe takes carry identity_strategy promise + mechanism_actually_used" -- cinema/shots/controller.py phase_c_assembly.py tests/unit/test_identity_strategy_router.py
```

## Chunk 3: Kontext multi-char branch (S1-gated) + accountability + registration

> **GATE — RESOLVED 2026-06-10 (spec §6 "S1 RESULT" is the full record):** S1
> ran live (user-approved). Pre-registered quantitative criteria returned NO-GO
> on both measurement passes, but the measurement itself was shown invalid at
> two-shot face scale (control-anchor saturation + embedding domain-gap: the
> UNCONDITIONED baseline outscored the conditioned arms against the secondary's
> ref). The blocking question answered qualitatively: @Image2 HONORED, zero
> blending across all three arms. **Disposition: Tasks 7–8 PROCEED** —
> secondaries stay advisory-fail territory exactly as §3(a) projects. One
> implementation note from the spike: wardrobe cross-bleed (multi_b put the
> secondary's reference clothing on both people) — Task 7's prompt builder
> carries a keep-own-clothing constraint for it.

### Task 7: Slot allocator + multi-char prompt builder (pure functions)

**Files:**
- Modify: `phase_c_assembly.py` (two new module-level helpers above `_fal_flux_fallback`)
- Test: `tests/unit/test_kontext_multichar.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
from phase_c_assembly import _allocate_ref_slots, _build_multichar_kontext_prompt


def test_two_char_allocation_3_2():
    paths, slot_map = _allocate_ref_slots(
        primary_refs=["/a/1.jpg", "/a/2.jpg", "/a/3.jpg", "/a/4.jpg"],
        secondary_chars=[{"char_id": "char_b", "reference": "/b/c.jpg",
                          "multi_angle_refs": ["/b/1.jpg", "/b/2.jpg"]}],
    )
    assert paths == ["/a/1.jpg", "/a/2.jpg", "/a/3.jpg", "/b/c.jpg", "/b/1.jpg"]
    assert slot_map == {"primary": [1, 2, 3], "char_b": [4, 5]}


def test_three_char_allocation_3_2_1_and_six_cap():
    paths, slot_map = _allocate_ref_slots(
        primary_refs=["/a/1.jpg", "/a/2.jpg", "/a/3.jpg"],
        secondary_chars=[
            {"char_id": "char_b", "reference": "/b/c.jpg",
             "multi_angle_refs": ["/b/1.jpg"]},
            {"char_id": "char_c", "reference": "/c/c.jpg",
             "multi_angle_refs": ["/c/1.jpg", "/c/2.jpg"]},
        ],
    )
    assert len(paths) == 6
    assert slot_map == {"primary": [1, 2, 3], "char_b": [4, 5], "char_c": [6]}


def test_thin_secondary_does_not_inflate_primary():
    """Slots are CONTIGUOUS and shares are FIXED (primary 3 / sec-1 2 / sec-2 1):
    a thin secondary leaves the cap unfilled rather than reordering slots."""
    paths, slot_map = _allocate_ref_slots(
        primary_refs=["/a/1.jpg", "/a/2.jpg", "/a/3.jpg", "/a/4.jpg", "/a/5.jpg"],
        secondary_chars=[{"char_id": "char_b", "reference": "/b/c.jpg",
                          "multi_angle_refs": []}],
    )
    assert slot_map["primary"] == [1, 2, 3]   # fixed at 3 when secondaries exist
    assert slot_map["char_b"] == [4]          # canonical only — nothing to fill with
    assert len(paths) == 4                    # cap is a ceiling, not a quota


def test_single_char_alone_keeps_all_six():
    paths, slot_map = _allocate_ref_slots(
        primary_refs=[f"/a/{i}.jpg" for i in range(8)], secondary_chars=[],
    )
    assert slot_map == {"primary": [1, 2, 3, 4, 5, 6]}
    assert len(paths) == 6


def test_multichar_prompt_addresses_each_slot():
    prompt = _build_multichar_kontext_prompt(
        {"SCENE": "a rooftop cafe", "ACTION": "talking", "OUTFIT": "",
         "SHOT": "Medium two-shot"},
        char_blocks=[(1, "a woman with auburn hair"), (4, "a man with a grey beard")],
    )
    assert "@Image1 is a woman with auburn hair" in prompt
    assert "@Image4 is a man with a grey beard" in prompt
    assert "Do NOT blend or average" in prompt
    assert "Do NOT transfer clothing" in prompt   # S1 wardrobe cross-bleed pin
    assert "CHANGE BACKGROUND: a rooftop cafe." in prompt
    assert prompt.count("PRESERVE IDENTITY") == 2
```

- [ ] **Step 2: Run — expect FAIL** (ImportError)

- [ ] **Step 3: Implement** (above `_fal_flux_fallback`; mirror its comment style)

```python
def _allocate_ref_slots(primary_refs, secondary_chars, cap=6):
    """Partition the Kontext image_urls budget across characters (P1-1 spec §3a).

    FIXED shares, CONTIGUOUS slots: primary takes up to 3 (up to `cap` when no
    secondaries); the first secondary up to 2 (canonical first, then angles);
    the second secondary up to 1. The cap is a ceiling, not a quota — thin
    secondaries leave it unfilled rather than reordering slots (the primary's
    @ImageN indices must stay 1..k). Returns (ordered file paths, slot_map)
    with 1-based @ImageN indices per char_id ('primary' for the primary).
    """
    n_secondary = len(secondary_chars)
    primary_take = min(len(primary_refs), 3 if n_secondary else cap)
    paths = list(primary_refs[:primary_take])
    slot_map = {"primary": list(range(1, len(paths) + 1))}
    for i, entry in enumerate(secondary_chars):
        share = 2 if i == 0 else 1
        char_paths = ([entry["reference"]]
                      + list(entry.get("multi_angle_refs") or []))[:share]
        start = len(paths) + 1
        paths.extend(char_paths)
        slot_map[entry["char_id"]] = list(range(start, start + len(char_paths)))
    return paths, slot_map
```

(This is the FINAL allocator — fixed shares 3/2/1, never more than 6 with the
router's 2-secondary cap. Spec §3(a) now states this same fixed-share rule —
the wording was synced at the 2026-06-11 Lane-V disposition (V-7), so no Task-12
sync remains for it.)

```python
def _build_multichar_kontext_prompt(sections, char_blocks):
    """Per-character @ImageN PRESERVE blocks + shared scene/constraints/quality.

    char_blocks: [(first_slot_index, identity_anchor), ...] — one per character,
    primary first. Single-char shots NEVER reach this function (early return in
    _fal_flux_fallback keeps the golden-snapshot path untouched).
    """
    scene_desc = sections.get("SCENE", "")
    action_desc = sections.get("ACTION", "facing the camera")
    outfit_desc = sections.get("OUTFIT", "")
    shot_desc = sections.get("SHOT", "Medium shot, 85mm lens")

    parts = []
    for slot, anchor in char_blocks:
        who = anchor or "the person in this reference"
        parts.append(
            f"PRESERVE IDENTITY: The person from @Image{slot} is {who}. "
            f"Keep this EXACT face, hair, glasses, eye color, skin tone unchanged."
        )
    parts.append(f"CHANGE BACKGROUND: {scene_desc}.")
    if outfit_desc:
        parts.append(f"CHANGE OUTFIT: {outfit_desc}.")
    parts.append(f"SET POSE: {action_desc}.")
    parts.append(f"SET CAMERA: {shot_desc}.")
    tokens = ", ".join(f"@Image{slot}" for slot, _ in char_blocks)
    parts.append(
        f"CONSTRAINTS: Do NOT alter facial features, hairstyle, glasses, or skin. "
        f"Do NOT generate a different person. Do NOT blend or average the faces. "
        f"Do NOT transfer clothing between people — each person keeps their own "
        f"outfit. "
        f"Each output face MUST match its own reference ({tokens}) exactly."
    )
    parts.append(
        "QUALITY: Photorealistic, visible skin pores and subsurface scattering, "
        "shallow depth of field with circular bokeh, natural film grain ISO 400, "
        "volumetric atmospheric lighting, micro-detail in fabric texture, "
        "no AI artifacts, no smooth plastic skin, no over-saturated colors."
    )
    return " ".join(parts)
```

- [ ] **Step 4: Run — PASS; commit (pathspec)**

```bash
git commit -m "feat(p1-1): Kontext slot allocator + multi-char prompt builder (S1 GO)" -- phase_c_assembly.py tests/unit/test_kontext_multichar.py
```

### Task 8: Wire the branch into `_fal_flux_fallback`

**Files:**
- Modify: `phase_c_assembly.py:439-478` (signature + ref-collection) — single-char
  path untouched; `generate_ai_broll` forwards the kwarg to every
  `_fal_flux_fallback` call site (`grep -n '_fal_flux_fallback(' phase_c_assembly.py`
  — update ALL hits; while in the signature, audit the `ctx` note from spec §3(a))
- Test: `tests/unit/test_kontext_multichar.py` + the Task-1 snapshot must stay
  green; EXTEND `tests/unit/test_phase_c_assembly_provenance.py` (spec AC6 —
  Lane-V V-6: this extension was named by the spec but never implemented by any
  task; it lands here, in the same task that touches the signature)

- [ ] **Step 1: Write the failing test.** Pytest does NOT resolve fixtures across
test modules: either move `fal_capture` from Task 1's file into
`tests/unit/conftest.py` (check whether one exists and what it already holds —
don't collide), or define a local copy in `tests/unit/test_kontext_multichar.py`.
Local copy is the safe default.

```python
def test_multichar_branch_sends_both_chars_refs_and_blocks(fal_capture, tmp_path):
    a = tmp_path / "a.jpg"; a.write_bytes(b"j")
    b = tmp_path / "b.jpg"; b.write_bytes(b"j")
    out = tmp_path / "out.jpg"
    result = phase_c_assembly._fal_flux_fallback(
        "A rooftop cafe", str(out),
        character_image=str(a),
        identity_anchor="a woman with auburn hair",
        secondary_char_refs=[{"char_id": "char_b", "reference": str(b),
                              "multi_angle_refs": [],
                              "identity_anchor": "a man with a grey beard"}],
    )
    assert result.api_name == "FLUX_KONTEXT"
    args = fal_capture["arguments"]
    assert len(args["image_urls"]) == 2
    assert "@Image2 is a man with a grey beard" in args["prompt"]
    assert args["prompt"].count("PRESERVE IDENTITY") == 2


def test_empty_secondary_refs_is_byte_identical_to_single_char(fal_capture, tmp_path):
    """The early return: secondary_char_refs=None and =[] both take the old path."""
    # …same body as the Task-1 snapshot test, with secondary_char_refs=[] —
    # asserts the SAME golden string. Import the golden constant from the
    # snapshot test module rather than duplicating it.
```

And in `tests/unit/test_phase_c_assembly_provenance.py` (spec AC6 / Lane-V V-6 —
mirror that file's existing fixture pattern, R-BRIEF):

```python
def test_kontext_failure_with_secondaries_falls_back_with_original_prompt(...):
    """V-1 pin: when the Kontext call raises and secondary_char_refs were passed,
    the FLUX-Pro fallback receives the ORIGINAL prompt — the @ImageN multi-char
    rewrite must never escape the Kontext try-block (phase_c_assembly.py:557
    passes `prompt`, not `kontext_prompt`)."""
    # Arrange: subscribe raises on the 'kontext' endpoint, succeeds on
    # 'flux-pro/v1.1-ultra'; capture the flux-pro call's arguments.
    # Assert: captured prompt == the original prompt argument (no "@Image" in it);
    #         result.api_name == "FLUX_PRO".
```

- [ ] **Step 2: Run — expect FAIL** (unexpected kwarg)

- [ ] **Step 3: Implement.** Add `secondary_char_refs=None` to `_fal_flux_fallback`'s
signature. Inside the Kontext block, branch BEFORE the existing ref-collection:

```python
                if secondary_char_refs:
                    # P1-1 multi-char branch (S1-gated). Existence-filter refs the
                    # same way the single-char path does, allocate slots, address
                    # each character by its first slot.
                    primary_refs = [r for r in (multi_angle_refs or []) if os.path.exists(r)] \
                        or [character_image]
                    live_secondaries = [
                        e for e in secondary_char_refs if os.path.exists(e["reference"])
                    ]
                    ref_paths, slot_map = _allocate_ref_slots(primary_refs, live_secondaries)
                    image_urls = []
                    for ref_path in ref_paths:
                        try:
                            image_urls.append(fal_client.upload_file(ref_path))
                        except Exception:
                            pass
                    sections = _parse_structured_prompt(prompt)
                    char_blocks = [(slot_map["primary"][0], identity_anchor)]
                    char_blocks += [
                        (slot_map[e["char_id"]][0], e.get("identity_anchor", ""))
                        for e in live_secondaries if e["char_id"] in slot_map
                    ]
                    kontext_prompt = _build_multichar_kontext_prompt(sections, char_blocks)
                    print(f"   [KONTEXT] Multi-char ({len(image_urls)} refs, "
                          f"{len(char_blocks)} identities)")
                else:
                    <existing lines :462-529 — UNTOUCHED>
```

The enclosing structure after the edit — BOTH branches assign `image_urls` and
`kontext_prompt`, then ONE shared `subscribe` follows at the if/else's indent level
(do NOT duplicate the subscribe call):

```python
                if secondary_char_refs:
                    # …multi-char block above…
                    if not image_urls:
                        # all uploads failed — degrade to single-char via the
                        # multichar builder (1 block); do not crash the take
                        image_urls = [fal_client.upload_file(character_image)]
                        kontext_prompt = _build_multichar_kontext_prompt(
                            _parse_structured_prompt(prompt),
                            [(1, identity_anchor)],
                        )
                else:
                    # existing lines :462-529 byte-for-byte, including their own
                    # `if not image_urls:` guard — the golden snapshot pins them
                    ...

                result = fal_client.subscribe(            # :531 — unchanged, shared
                    "fal-ai/flux-pro/kontext/max/multi", ...)
```

(The degraded single-char-via-multichar-builder prompt differs from the golden
single-char prompt — acceptable: it only fires when secondaries were requested AND
every upload failed. The degradation block's own `upload_file` call may raise too —
that lands in the enclosing `except Exception as e_kontext` and cascades to
FLUX-Pro, which is exactly the existing total-failure behavior.) Forward the kwarg from `generate_ai_broll` (signature already
accepts it since Task 6) to ALL SIX `_fal_flux_fallback` call sites —
phase_c_assembly.py:171, 178, 190, 215, 412, 417 at plan time; re-grep
(`grep -n '_fal_flux_fallback(' phase_c_assembly.py`) rather than trusting these
numbers. Five of the six are error/fallback paths where the value is simply None —
update them anyway so the signature stays coherent.

- [ ] **Step 4: Run multichar + snapshot + provenance suites — green; then full suite + smoke; commit (pathspec)**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_kontext_multichar.py tests/unit/test_kontext_prompt_snapshot.py tests/unit/test_phase_c_assembly_provenance.py -q
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/ -q
git commit -m "feat(p1-1): multi-character Kontext keyframes — secondary refs + @ImageN addressing" -- phase_c_assembly.py tests/unit/test_kontext_multichar.py tests/unit/test_phase_c_assembly_provenance.py
```

### Task 9: Per-character keyframe validation (`identity_per_char`)

**Files:**
- Modify: `cinema/shots/controller.py:666-704` (post-generation validation block)
- Test: `tests/unit/test_identity_strategy_router.py` (extend)

- [ ] **Step 1: Write the failing test** — monkeypatch
`phase_c_vision._get_shared_validator` (controller imports it inside the function;
patch at source module) with a stub returning fixed scores per character_id:

```python
def test_identity_per_char_written_for_conditioned_only(controller_two_chars, captured):
    controller_two_chars.generate_keyframe_take("scene_1", "shot_1")
    take = _latest_keyframe_take(controller_two_chars, "shot_1")
    per_char = take["metadata"]["identity_per_char"]
    assert set(per_char) == {"char_a", "char_b"}      # conditioned chars only
    assert take["metadata"]["identity_score"] == per_char["char_a"]  # scalar = primary, unchanged


def test_single_char_identity_per_char_pins_scalar_convention(
        controller_one_char, captured):
    """INFO-3 pin: a single-char shot gets identity_per_char == {primary: scalar}
    and the identity_score scalar itself is byte-unchanged."""
    controller_one_char.generate_keyframe_take("scene_1", "shot_1")
    take = _latest_keyframe_take(controller_one_char, "shot_1")
    assert take["metadata"]["identity_per_char"] == \
        {"char_a": take["metadata"]["identity_score"]}
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement.** Keep the existing primary block byte-identical
(identity_score scalar, failure diagnostics, T6 advisory). After it, add:

```python
        # P1-1: score every conditioned character; unconditioned chars are never
        # scored (a low score on them would be expected, not a generation failure).
        if primary_ref:
            per_char = {primary_char_id: identity_score}
            for spec_c in strategy.secondary_specs:
                sec_result = _get_shared_validator().validate_image(
                    img_path, spec_c.reference,
                    character_id=spec_c.char_id,
                    threshold=threshold,
                )
                per_char[spec_c.char_id] = sec_result.overall_score
            take["metadata"]["identity_per_char"] = per_char
```

(Same `identity_per_char` key the motion take uses — controller.py:1060-1066;
separate take dicts, no collision, one scorecard convention.)

- [ ] **Step 4: Run, full suite, commit (pathspec)**

```bash
git commit -m "feat(p1-1): keyframe takes score every conditioned char (identity_per_char)" -- cinema/shots/controller.py tests/unit/test_identity_strategy_router.py
```

### Task 10: Scorecard surfaces `identity_multi`

**Files:**
- Modify: `cinema/capability_scorecard.py:141-163` (per-shot loop; current identity
  read is `identity_score` at :144, per_shot entry at :160)
- Test: `tests/unit/test_capability_scorecard.py` (extend — mirror its fixtures)

- [ ] **Step 1: Write the failing test**

```python
def test_per_shot_identity_multi_surfaces_promise_and_scores():
    shot = _shot_with_approved_keyframe(metadata={
        "identity_score": 0.8,
        "identity_per_char": {"char_a": 0.8, "char_b": 0.55},
        "identity_strategy": {"mechanism_tag": "KONTEXT_MULTI_CHAR",
                              "primary_char_id": "char_a",
                              "conditioned_chars": [{"char_id": "char_a"},
                                                    {"char_id": "char_b"}],
                              "unconditioned_chars": ["char_c"]},
    })
    card = build_capability_scorecard(_project([shot]), project_dir="/tmp/x")
    entry = card["per_shot"][0]
    assert entry["identity_multi"] == {
        "mechanism": "KONTEXT_MULTI_CHAR",
        "per_char": {"char_a": 0.8, "char_b": 0.55},
        "unconditioned": ["char_c"],
    }


def test_per_shot_identity_multi_absent_for_legacy_takes():
    shot = _shot_with_approved_keyframe(metadata={"identity_score": 0.8})
    card = build_capability_scorecard(_project([shot]), project_dir="/tmp/x")
    assert "identity_multi" not in card["per_shot"][0]
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement** in the per-shot loop (after the :160 `per_shot.append`,
mutate the just-built entry, or build it conditionally):

```python
        kf_md = (kf or {}).get("metadata", {})
        if kf_md.get("identity_strategy"):
            strat = kf_md["identity_strategy"]
            per_shot[-1]["identity_multi"] = {
                "mechanism": strat.get("mechanism_tag"),
                "per_char": kf_md.get("identity_per_char", {}),
                "unconditioned": strat.get("unconditioned_chars", []),
            }
```

- [ ] **Step 4: Run, full suite, commit (pathspec)**

```bash
git commit -m "feat(p1-1): scorecard identity_multi — promise vs per-char measurement" -- cinema/capability_scorecard.py tests/unit/test_capability_scorecard.py
```

### Task 11: Register the Aria LoRA (pod-independent prerequisite, spec §7.3)

**Files:**
- Create: `scripts/_register_aria_lora.py`

- [ ] **Step 1: Write the script**

```python
"""Register the fal-trained Aria LoRA onto project cfd3f0967eb3 (P1-1 spec §7.3).

No machine-validated strength exists (the v2 sweep covered only {0.55, 0.65, 0.70};
no argmax persisted) — strength 0.55 is supplied manually per the 2026-06-02
finding. Trigger 'TOKwoman' is supplied manually (FAL-trained LoRAs have no
dataset_manifest.json; the value is hardcoded in scripts/_fal_lora_train.py:28).
The .safetensors stays local; pod-side placement into ComfyUI's loras/ dir is a
slice-2 pod-session step. Idempotent; prints before/after.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.project_manager import mutate_project, load_project

PROJECT_ID = "cfd3f0967eb3"
CHAR_ID = "char_b9c8bcfe9af0"
LORA_PATH = os.path.abspath("logs/char_lora_fal_v2.safetensors")
STRENGTH = 0.55
TRIGGER = "TOKwoman"


def main() -> int:
    assert os.path.exists(LORA_PATH), f"missing artifact: {LORA_PATH}"
    project = load_project(PROJECT_ID)
    chars = [c.get("id") for c in project.get("characters", [])]
    assert CHAR_ID in chars, f"{CHAR_ID} not in project characters: {chars}"

    def _mutate(p):
        gs = p.setdefault("global_settings", {})
        before = {k: gs.get(k) for k in
                  ("char_lora_paths", "char_lora_strengths", "char_lora_triggers")}
        gs.setdefault("char_lora_paths", {})[CHAR_ID] = LORA_PATH
        gs.setdefault("char_lora_strengths", {})[CHAR_ID] = STRENGTH
        gs.setdefault("char_lora_triggers", {})[CHAR_ID] = TRIGGER
        print("before:", json.dumps(before, indent=1))
        return p

    mutate_project(PROJECT_ID, _mutate)
    after = load_project(PROJECT_ID).get("global_settings", {})
    print("after:", json.dumps({k: after.get(k) for k in
          ("char_lora_paths", "char_lora_strengths", "char_lora_triggers")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

NOTE: verify `load_project`'s actual name/signature first
(`grep -n 'def load_project\|def get_project' domain/project_manager.py`) and adapt —
the mutate callback shape is verified (mutate_project at
domain/project_manager.py:712); the loader name is not.

- [ ] **Step 2: Run it; verify the three keys land**

Run: `.venv/bin/python scripts/_register_aria_lora.py`
Expected: after-block shows all three dicts populated for `char_b9c8bcfe9af0`.

- [ ] **Step 3: Commit (pathspec — script only; project.json data files are not committed if gitignored — check `git status` and follow the repo's existing treatment of domain/projects/)**

```bash
git commit -m "feat(p1-1): register Aria LoRA (manual strength 0.55 + TOKwoman trigger, spec 7.3)" -- scripts/_register_aria_lora.py
```

### Task 12: Doc sync + final verification

**Files:**
- Modify: `ARCHITECTURE.md` §8.2 (production-tier cascade — note per-character
  Kontext conditioning + the identity_strategy promise metadata, with file:line
  anchors), spec §6 (S1 measured scores; the §3(a) slot-rule wording was already
  synced at the 2026-06-11 Lane-V disposition — only re-sync if implementation
  diverges further)
- Reference: R-START rule — doc fixes ride the same session as the code

- [ ] **Step 1: Update ARCHITECTURE.md §8.2** with the new data flow (2-4 sentences +
anchors: `_resolve_identity_strategy`, `secondary_chars`, `_allocate_ref_slots`,
`identity_per_char`). Run the doc verifier:

Run: `.venv/bin/python scripts/check_doc_claims.py` (standalone `__main__` works;
ci_smoke imports it as a module — either route is fine) — expect zero drifts.

- [ ] **Step 2: Record S1's measured scores in the spec** (§6, whichever verdict).

- [ ] **Step 3: Full suite + smoke one last time**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/ -q` → N passed / 0 failed (N ≥ 2021 + new tests)
Run: `.venv/bin/python scripts/ci_smoke.py` → OK

- [ ] **Step 4: Commit (pathspec), update the handoff per the session-wrap ritual**

```bash
git commit -m "docs(p1-1): ARCHITECTURE 8.2 multi-char keyframe flow + S1 result recorded" -- ARCHITECTURE.md docs/SPEC-P1-1-multichar-generation-identity-2026-06-10.md
```

---

## Out of scope (do not let the session absorb these)

- Mechanisms (b)/(c) — max-tier LoRA chaining, dual ReActor, chained PuLID: slice 2,
  pod-gated (spec §7.2). The `char_lora_triggers` CONSUMPTION is slice 2; slice 1
  only persists it (Task 11).
- The `web_server.py` train-endpoint write of `char_lora_triggers`: slice-2 prep.
- Scorecard scalar swap to per-char mean; SSE/FE surfacing of identity_multi.
- The production `pulid.json` SDXL-PuLID-on-FLUX bug (spec §9) — separate ticket.
- Budget gating of keyframe spend (ADR-022 backlog).
