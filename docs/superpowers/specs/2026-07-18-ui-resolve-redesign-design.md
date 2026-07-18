# Cinema Tool — Resolve-style UI Redesign (Design Spec)

> Status: **approved design direction** (2026-07-18). Blueprint for implementation.
> Prereq: land AFTER the Google-first overhaul + pod/dialogue exploration (per user:
> "adjust the UI after setup is done"). Companion mock: `scratchpad/ui_mockup_v3.html`.

**Goal:** Replace today's four bespoke, "editorial"-styled mode-screens with **one
Resolve-style shell** — dark, dense, practical, page-navigated — whose controls
**faithfully reflect the current pipeline**, and which **labels every option that
requires the RunPod pod**.

**Architecture:** A single persistent shell (top bar + bottom page-bar + status) with a
**swappable center**. The four surfaces become four **pages** — `Setup · Edit · Run ·
Capability` — selected from a Resolve-style bottom bar. Chrome stays put; only the
working area changes. Theme is a small set of CSS variables (no per-component color).

**Tech stack:** Existing — React 19 + Vite + TypeScript + Tailwind (`web/`). No new deps.
Reuse the existing functional panels and hooks (`usePipelineState`, `useSSE`); the redesign
is structural + stylistic, not a rewrite of data flow.

---

## Global Constraints (bind every task)

- **Design tokens only.** All color/spacing/type flow from CSS variables (see Design
  System). No hard-coded hex in components; no `stageColors`/editorial token sprawl.
- **Accent = indigo** `--acc:#7c83e0`, `--acc-dim:#333a66`. Swapping the accent (or adding
  a light theme later) must remain a one-file token edit.
- **Practical over stylistic.** System font, 11–13px, tight rows, uppercase micro-labels,
  tabular numerals. NO Fraunces display serifs, NO "NOW SHOWING" marquee, NO `Eyebrow`
  kickers, NO magazine chrome.
- **Color = meaning, not decoration:** `--ok` green, `--warn` amber, `--fail` red,
  `--pri` green (primary/engaged), `--pod` amber (pod-gated), `--acc` indigo (selection).
- **Truthful controls.** Every exposed model/option/default must match current pipeline
  code — verify the write-path, never trust an old label.
- **Pod labeling is mandatory** on every option (see Pod-Gating).
- **Preserve data flow.** SSE wiring, project-mutate flows, and the sticky
  `BUDGET_EXCEEDED` halt (owned by `App.tsx`) must survive the restructure unchanged.

---

## Design System (new: `web/src/theme/tokens.css` + Tailwind token map)

| Token | Value | Use |
|---|---|---|
| `--bg / --gutter / --panel / --head` | `#141417 / #101013 / #1c1c20 / #25252b` | surfaces |
| `--line` | `#2e2e35` | borders |
| `--tx / --mut / --dim` | `#d5d5da / #8a8a93 / #5c5c65` | text tiers |
| `--acc / --acc-dim` | `#7c83e0 / #333a66` | selection, active tab, toggle-on, primary button |
| `--pri / --pri-bg` | `#67b98a / #1e3a2c` | primary/engaged badge, ok meter |
| `--pod / --pod-bg` | `#d3974a / #3a2c19` | pod-required badge |
| `--ok / --warn / --fail` | `#5aa469 / #c9a24b / #c05a52` | status dots |

Shared primitives (`web/src/components/ui/`): `Badge` (`pri`/`pod`/`cloud` variants),
`Toggle`, `StatusDot`, `Meter`, `Section` (collapsible inspector section), `SelectPill`.
These replace ad-hoc styling across panels. **Delete** `Eyebrow.tsx`, `lib/stageColors.ts`,
and the editorial token block in `tailwind.config.js`.

---

## Shell + Navigation (new: `web/src/components/AppShell.tsx`)

Replaces the `mode`-switch in `App.tsx` (which currently renders `EditorialShell` /
`PipelineLayout` / `DirectorsConsole` / `CapabilityConsole` as separate full screens).

- **Top bar (38px):** `‹ Projects` · project name/reel · act pill · spacer · cost estimate
  (`est. $X / cap $Y`) · credential pills (`ADC ✓ · fal ✓`) · settings gear.
- **Center:** the active page (one of four `<PageView>`s; only the active one mounts-hot,
  others keep state via the existing hooks).
- **Bottom page-bar (52px):** `runstat` (left) · centered page tabs
  `◧ Setup · ✂ Edit · ▷ Run · ▤ Capability` · `▶ Generate` (right).
- **Navigation:** (1) page-bar tab click → switch page; (2) contextual — double-click a
  scene (Setup tree or cue-sheet) → open Edit focused on that scene. A `usePage()` context
  holds `{page, focusScene}`.
- Pod/Cloud/Primary **legend** pinned above the page-bar.

---

## Page 1 — Setup  (replaces `EditorialShell`)

3-column inspector layout:
- **Left — Project tree:** Characters / Locations / Objects / Scenes (counts, thumbnails,
  `＋` add). Reuses `CharacterPanel`, `LocationPanel`, `ObjectPanel`, `ScenePanel` logic,
  restyled into the tree.
- **Center — Scenes cue sheet:** dense table (#, scene, location, shots, primary API,
  status). Double-click → Edit.
- **Right — Settings inspector:** collapsible `Section`s, reconciled (see Reconciliation):
  Video engines (cascade order), Image, Identity, Voice, Budget. Replaces the 11-section
  `settings/` sprawl; **`MaxQualityTierSection` is deleted**, `ApiEnginesSection` rebuilt.

## Page 2 — Edit  (NEW — the shot workspace; consolidates scattered editing)

Pulls per-shot editing out of the mid-run pipeline view into a first-class page.
- **Left:** current scene's shots as a bin (status per shot).
- **Center:** viewer (selected shot's keyframe/take) + transport + **timeline** where
  *scenes → shots* are clips on a track (Resolve Edit-page pattern).
- **Right — shot inspector:** Prompt (positive/negative), Dialogue (line + voice + pace),
  Shot (type / primary API / duration), Identity (PuLID weight / threshold + `⚙ Pod`
  ComfyUI-keyframe toggle). Reuses `PromptEditor` logic.

## Page 3 — Run  (merges `PipelineLayout` + `DirectorsConsole`)

Live generation monitor **and** take-review on one page:
- **Left:** shot queue with live status (approved / running / queued / failed-retry).
- **Center:** stage rail (Decompose▸Plan▸Keyframe▸Motion▸Post▸Review▸Done) + hero viewer +
  takes filmstrip ("pick the keeper"). Reuses `PipelineStageRail`, `HeroShot`, `TakeStrip`.
- **Right:** budget meter, per-take identity/lip-sync scores, Approve/Reject/Iterate,
  director notes. Reuses `ShotApprovalControls`, `Notes`, `Telemetry`.
- **Consolidate the duplicated `Filmstrip`** (exists in both `pipeline/` and `console/`)
  into one shared component.

## Page 4 — Capability  (restyle `CapabilityConsole`)

Serves the PROGRAM-MANUAL "operate to full capability" intent:
- Overall score (e.g. `72/100`) + "N of M systems engaged".
- Capability cards with meters (Identity lock, Multi-API cascade, Dialogue/voice,
  Continuity, Lip-sync, Post). Lip-sync card surfaces "gate needs recal".
- **"Available — not engaged"** row (ComfyUI max keyframe `⚙ Pod off`, second-char LoRA,
  Foley) — what the project could turn on.

---

## Pod-Gating (the load-bearing label requirement)

Each option carries exactly one badge: **`⚙ Pod`** (needs RunPod running) or **`Cloud`**
(runs on an API). Source of truth = pipeline code, not old labels.

- **Pod-gated:** ComfyUI/FLUX+PuLID image path (arc-gate fallback + max keyframe),
  per-character LoRA training, any ComfyUI-graph feature.
- **Cloud:** all Google (Omni Flash, Veo, Nano Banana), fal (Kling, Seedance, LTX,
  OmniHuman, Aurora), ElevenLabs.
- A pod-gated option shows a disabled/"start pod" affordance when the pod is stopped
  (read pod status if a health endpoint exists; otherwise a manual "pod running" toggle).

---

## Reconciliation (staleness sweep — fold in here, not a separate pass)

- **Video engines → Google-first order:** `Omni Flash (Primary) → Veo 3.1 → Kling 3.0 →
  Seedance 2.0 → LTX`. **Remove Sora 2, Runway Gen-4, Hedra** from the UI.
- **Image → Nano Banana `Primary`** (`gemini-2.5-flash-image`) + ComfyUI fallback (`⚙ Pod`).
  Default backend = `gemini_multiref`, not pod/max.
- **Delete the Max-Quality tier** control (`MaxQualityTierSection`) — retired.
- **Voice:** ElevenLabs v3, defaults Eric (male) / Lily (female). **Pace control =
  target-wpm via `atempo` post-process, NOT a `speed` field** (eleven_v3 ignores `speed`).
- **Lip-sync fix (deferred here from the dialogue session):** drop the miswired Kling
  overlay endpoint (`fal-ai/kling-video/lipsync/audio-to-video`, needs `video_url`) from
  the still→talking-head GENERATION cascade in `lip_sync.py:~860` → OmniHuman becomes
  correct ATTEMPT 0. Surface lip-sync engine status honestly in the Run page + Capability.

---

## Error Handling

- Preserve the sticky `BUDGET_EXCEEDED` halt banner (owned by the shell, survives page
  switches) and the `ErrorBoundary` wrapping.
- Per-page empty/error/loading states via the shared `ui/` `ErrorState`/`LoadingState`.
- Pod-gated action attempted while pod is stopped → inline "start the pod" notice, never a
  silent failure.

## Testing

- **Component tests** (Vitest + Testing Library) for the shared `ui/` primitives (Badge
  variants, Toggle, Meter) and the page-bar navigation (tab switch + scene double-click).
- **Visual smoke:** each page renders with a mocked project + config; the pod-badge legend
  and Google-first cascade order assert against the reconciliation list.
- Reuse existing `usePipelineState`/SSE tests unchanged (data flow is preserved).

## Out of Scope / Phasing

- Light theme (tokens make it a later one-file add).
- Backend API changes beyond what reconciliation requires (the config/settings the UI
  reads must expose the reconciled engine list + pod-status).
- Implementation sequencing (shell → tokens → pages → reconciliation) belongs in the
  implementation plan (writing-plans), not this spec.
