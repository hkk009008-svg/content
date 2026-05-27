# PR-* Cell Pre-Staging Cross-References — Cycle 15 Entry (2026-05-27)

**From:** Operator-seat (cycle-15 entry adjacent-useful work; Lane C-style read-only survey)
**For:** Director-seat (next session, cycle-15+) — substrate for 5 remaining PR-* STUB cell fills in [docs/BRIEF-comprehensive-test-2026-05-27.md](BRIEF-comprehensive-test-2026-05-27.md)
**Companion canonical:** [docs/EXTENSIVE-TEST-PLAN-2026-05-27.md](EXTENSIVE-TEST-PLAN-2026-05-27.md) §5 P1-P14 (operator-default per Option B semantic split)
**Format reference:** filled PR-* cells in brief §5.3 (PR-STORY, PR-IMAGE, PR-MOTION — director-authored at v0.3)

---

## Purpose

Per the cycle-14 close operator handoff §"Mid-term" + cycle-14 close director handoff §"What I would do next" priority #1: director's next session has 5 PR-* STUB cells to fill for brief v1.0 ship. Each maps to one or two operator-testplan §5 P-sections per the brief §5.3 status table.

This doc provides:

1. **Verified impl file:line refs** for each PR-* cell (Rule #12 grep-the-writes applied; surfaced 2 testplan inaccuracies — see §"Verification notes")
2. **Cross-reference substrate** (testplan P-source content + ARCHITECTURE refs + tier classification) ready for director's authorship
3. **Pattern reminders** from the 3 filled PR-* cells (PR-STORY/PR-IMAGE/PR-MOTION) so director's fills mirror the established §4 predictive harness format

**This doc does NOT pre-author the cells themselves.** Per role partition Sh, PR-* fills are director-default. Operator's pre-staging stops at "substrate ingredients ready for director to compose."

---

## Cell-to-source mapping (at-a-glance)

| Cell | Testplan §5 P-source | Impl file:line (verified) | Tier | ARCHITECTURE ref |
|---|---|---|---|---|
| **PR-DIALOGUE** | P8 — Dialogue Writer | [`domain/dialogue_writer.py:60`](../domain/dialogue_writer.py) (`system_prompt = ...`) | C | §7 LLM ensemble (dialogue layer) |
| **PR-CONTINUITY** | P12 — Continuity prompt enhancement | [`domain/continuity_engine.py:446`](../domain/continuity_engine.py) (`def enhance_shot_prompt`) | B + C | §8 continuity engine |
| **PR-STYLE-LLM** | P1 — Style Director system_prompt | [`llm/style_director.py:62`](../llm/style_director.py) (`system_prompt = f"""You are a world-class cinematographer...`) | B + C | §7.1 style stage |
| **PR-CHIEFDIR** | P2 (HC1-HC8 / T1-T9) + P3 (RETRY/ACCEPT_LENIENT/FAIL) | [`llm/chief_director.py:130-206`](../llm/chief_director.py) (system prompt) + [`llm/chief_director.py:208`](../llm/chief_director.py) (`def validate_shot_prompts`) + [`llm/chief_director.py:~318-446`](../llm/chief_director.py) (`diagnose_failure` decision arms) | B + C | §7 LLM ensemble + validation |
| **PR-AUDIO-VIBE** | P9 — Music prompt `_build_music_prompt` | [`audio/music.py:88`](../audio/music.py) (`def _build_music_prompt(music_vibe: str)`) | B + C | §13 audio pipeline |

---

## Per-cell substrate

### PR-DIALOGUE → testplan P8

**Source quote (operator testplan §5 P8):**
> P8. Dialogue Writer (`domain/dialogue_writer.py:60`)
> - **Current:** "professional screenwriter for photorealistic cinema"
> - **Predicted weakness:** Dialogue may default to cinematic clichés
> - **Tweak variants:** (a) baseline; (b) add "avoid clichés" with examples; (c) language-specific tuning (English vs Korean)
> - **Compare:** cliché rate (manual coding on N=10 dialogues)

**Verified impl context:**
- Line 60: `system_prompt = f"""You are a professional screenwriter for photorealistic cinema.`
- Line 94: `system_with_tools = system_prompt + """` (tools appended)
- Line 103: `system_prompt=system_with_tools,` (used in LLM call)
- File length: 184 lines

**ARCHITECTURE reference:** §7 LLM ensemble + dialogue generation layer (Tier C only per brief table — dialogue happens during PERFORMANCE phase shot iteration, not Tier B single-shot)

**Tier:** C (dialogue is invoked during full-reel performance capture)

**Format reminder (from PR-STORY/PR-IMAGE/PR-MOTION filled cells):**
- Phase / class: Prompt class (cross-cuts PERFORMANCE / dialogue layer)
- Stage in pipeline: ARCHITECTURE §7 + impl ref
- Test tier: C
- Estimated cost: $0 — prompt evaluation is intrinsic to performance capture; this cell is a focused angle
- Wall-clock prediction: N/A — reuses upstream cell observation
- PREDICTION: Expected output shape (dialogue string structure: speaker + content?) + Expected content quality (era-appropriate, character-voice-consistent, no clichés) + Top 3 failure modes + Adjustment indicators

**Likely failure modes for director consideration (substrate, NOT authoritative):**
1. Cinematic clichés ("It's over, Anya. We both know it.") — root cause: persona persona-default
2. Language drift — Korean characters get English-shaped dialogue (subject-first SVO) when source/scene is Korean cultural context
3. Character voice collapse — all characters speak in same register; root cause: prompt may not enforce per-character voice differentiation

**Cross-reference cold-context verification command (already in brief §5.5):**
> "Read `domain/dialogue_writer.py:60`; verify dialogue system prompt + language adaptation per testplan §5 P8."

---

### PR-CONTINUITY → testplan P12

**Source quote (operator testplan §5 P12):**
> P12. Continuity prompt enhancement (`domain/continuity_engine.py:enhance_shot_prompt`)
> - **Current:** Deterministic assembly: raw + location + character + physics + motion + notes
> - **Predicted weakness:** Assembly order may matter for image gen (later text often weighted more)
> - **Tweak variants:** (a) baseline; (b) reorder fragments; (c) inject character anchor earlier
> - **Compare:** identity score variance

**Verified impl context (line 446 onward):**
- Line 446: `def enhance_shot_prompt(self, shot, scene, previous_shot=None, shot_index=0, approved_anchor_image=None)`
- Line 467: `prompt_parts.append(shot.get("prompt", ""))` (1. raw prompt)
- Line 472-474: location persistence (2. location)
- Line 478-490: character identity fragments with spatial position (left/center/right for ≥2-3 chars) (3. characters)
- Line 493-497: physics constraints (4. physics)
- Line 501-505: motion constraints from action continuity (5. motion)
- Line 507-509: `continuity_notes = shot.get("continuity_constraints", "")` + `prompt_parts.append(f"Continuity note: {continuity_notes}")` (6. notes)
- Line 513: `anchor_image = approved_anchor_image if approved_anchor_image and os.path.exists(approved_anchor_image) else None` — anchor is separate `continuity_config` output, NOT part of positive-prompt assembly

**ARCHITECTURE reference:** §8 continuity engine

**Tier:** B + C (continuity injection runs at every keyframe + motion phase; observable at both single-shot and full-reel scale)

**Format reminder:**
- Phase / class: Prompt class (cross-cuts P-KEYFRAME + P-MOTION phases at the `enhance_shot_prompt` injection point)
- Stage in pipeline: ARCHITECTURE §8 + impl `domain/continuity_engine.py:446 enhance_shot_prompt`
- Test tier: B + C
- Estimated cost: $0 — prompt assembly is intrinsic to P-KEYFRAME/P-MOTION; this cell is a focused angle
- Wall-clock prediction: N/A — reuses upstream cell observation
- PREDICTION: Expected output (continuity-enhanced prompt + continuity_config dict) + Expected content quality (location + character + physics + motion + notes all present when applicable; spatial positioning for ≥2 chars) + Top 3 failure modes + Adjustment indicators

**Likely failure modes for director consideration (substrate, NOT authoritative):**
1. Assembly-order weight effects — later prompt fragments (notes, motion) may dominate over earlier (raw shot intent); root cause: image gen attention bias to recent tokens
2. Character fragment overwhelming raw shot — when ≥3 chars in shot, character fragments dominate prompt token budget; root cause: no length cap on per-character fragments
3. Anchor / prompt conflict — `approved_anchor_image` references day-shot continuity but raw shot is night; root cause: anchor selection in `_resolve_previous_approved_keyframe` not scene-boundary-aware (already flagged in PR-IMAGE)

**Cross-reference (already in brief §5.5):**
> "Read `domain/continuity_engine.py:446 enhance_shot_prompt`; verify assembly order per testplan §5 P12."

---

### PR-STYLE-LLM → testplan P1

**Source quote (operator testplan §5 P1):**
> P1. Style Director system_prompt (`llm/style_director.py:62`)
> - **Current:** "world-class cinematographer and production designer" persona; outputs 6-rule JSON
> - **Predicted weakness:** 6-rule partition may be coarse; `sound_design_rules` might be generic
> - **Tweak variants:** (a) baseline; (b) add "be specific about color palette (named colors)" instruction; (c) include topic context in user_prompt
> - **Compare:** rule specificity (count of concrete nouns) before vs after tweak

**Verified impl context (line 62 onward):**
- Line 62: `system_prompt = f"""You are a world-class cinematographer and production designer.`
- Line 95: `system_with_tools = system_prompt + """` (tools appended for structured output)
- Line 107: `system_prompt=system_with_tools,` (used in LLM call)
- File length: 193 lines
- 6-key output schema is enforced via tools-appended prompt format (per filled PR-STORY pattern)

**ARCHITECTURE reference:** §7.1 style stage (first phase of pipeline)

**Tier:** B + C (style runs once at session/project entry; observable at single-call and full-reel scale)

**NOTE — partial coverage by P-STYLE:** brief table marks PR-STYLE-LLM as "STUB (covered partially by P-STYLE)". Director should consider whether this cell is a distinct angle (specifically the LLM-input prompt construction, not the output JSON validation which P-STYLE already covers) OR can be folded into P-STYLE's predictive harness. Operator recommendation: keep as distinct cell because P-STYLE is OUTPUT-focused (JSON schema, key presence, content quality) while PR-STYLE-LLM is INPUT-focused (does the prompt construction elicit specific palette / camera vocab / production-design specificity?).

**Format reminder:**
- Phase / class: Prompt class (cross-cuts P-STYLE phase; input side of LLM call)
- Stage in pipeline: ARCHITECTURE §7.1 + impl `llm/style_director.py:62`
- Test tier: B + C
- Estimated cost: $0 — observation intrinsic to P-STYLE
- Wall-clock prediction: N/A — reuses P-STYLE observation
- PREDICTION: Expected output (6-key JSON: color_palette / camera_style / lighting / production_design / mood / sound_design) + Expected content quality (named colors not abstract; specific camera lens classes; specific lighting setups) + Top 3 failure modes + Adjustment indicators

**Likely failure modes for director consideration (substrate, NOT authoritative):**
1. Generic palette ("warm" not "burnt sienna and ochre at sunset") — root cause: prompt doesn't enforce concrete-noun preference
2. `sound_design_rules` generic — root cause: prompt likely under-specifies; cinematographer persona may de-prioritize audio
3. Topic-context absence — user_prompt may not include scene/genre context; LLM produces generic-cinematic rules

**Cross-reference (already in brief §5.5):**
> "Read `llm/style_director.py:62`; verify 6-key output schema per testplan §5 P1."

---

### PR-CHIEFDIR → testplan P2 + P3 (dual-source)

**Source quotes (operator testplan §5 P2 + P3):**
> P2. Chief Director `ChiefDirector v2.0` (`llm/chief_director.py:130-206`)
> - **Current:** IDENTITY_FIREWALL HC1–HC8 + T1–T9 tripwires
> - **Predicted weakness:** HC1-HC8 may over-trigger on legitimate character variation (e.g., different outfit ≠ different character)
> - **Tweak variants:** (a) baseline; (b) relax HC1 wording on outfit variation; (c) add explicit "outfit changes do NOT count as identity violations" clarification
> - **Compare:** false-positive REJECTED rate on clean shots before vs after
>
> P3. Chief Director evaluate_take (`llm/chief_director.py:352`)
> - **Current:** RETRY/ACCEPT_LENIENT/FAIL trichotomy
> - **Predicted weakness:** ACCEPT_LENIENT may be over-used (lowering bar) or under-used (forcing FAIL on borderline takes)
> - **Tweak variants:** (a) baseline; (b) add explicit acceptance criteria for ACCEPT_LENIENT; (c) require quality_score floor for ACCEPT_LENIENT
> - **Compare:** distribution of decisions across 20+ takes pre vs post

**⚠️ P3 reference inaccuracy — see Verification notes §1.** Actual `evaluate_take`-shaped method is `diagnose_failure` (RETRY/ACCEPT_LENIENT/FAIL emitted ~lines 318-446). Validation pre-shot uses `validate_shot_prompts` at line 208. Director should treat P3 as referring to `diagnose_failure`, not `evaluate_take` (which doesn't exist).

**Verified impl context (validated by Rule #12 grep):**
- Line 27: `class ChiefDirector:`
- Line 130: `You are "ChiefDirector v2.0" — a strict metacognitive oversight engine...` (system prompt for validation pathway)
- Line 138: `HC1: You MUST output valid JSON. No markdown, no explanation, no conversational text.` (start of HC1-HC8 enumeration; T1-T9 follows)
- Line 208: `def validate_shot_prompts(self, shots: List[Dict], scene: Dict) -> Dict:` (pre-keyframe shot-prompt validation; uses lines 130-206 system prompt)
- Line 318: First `return {"decision": "RETRY", ...}` in diagnose_failure
- Line 352: `eval_prompt = json.dumps({...})` inside diagnose_failure DIAGNOSE_GENERATION_FAILURE pathway (NOT a method definition — testplan P3's "line 352" is inaccurate; actual method is `diagnose_failure`)
- Line 366: Second system prompt: `"You are ChiefDirector diagnosing a generation failure..."`
- Line 396: JSON schema: `'  "decision": "RETRY" | "ACCEPT_LENIENT" | "FAIL",\n'`
- Line 427: ACCEPT_LENIENT visible-skip log comment
- Line 446: Another `return {"decision": "RETRY", ...}` in diagnose_failure
- File length: 459 lines

**ARCHITECTURE reference:** §7 LLM ensemble + validation (Chief Director is post-decompose validation + post-take diagnosis)

**Tier:** B + C (P2 validates each shot prompt — runs B and C; P3 diagnoses per-take failures — runs B and C with take retries enabled)

**SPECIAL — DUAL-SOURCE CELL:** PR-CHIEFDIR is the only PR-* cell with TWO source P-sections (P2 + P3). Per the cycle-14 close director handoff §"What I would do next": "PR-CHIEFDIR → P2/P3". Director's authorship options:
- (a) Single PR-CHIEFDIR cell covering both validation prompt + diagnosis prompt as one prompt-class observation
- (b) Two sub-cells: PR-CHIEFDIR-VALIDATE (P2-sourced) + PR-CHIEFDIR-DIAGNOSE (P3-sourced)

Operator recommendation: (a) — single cell, two-paragraph PREDICTION addressing both prompts. The brief table shows only one PR-CHIEFDIR row; splitting would require table revision + may over-engineer for tier C / single execution pass.

**Format reminder:**
- Phase / class: Prompt class (cross-cuts P-CHIEFDIR phase + per-take diagnosis pathway during P-KEYFRAME/P-PERFORMANCE/P-MOTION)
- Stage in pipeline: ARCHITECTURE §7 + impl `llm/chief_director.py:130-206` (validation) + `llm/chief_director.py:diagnose_failure` (~318-446) (diagnosis)
- Test tier: B + C
- Estimated cost: $0 — prompt evaluation intrinsic to validation + diagnosis phases
- Wall-clock prediction: N/A — reuses upstream cells
- PREDICTION: Expected output (validation: APPROVED/MODIFIED/REJECTED + per-shot decisions; diagnosis: RETRY/ACCEPT_LENIENT/FAIL + mutation suggestion) + Expected content quality + Top 3 failure modes (cover both prompts) + Adjustment indicators

**Likely failure modes for director consideration (substrate, NOT authoritative):**
1. (P2) HC1-HC8 over-trigger — outfit / hair / lighting variation flagged as identity violation; root cause: HC phrasing may not distinguish costume vs face/build
2. (P3) ACCEPT_LENIENT over-use — borderline takes accepted at scale → quality dilution; root cause: no quality_score floor enforcement in prompt
3. (P3) FAIL under-use — broken takes get RETRY instead of FAIL → wasted budget; root cause: prompt may not enforce "if X failure mode, FAIL not RETRY" rule

**Cross-reference (already in brief §5.5):**
> "Read `llm/chief_director.py:130-206`; verify HC1-HC8 + T1-T9 phrasing per testplan §5 P2."

---

### PR-AUDIO-VIBE → testplan P9

**Source quote (operator testplan §5 P9):**
> P9. Music prompt `_build_music_prompt` (`audio/music.py:88`)
> - **Current:** Text prompt assembled from `music_vibe`, `video_pacing`, `story_tension`
> - **Predicted weakness:** Three-axis input may be too coarse for FAL Stable Audio
> - **Tweak variants:** (a) baseline; (b) add instrument-list hint; (c) add tempo-bpm hint
> - **Compare:** subjective fit + duration accuracy

**⚠️ P9 input axis claim inaccurate — see Verification notes §2.** Actual `_build_music_prompt(music_vibe: str)` takes ONE input (vibe key), produces detailed producer-grade prompt via dict lookup at lines 90-117 (e.g., `"suspense": "70bpm D minor, slow deep sub-bass drones, distant reversed piano, ticking clock polyrhythm, cinematic brass stabs, Hans Zimmer tension, dark ambient thriller score."`). NOT three-axis (`video_pacing` and `story_tension` are NOT inputs). Director should re-frame the predicted weakness around: (a) does the static vibe→prompt mapping miss scene-context that pacing/tension would convey; (b) is the producer-grade dict richness sufficient or does it over-constrain.

**Verified impl context (line 88 onward):**
- Line 88: `def _build_music_prompt(music_vibe: str) -> str:` — SINGLE parameter
- Line 90-117: Vibe→prompt dict (27 mood keys: suspense / thriller / horror / noir / dystopian / melancholic / romantic / bittersweet / grief / hopeful / epic / action / triumphant / chase / ethereal / dreamy / meditative / cosmic / cyberpunk / corporate / gritty / urban / uplifting / jazz_noir / classical / western)
- Line 120-121: Default fallback for unknown vibe: `"Cinematic ambient music, {music_vibe} mood, slow, atmospheric, film score quality, professional production."`
- Line 158: `prompt = _build_music_prompt(music_vibe)` (called from generate_suno_v5 path)
- Line 216-217: `def generate_bgm(music_vibe: str, ...)` (Suno + FAL routing)
- File length: 380 lines

**ARCHITECTURE reference:** §13 audio pipeline

**Tier:** B + C (BGM generation runs once per project; observable at single-call BGM probe (Tier B) and full-reel assembly (Tier C))

**Format reminder:**
- Phase / class: Prompt class (cross-cuts P-BGM phase; specifically the `_build_music_prompt` mapping)
- Stage in pipeline: ARCHITECTURE §13 + impl `audio/music.py:88 _build_music_prompt`
- Test tier: B + C
- Estimated cost: $0 — prompt observation intrinsic to P-BGM
- Wall-clock prediction: N/A — reuses P-BGM observation
- PREDICTION: Expected output (producer-grade text prompt string with BPM + key + instrumentation + reference) + Expected content quality (concrete instrumentation, BPM, named reference like "Hans Zimmer tension"; 27 known vibes have rich mappings; unknown vibes fall back to generic) + Top 3 failure modes + Adjustment indicators

**Likely failure modes for director consideration (substrate, NOT authoritative — re-framed away from incorrect three-axis claim):**
1. Vibe→prompt static mapping misses scene-context — pacing changes within a scene (slow start → fast climax) can't be conveyed by a single vibe key; root cause: dict-lookup design, no scene-aware composition
2. Unknown-vibe generic fallback (line 120-121) is much weaker than mapped vibes — if scene's vibe falls outside 27 keys, BGM quality degrades; root cause: no fuzzy-match or composition from neighboring vibes
3. 27 vibes may over-cluster around cinema/score — e.g., 7 are explicitly orchestra-leaning ("epic", "triumphant", "classical", etc.), few are electronic/contemporary; root cause: dict was hand-curated; gaps reflect curator taste

**Cross-reference (already in brief §5.5):**
> "Read `audio/music.py:88 _build_music_prompt`; verify vibe→prompt mapping per testplan §5 P9."

---

## Verification notes (operator-internal Rule #12 grep-the-writes findings)

Per Rule #12 brief-pattern reference verification (cycle-13 codification at `8ab0bbb`): operator-default to grep-verify any cited file:line or function-name reference BEFORE downstream consumption. The 5 PR-* STUBs reference 6 operator-testplan §5 P-sections (P1, P2, P3, P8, P9, P12). All 6 were grep-verified. **2 found inaccurate:**

### Finding A — Testplan §5 P3 references nonexistent `evaluate_take` method

**Cited:** `llm/chief_director.py:352` for "Chief Director evaluate_take" with RETRY/ACCEPT_LENIENT/FAIL trichotomy

**Actual:**
- Line 352 is `eval_prompt = json.dumps({...})` inside a method (NOT a method definition).
- `grep -n "def evaluate_take" llm/chief_director.py` returns NO matches.
- The method emitting RETRY/ACCEPT_LENIENT/FAIL is `diagnose_failure` (system prompt at line 366; JSON schema enumerating decisions at line 396; decision returns at lines 318, 446).
- Pre-shot validation method is `validate_shot_prompts` at line 208 (uses HC1-HC8 + T1-T9 system prompt from lines 130-206).

**Severity:** MINOR — testplan got the BEHAVIOR right (the prompt does emit RETRY/ACCEPT_LENIENT/FAIL trichotomy) but wrong METHOD NAME and LINE NUMBER. Director using this doc's PR-CHIEFDIR substrate has the correct refs.

**Disposition recommendation:** advisory; testplan revision optional. If shipped, operator can land a `docs(testplan): correct P3 reference — diagnose_failure not evaluate_take` commit (separate, ~5 LoC change in 1 file). Operator-default per Sh + brief-pattern reference scope. Director-side action: NONE; this doc's substrate is authoritative for PR-CHIEFDIR.

### Finding B — Testplan §5 P9 claims three-axis input not in impl

**Cited:** `_build_music_prompt` "Text prompt assembled from `music_vibe`, `video_pacing`, `story_tension`"

**Actual:**
- `def _build_music_prompt(music_vibe: str) -> str:` at line 88 — SINGLE parameter.
- No `video_pacing` or `story_tension` references anywhere in `audio/music.py` (verified via grep).
- Function uses static vibe→prompt dict lookup (lines 90-117; 27 keys) with default fallback (lines 120-121).
- The producer-grade prompts are richly detailed (BPM + key + instrumentation + reference) for the 27 mapped vibes; default fallback is much shorter.

**Severity:** IMPORTANT — testplan's "three-axis input" claim is structurally wrong; the predicted weakness ("Three-axis input may be too coarse") doesn't apply because there's no three-axis input. Director using this needs the RE-FRAMED failure modes from PR-AUDIO-VIBE substrate above (vibe→prompt static mapping, fallback weakness, vibe cluster bias).

**Disposition recommendation:** advisory; testplan revision recommended. If shipped, operator can land a `docs(testplan): correct P9 — _build_music_prompt is single-axis (music_vibe only)` commit (separate, ~15 LoC change for accurate current + weakness + tweak-variant re-framing). Operator-default per Sh. Director-side action: NONE; this doc's substrate is authoritative for PR-AUDIO-VIBE.

### Finding-class observation (Candidate #4-adjacent)

Findings A + B are Rule #12-violation shape (cited symbols don't grep-verify). They are **operator's own testplan errors**, NOT brief-pattern reference errors. Distinct from Candidate #4 N=1 (Lane V #12 OBS-1: brief cited `_mutate_shot` — director-authored brief affecting implementer dispatch). Findings A/B are testplan-authoring errors affecting cross-doc consumption.

**Not Candidate #4 N=2 evidence** — different layer (substrate-doc authoring vs dispatch-time brief reference); different consumer (cross-doc cell-fill vs implementer subagent). Could be a NEW N=1 candidate (Candidate #9?) if a second instance emerges at the substrate-doc layer in cycle-15+. **Not filing as candidate this cycle** — single instance + clean operator-side self-fix path + low operational impact (this doc supplies corrected refs to director).

---

## Recommendations for director's next session

1. **Use this doc's verified file:lines, not the testplan's cites.** Specifically PR-CHIEFDIR P3 and PR-AUDIO-VIBE P9 — testplan has inaccuracies; this doc has ground truth.

2. **For PR-CHIEFDIR: prefer single-cell composition (option a from §"PR-CHIEFDIR" above)** unless tier C execution surfaces strong reason to split validation vs diagnosis observation.

3. **For PR-STYLE-LLM: keep as distinct cell from P-STYLE** (different scope: input prompt construction vs output JSON validation). Operator's recommendation, director's call.

4. **PR-AUDIO-VIBE PREDICTION should re-frame failure modes** away from the incorrect three-axis premise. This doc's "re-framed failure modes" subsection provides starting points.

5. **Cell-fill order suggestion:** PR-STYLE-LLM (shortest; cleanest P-section source) → PR-DIALOGUE (clean P-section) → PR-CONTINUITY (clean; longer impl context) → PR-AUDIO-VIBE (requires re-frame from inaccurate testplan claim) → PR-CHIEFDIR (dual-source; most complex). Front-load wins, end with most complex.

6. **Wall-clock estimate:** ~10-15 min per cell × 5 cells = ~50-75 min total director time for PR-* fills (assumes director uses this doc's substrate; without it, ~25-30 min per cell + testplan re-verification = ~2-2.5 hours).

7. **Optional follow-up:** ship `docs(testplan): correct P3 evaluate_take + P9 three-axis references` as a small operator-default commit. Low priority — this pre-staging doc supplies corrected refs to director. Operator can land in cycle-15+ if appropriate window.

---

## Sign-off

Operator-seat cycle-15 entry adjacent-useful work. Lane C-style read-only survey of operator testplan §5 P1-P14 + filled PR-* cells in brief §5.3 (PR-STORY/PR-IMAGE/PR-MOTION); Rule #12 grep-verification of all 6 cited file:line refs; cross-reference substrate drafted for 5 PR-* STUB cells (PR-DIALOGUE / PR-CONTINUITY / PR-STYLE-LLM / PR-CHIEFDIR / PR-AUDIO-VIBE); 2 testplan inaccuracies surfaced (P3 evaluate_take nonexistent; P9 three-axis claim wrong) with disposition recommendations.

**No commits or pushes other than this doc itself.** No PR-* cells authored (director-default per Sh + brief is strategic-default canonical doc). No cross-seat mailbox events (this is pre-staging substrate, not active coordination). Future operator-self-fix option (testplan revision) noted but deferred to discretion.

**Director's next session pickup:** read this doc + testplan §5 + brief §5.3 filled cells + ARCHITECTURE §7/§8/§13 (for ref). Director can plausibly fill all 5 PR-* cells in ~1 session using this doc's substrate.

*Pre-staging at HEAD `d64cba7` (cycle-14 operator transplant). Branch 0 ahead of `origin/main` pre-this-commit. Per the cycle-14 close handoff §"Adjacent-useful work when you can't claim the loop": "Pre-locate fixes ... draft prompts ... validate type shapes ... prepare closing reports." This doc is the "validate type shapes" + "prepare closing reports" combination shape — substrate for director's next-session fill-then-ship work, NOT replacing director's authorship.*
