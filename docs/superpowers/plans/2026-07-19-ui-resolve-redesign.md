# Cinema Tool — Resolve-style UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the four bespoke "editorial"-styled mode-screens with one dark/practical DaVinci-Resolve-style shell (four pages on a bottom page-bar) whose controls faithfully reflect the current Google-first pipeline and label every pod-gated option.

**Architecture:** A single persistent `AppShell` (top bar + swappable center + bottom page-bar) driven by a `usePage()` context replaces the `mode`-switch in `App.tsx`. The four surfaces become four `<PageView>`s (Setup · Edit · Run · Capability). All existing data flow (`usePipelineState`, `useSSE`, the `App.tsx`-owned `budgetHalt`) is preserved; the redesign is structural + stylistic + a truthful reconciliation of the engine/option controls — NOT a rewrite of pipeline logic.

**Tech Stack:** React 19 + Vite 6 + TypeScript 5.7 + Tailwind 3.4 (`web/`). Adds Vitest + @testing-library/react as devDeps (currently absent). No other new runtime deps.

## Global Constraints (bind every task — copied from the spec)

- **Design tokens only.** All color/spacing/type flow from CSS variables / Tailwind token classes. No hard-coded hex in components.
- **Accent = indigo** `--acc:#7c83e0`, `--acc-dim:#333a66`. Accent swap must remain a one-file token edit.
- **Practical over stylistic.** System font, 11–13px, tight rows, uppercase micro-labels, tabular numerals. NO Fraunces display serifs, NO "NOW SHOWING" marquee, NO `Eyebrow` kickers, NO magazine chrome.
- **Color = meaning:** `--ok` green, `--warn` amber, `--fail` red, `--pri` green (primary/engaged), `--pod` amber (pod-gated), `--acc` indigo (selection).
- **Truthful controls.** Every exposed engine/option/default must match current pipeline code — verify the write-path, never trust an old label. The engine list is SERVER-DRIVEN from `GET /api/config` `api_registry`, ordered by `DEFAULT_VIDEO_CASCADE`.
- **Pod labeling is mandatory** on every engine/option. Source of truth = `billing_providers` from `/api/config` (`RUNPOD_GPU` bucket ⇒ `⚙ Pod`; everything else ⇒ `Cloud`) plus the two non-engine pod features (per-character LoRA training, ComfyUI keyframe backend).
- **Preserve data flow.** `usePipelineState` public API is frozen (see Task 5 for the exact frozen name list). SSE wiring, project-mutate flows, and the sticky `BUDGET_EXCEEDED` halt (owned by `App.tsx`, must survive page switches) are unchanged in behavior.
- **`update(key,value)` settings contract** stays: `PUT /api/projects/:id { global_settings: {...s, [key]: value} }` then `onRefresh()`.

---

## File Structure

**New files**
- `web/src/theme/tokens.css` — the indigo CSS-variable token set (imported by `index.css`).
- `web/src/components/ui/Badge.tsx` — `pri | pod | cloud | ok | warn | fail | neutral` variants.
- `web/src/components/ui/Toggle.tsx` — on/off switch (replaces per-section inline toggles).
- `web/src/components/ui/StatusDot.tsx` — `ok | warn | fail | idle | run` dot.
- `web/src/components/ui/Meter.tsx` — labeled horizontal meter (0–1 or 0–100).
- `web/src/components/ui/SelectPill.tsx` — compact mono `<select>` styled as a pill.
- `web/src/components/ui/Section.tsx` — collapsible inspector section (generalizes `settings/SettingsSection`).
- `web/src/lib/podGating.ts` — `isPodGated(engineKey, billingProviders)` + the pod-feature constant list.
- `web/src/lib/engines.ts` — `videoEngines(config)`: derive the ordered, reconciled, live video-engine list from `config`.
- `web/src/context/PageContext.tsx` — `usePage()` `{page, setPage, focusScene, setFocusScene}`.
- `web/src/components/AppShell.tsx` — the unified shell (top bar + center router + page-bar + legend).
- `web/src/components/pages/SetupPage.tsx`, `EditPage.tsx`, `RunPage.tsx`, `CapabilityPage.tsx`.
- `web/src/components/setup/ProjectTree.tsx`, `SceneCueSheet.tsx`, `SettingsInspector.tsx`.
- `web/src/components/setup/inspector/{VideoSection,ImageSection,IdentitySection,VoiceSection,BudgetSection}.tsx`.
- `web/src/components/edit/{ShotBin,ShotViewer,Timeline,ShotInspector}.tsx`.
- `web/src/components/shared/Filmstrip.tsx` — the ONE canonical filmstrip (merges pipeline/ + console/).
- Test files colocated as `*.test.tsx` under `web/src/**`.

**Modified**
- `web/package.json`, `web/vite.config.ts` (Vitest), `web/tailwind.config.js` (indigo namespace), `web/src/index.css` (token-driven hex), `web/src/App.tsx` (mount `AppShell`), `web/src/components/ui/index.ts` (barrel).
- Restyled in place (logic preserved): `CharacterPanel`, `LocationPanel`, `ObjectPanel`, `ScenePanel`, `GenerationPanel`, `PreviewPanel`, `BudgetHaltBanner`, `Button`, `ErrorState`, `LoadingState`, `ErrorBoundary`, `PipelineStageRail`, `PromptEditor`, `ShotApprovalControls`, `ShotRow`, `HeroShot`, `TakeStrip`, `Telemetry`, `Notes`, `Monitor`, `CapabilityConsole`.
- Backend (reconciliation): `lip_sync.py` (Kling cascade fix). `web_server.py` `/api/config` already returns `billing_providers`/`api_registry` — verify only.
- `web/src/types/project.ts` — add `objects: ProductObject[]` to `Project` (removes the `as any` casts).

**Deleted**
- `web/src/components/ui/Eyebrow.tsx` (migrate 4 importers first).
- `web/src/lib/stageColors.ts` (migrate 2 importers first).
- `web/src/components/settings/MaxQualityTierSection.tsx` (+ simplify `isMaxTier` branches).
- `web/src/components/EditorialShell.tsx`, `web/src/components/pipeline/PipelineLayout.tsx` chrome, `web/src/components/DirectorsConsole.tsx`, `web/src/components/console/CapabilityConsole.tsx`'s outer shell — **only after** their reusable children are wired into the new pages. (Delete the old `settings/SettingsPanel.tsx` flat stack once `SettingsInspector` replaces it.)

> **Sequencing note:** Tasks 1–4 are foundation (no visible change). Task 5 makes the shell live (App renders `AppShell`; pages start as stubs that mount the existing screens so nothing breaks). Tasks 6–11 flesh out each page and fold in reconciliation. Task 12 is the backend lip-sync fix. Task 13 is cleanup + build-green. Each task ends buildable (`npm run build` passes) and, where a test exists, green.

---

### Task 1: Test infrastructure (Vitest + Testing Library)

**Files:**
- Modify: `web/package.json`, `web/vite.config.ts`
- Create: `web/src/test/setup.ts`, `web/src/test/smoke.test.tsx`

**Interfaces:**
- Produces: `npm --prefix web run test` runs Vitest in jsdom with `@testing-library/jest-dom` matchers; the pattern every later task's tests rely on.

- [ ] **Step 1: Add devDeps** — in `web/package.json` devDependencies add: `vitest ^2`, `@testing-library/react ^16`, `@testing-library/jest-dom ^6`, `@testing-library/user-event ^14`, `jsdom ^25`. Add script `"test": "vitest run"` and `"test:watch": "vitest"`. Run `npm --prefix web install`.
- [ ] **Step 2: Configure Vitest** — in `web/vite.config.ts` add to the config object: `test: { environment: 'jsdom', globals: true, setupFiles: ['./src/test/setup.ts'], css: false }`. Add the vitest triple-slash types ref at top: `/// <reference types="vitest/config" />`.
- [ ] **Step 3: Setup file** — `web/src/test/setup.ts`: `import '@testing-library/jest-dom'`.
- [ ] **Step 4: Smoke test (write failing)** — `web/src/test/smoke.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
describe('test harness', () => {
  it('renders and matches', () => {
    render(<div>cinemaker-test-ok</div>)
    expect(screen.getByText('cinemaker-test-ok')).toBeInTheDocument()
  })
})
```
- [ ] **Step 5: Run** — `npm --prefix web run test` → PASS (1 file, 1 test). If jest-dom matcher `toBeInTheDocument` is unknown, the setup file isn't wired — fix Step 2/3.
- [ ] **Step 6: Commit** — `git add web/package.json web/package-lock.json web/vite.config.ts web/src/test && git commit -m "test(web): add Vitest + Testing Library harness"`.

---

### Task 2: Design tokens (indigo namespace)

**Files:**
- Create: `web/src/theme/tokens.css`
- Modify: `web/tailwind.config.js`, `web/src/index.css`

**Interfaces:**
- Produces: CSS variables `--bg --gutter --panel --head --line --tx --mut --dim --acc --acc-dim --pri --pri-bg --pod --pod-bg --ok --warn --fail` and Tailwind color classes `bg-app / bg-gutter / bg-panel / bg-head / border-line / text-tx / text-mut / text-dim / *-acc / *-pri / *-pod / *-ok / *-warn / *-fail`.

- [ ] **Step 1: Token file** — `web/src/theme/tokens.css` under `:root`, exact values from the spec Design System table:
```css
:root{
  --bg:#141417; --gutter:#101013; --panel:#1c1c20; --head:#25252b; --line:#2e2e35;
  --tx:#d5d5da; --mut:#8a8a93; --dim:#5c5c65;
  --acc:#7c83e0; --acc-dim:#333a66;
  --pri:#67b98a; --pri-bg:#1e3a2c;
  --pod:#d3974a; --pod-bg:#3a2c19;
  --ok:#5aa469; --warn:#c9a24b; --fail:#c05a52;
}
```
- [ ] **Step 2: Tailwind token map** — in `web/tailwind.config.js` `theme.extend.colors` add a THIRD namespace mapping to the vars (do NOT delete `editorial`/`console` yet — Task 13 prunes them after all consumers migrate):
```js
app:'var(--bg)', gutter:'var(--gutter)', panel:'var(--panel)', head:'var(--head)', line:'var(--line)',
tx:'var(--tx)', mut:'var(--mut)', dim:'var(--dim)',
acc:'var(--acc)', 'acc-dim':'var(--acc-dim)', pri:'var(--pri)', 'pri-bg':'var(--pri-bg)',
pod:'var(--pod)', 'pod-bg':'var(--pod-bg)', ok:'var(--ok)', warn:'var(--warn)', fail:'var(--fail)',
```
- [ ] **Step 3: Import + neutralize globals** — at the very top of `web/src/index.css` add `@import './theme/tokens.css';`. Change the hardcoded body background `#0a0a0a`→`var(--gutter)`, body color `#f0ebe1`→`var(--tx)`, `::selection` bg `#bf3737`→`var(--acc)`, scrollbar thumb `#2a2a2a`→`var(--line)` / `#d4a85a`→`var(--acc)`, focus outline `#d4a85a`→`var(--acc)`. Keep the film-grain/vignette utilities for now (Task 13 decides removal).
- [ ] **Step 4: Verify build** — `npm --prefix web run build` → succeeds (tsc + vite). No test needed (pure CSS/config).
- [ ] **Step 5: Commit** — `git add web/src/theme web/tailwind.config.js web/src/index.css && git commit -m "feat(ui): indigo design tokens (add alongside editorial/console)"`.

---

### Task 3: Shared `ui/` primitives

**Files:**
- Create: `web/src/components/ui/{Badge,Toggle,StatusDot,Meter,SelectPill,Section}.tsx` + their `*.test.tsx`
- Modify: `web/src/components/ui/index.ts`

**Interfaces:**
- Produces (exact signatures — later tasks consume these verbatim):
  - `Badge({variant, children, className?})` where `variant: 'pri'|'pod'|'cloud'|'ok'|'warn'|'fail'|'neutral'`. `pod` renders a leading `⚙` and label defaults to children (usually "Pod"). Class per variant uses the token colors (`pri`→`text-pri bg-pri-bg`, `pod`→`text-pod bg-pod-bg`, `cloud`→`text-mut bg-head`, etc.).
  - `Toggle({checked, onChange, disabled?, 'aria-label': string})` → 30×16 pill; on = `bg-acc-dim border-acc`.
  - `StatusDot({status})` where `status: 'ok'|'warn'|'fail'|'idle'|'run'` → 7px dot (`ok`→`bg-ok`, `run`→`bg-acc`, `idle`→`bg-dim`…).
  - `Meter({value, max?=1, tone?='acc', label?, right?})` → labeled bar; fill width `value/max*100%`, fill `bg-{tone}`.
  - `SelectPill({value, onChange, options, 'aria-label'})` where `options: {value:string,label:string}[]` or `string[]`.
  - `Section({title, children, defaultOpen?=true, right?})` → collapsible; header is uppercase 10px `text-mut`, chevron, optional `right` slot.

- [ ] **Step 1: Write failing tests** (`Badge.test.tsx`, `Toggle.test.tsx`, `Section.test.tsx`):
```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { Badge } from './Badge'; import { Toggle } from './Toggle'; import { Section } from './Section'

describe('Badge', () => {
  it('pod variant shows gear + pod token class', () => {
    const { container } = render(<Badge variant="pod">Pod</Badge>)
    expect(screen.getByText(/Pod/)).toBeInTheDocument()
    expect(container.firstChild).toHaveClass('text-pod')
  })
})
describe('Toggle', () => {
  it('fires onChange with negated value', async () => {
    const on = vi.fn(); render(<Toggle checked={false} onChange={on} aria-label="x" />)
    await userEvent.click(screen.getByRole('switch')); expect(on).toHaveBeenCalledWith(true)
  })
})
describe('Section', () => {
  it('collapses on header click', async () => {
    render(<Section title="Video"><p>body</p></Section>)
    expect(screen.getByText('body')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: /Video/i }))
    expect(screen.queryByText('body')).toBeNull()
  })
})
```
- [ ] **Step 2: Run → FAIL** (`npm --prefix web run test` → modules not found).
- [ ] **Step 3: Implement the 6 primitives** using only token classes. `Toggle` root is `<button role="switch" aria-checked={checked} aria-label={...}>`; `Section` header is a `<button>` toggling local `open` state and conditionally rendering children. Keep each file focused (<60 lines).
- [ ] **Step 4: Barrel** — add the 6 exports to `web/src/components/ui/index.ts` (leave `Eyebrow` for now; Task 4 removes it).
- [ ] **Step 5: Run → PASS.**
- [ ] **Step 6: Commit** — `git add web/src/components/ui && git commit -m "feat(ui): Badge/Toggle/StatusDot/Meter/SelectPill/Section primitives"`.

---

### Task 4: Delete `Eyebrow` + `stageColors` (migrate importers first)

**Files:**
- Modify: `web/src/components/ui/{ErrorState,LoadingState}.tsx`, `web/src/components/EditorialShell.tsx` (temporary — replaced in Task 6, but must compile now), `web/src/components/settings/SettingsSection.tsx`, `web/src/components/ui/index.ts`, `web/src/components/GenerationPanel.tsx`, `web/src/components/console/Notes.tsx`
- Delete: `web/src/components/ui/Eyebrow.tsx`, `web/src/lib/stageColors.ts`

**Interfaces:**
- Consumes: nothing new. Produces: a `microLabel` className constant to replace `Eyebrow`'s styling and a token-based stage-tone helper to replace `stageColors`.

- [ ] **Step 1:** Add `export const MICRO_LABEL = 'font-mono text-[10px] uppercase tracking-[0.09em] text-mut'` to `web/src/components/ui/index.ts`. Replace each `<Eyebrow …>X</Eyebrow>` in `ErrorState.tsx`, `LoadingState.tsx`, `EditorialShell.tsx`, `settings/SettingsSection.tsx` with `<span className={MICRO_LABEL}>X</span>` (adjust tone: error labels use `text-fail` instead of `text-mut`). Remove the `Eyebrow` import from each and from `index.ts`.
- [ ] **Step 2:** Delete `web/src/components/ui/Eyebrow.tsx`.
- [ ] **Step 3:** Add `web/src/lib/stageTone.ts` exporting `stageTone(stage: string): string` returning a token text-color class (`DONE|COMPLETE|VALIDATED`→`text-ok`; `ERROR|IDENTITY_FAIL|SHOT_FAILED|CANCELLED`→`text-fail`; `RETRY|WARNING|PAUSED`→`text-warn`; default→`text-mut`). Replace `stageColors`/`consoleStageColors` lookups in `GenerationPanel.tsx` (also drop its stale inline dup `stageColors`) and `console/Notes.tsx` with `stageTone(stage)`. Delete `web/src/lib/stageColors.ts`.
- [ ] **Step 4: Test** — `web/src/lib/stageTone.test.ts`: assert `stageTone('DONE')==='text-ok'`, `stageTone('ERROR')==='text-fail'`, `stageTone('ZZZ')==='text-mut'`.
- [ ] **Step 5: Verify** — `npm --prefix web run test` PASS and `npm --prefix web run build` succeeds (proves no dangling `Eyebrow`/`stageColors` imports).
- [ ] **Step 6: Commit** — `git add -A web/src && git commit -m "refactor(ui): remove Eyebrow + stageColors, migrate importers to tokens"`.

---

### Task 5: `usePage` context + `AppShell` (stub pages) + wire `App.tsx`

**Files:**
- Create: `web/src/context/PageContext.tsx`, `web/src/components/AppShell.tsx`, `web/src/components/pages/{SetupPage,EditPage,RunPage,CapabilityPage}.tsx`
- Modify: `web/src/App.tsx`
- Create test: `web/src/components/AppShell.test.tsx`

**Interfaces:**
- Produces: `type Page = 'setup'|'edit'|'run'|'capability'`; `usePage(): {page, setPage, focusScene, setFocusScene}`; `<PageProvider>`. `AppShell` props = **exactly the current `EditorialShell` prop set** (so `App.tsx` passes the same object): `{project, config, events, latest, isStreaming, generating, onBackToProjects, onGenerate, onCancel, onRefreshProject, onOpenConsole?, onOpenCapability?, apiBase, budgetHalt?, onDismissBudgetHalt?}` plus the pipeline callbacks currently passed to `PipelineLayout` (thread them through so the Run page can use them). 
- **FROZEN — `usePipelineState` return names `App.tsx` must keep destructuring:** `events, latest, isStreaming, start, stop, stages, activeStage, shotStates, directorReview, processEvent, isPaused, failedShots, pause, resume, approveShotPlan, rejectShotPlan, generateKeyframe, approveKeyframe, approvePerformance, generateMotion, approveFinal, regenerateShot, restartShot, correctShot, diagnoseShot, proceedToAssembly, iterateTake, approveScreening, reassembleProject`. Do not change the hook.

- [ ] **Step 1: PageContext** — `PageProvider` holds `page` (default `'setup'`) + `focusScene: string|null`. `handleGenerate` should still `setPage('run')` (see Step 4). Export `usePage`.
- [ ] **Step 2: AppShell** — build the shell chrome only, mounting stub pages:
  - Top bar (38px, `bg-head border-b border-line`): `‹ Projects` (calls `onBackToProjects`), project name + `Reel {id.slice(0,4).toUpperCase()}`, spacer, cost estimate text, credential pills, gear. **Render `<BudgetHaltBanner event={budgetHalt} onDismiss={onDismissBudgetHalt}/>` here when `budgetHalt` is set** (this preserves the App-owned sticky-halt requirement across page switches — the banner now lives in the always-mounted shell, satisfying the dual-mount rule that previously needed it in both EditorialShell and PipelineLayout).
  - Center: `switch(page)` → `<SetupPage/> | <EditPage/> | <RunPage/> | <CapabilityPage/>`, each wrapped in `<ErrorBoundary>`. Pass every page the props it needs (all four get `project, config, apiBase, onRefreshProject`; Run/Edit also get the pipeline state + callbacks).
  - Bottom page-bar (52px): left `runstat` (`<StatusDot/>` + "idle · N/M shots"), centered tabs `◧ Setup · ✂ Edit · ▷ Run · ▤ Capability` (active = `bg-acc-dim text-white`), right `▶ Generate` button (`onGenerate`). Pinned legend row above it: `Cloud` / `⚙ Pod requires the pod` / `Primary` using `<Badge/>`.
- [ ] **Step 3: Stub pages** — to keep behavior intact while later tasks flesh them out, each stub RENDERS THE EXISTING SCREEN: `SetupPage` renders the current 3-col workshop grid (the six panels, mounted with their exact props from the inventory: `CharacterPanel/LocationPanel/ObjectPanel {project,config,onRefresh}`, `ScenePanel {project,config,onRefresh}`, `SettingsPanel {project,config,onRefresh}`, `GenerationPanel {project,events,latest,isGenerating}`, `PreviewPanel {project}`); `RunPage` renders the existing `PipelineLayout` with its callbacks; `EditPage`/`CapabilityPage` render a `LoadingState` placeholder (Capability stub may render the existing `CapabilityConsole` with a no-op `onBack`). Also port the `PostRunSummary` auto-open-on-DONE dedup behavior into `AppShell` (from EditorialShell lines 241-274).
- [ ] **Step 4: Wire App.tsx** — wrap the app in `<PageProvider>`. Replace the entire `mode`-switch return block with a single `<ErrorBoundary><AppShell {...props}/></ErrorBoundary>` (keep the `if (!project) return <ProjectSelector/>` guard above it). `handleGenerate` sets `page='run'` (via context) instead of `mode='pipeline'`; delete the `mode` state and the console/capability/pipeline branches (their content now lives in pages). `onOpenConsole`/`onOpenCapability` become `setPage('run')`/`setPage('capability')`.
- [ ] **Step 5: Test** — `AppShell.test.tsx`: render `AppShell` with a minimal mocked `project`/`config` inside `PageProvider`; assert the four page tabs exist; click `✂ Edit` → the Edit page marker shows; assert clicking a `.scene-jump` (if present) is deferred to Task 6. Also assert `BudgetHaltBanner` renders when `budgetHalt` prop is set (`role="alert"` present).
- [ ] **Step 6: Verify** — test PASS; `npm --prefix web run build` succeeds; manually confirm (Task 13 does the live check) the app still boots to Setup and Generate still switches to Run.
- [ ] **Step 7: Commit** — `git add -A web/src && git commit -m "feat(ui): AppShell + page-bar nav; App.tsx renders unified shell (pages stubbed to existing screens)"`.

---

### Task 6: Setup page — Project tree + Scenes cue sheet

**Files:**
- Create: `web/src/components/setup/{ProjectTree,SceneCueSheet}.tsx`, `web/src/components/pages/SetupPage.tsx` (replace stub), `SceneCueSheet.test.tsx`
- Modify: `web/src/types/project.ts` (add `objects: ProductObject[]` to `Project`)

**Interfaces:**
- Consumes: `usePage().setPage/setFocusScene`, the six panels' logic. Produces: nothing downstream depends on internals; `SceneCueSheet` calls `setFocusScene(id); setPage('edit')` on row double-click.

- [ ] **Step 1:** Add `objects: ProductObject[]` to the `Project` interface in `types/project.ts`; remove the `(project as any).objects` casts in `ObjectPanel.tsx` and `ScenePanel.tsx`.
- [ ] **Step 2: ProjectTree** (left column, `w-[236px] border-r border-line`) — a token-styled tree with collapsible groups Characters/Locations/Objects/Scenes (counts from `project.*`). Rather than rewrite CRUD, mount the existing panels' bodies inside the groups OR (simpler, lower-risk for this task) render the existing `CharacterPanel/LocationPanel/ObjectPanel/ScenePanel` restyled into the column. Reuse their `{project, config, onRefresh}` props verbatim.
- [ ] **Step 3: SceneCueSheet** (center) — dense `<table>` (`#`, Scene, Location, Shots, Primary API, Status) from `project.scenes` (read `scene.title`, `scene.location_id`→location name, `scene.num_shots||scene.shots?.length`, primary API label, a `<StatusDot/>`). Row `onDoubleClick` → `setFocusScene(scene.id); setPage('edit')`.
- [ ] **Step 4: SetupPage** — 3-col: `ProjectTree | SceneCueSheet | SettingsInspector` (SettingsInspector arrives in Task 8; until then mount the existing `SettingsPanel` in the right column). Preserve `GenerationPanel`/`PreviewPanel` access (fold into the tree footer or a Setup sub-panel).
- [ ] **Step 5: Test** — `SceneCueSheet.test.tsx`: render with 2 mock scenes; assert both rows show; double-click row 1 → asserts a `setPage` spy called with `'edit'` and `setFocusScene` with the scene id (inject via a mock `usePage`).
- [ ] **Step 6: Verify + Commit** — test PASS, build green. `git add -A web/src && git commit -m "feat(ui): Setup page — project tree + scene cue sheet with double-click-to-Edit"`.

---

### Task 7: Reconciliation A — engine list + pod-gating helpers (config-driven)

**Files:**
- Create: `web/src/lib/engines.ts`, `web/src/lib/podGating.ts` + `*.test.ts`
- Verify only (no change expected): `web_server.py` `/api/config` returns `api_registry` + `billing_providers`.

**Interfaces:**
- Produces:
  - `videoEngines(config: AppConfig|null): {key, label, status, primary, cost?, quality?}[]` — filters `config.api_registry` to `modality==='video'`, EXCLUDES the retired/sunset set `['SORA_NATIVE','SORA_2','RUNWAY_GEN4','RUNWAY','HEDRA_C3','KLING_NATIVE','VEO']` from the picker (per spec: remove Sora/Runway/Hedra; hide legacy fal proxies), orders by the canonical Google-first order `['GEMINI_OMNI','VEO_NATIVE','SEEDANCE','KLING_3_0','LTX']`, marks `primary=true` for `GEMINI_OMNI`. Any live video engine not in the exclude/order lists is appended after, so new engines surface automatically.
  - `isPodGated(engineKey, config): boolean` = `config.billing_providers?.[engineKey] === 'RUNPOD_GPU'`. Plus `POD_FEATURES = ['lora_training','comfyui_keyframe']` for the two non-engine pod gates.

- [ ] **Step 1: Confirm backend** — `curl -s localhost:8080/api/config | python -m json.tool | grep -E 'billing_providers|api_registry'` (or read `web_server.py:328` `get_config`) to confirm both keys ship. If `billing_providers` is absent from the payload, add it to `get_config` from `domain/scene_decomposer.BILLING_PROVIDERS` (it is listed in the returned keys per inventory — verify, don't assume).
- [ ] **Step 2: Write failing tests** — `engines.test.ts`: given a mock `config.api_registry` with `GEMINI_OMNI/VEO_NATIVE/SEEDANCE/KLING_3_0/LTX/SORA_NATIVE/RUNWAY_GEN4` all `modality:'video',status:'live'`, `videoEngines(config)` returns exactly 5 keys in order `[GEMINI_OMNI,VEO_NATIVE,SEEDANCE,KLING_3_0,LTX]` with `GEMINI_OMNI.primary===true` and NO Sora/Runway. `podGating.test.ts`: `isPodGated('FLUX_DEV', {billing_providers:{FLUX_DEV:'RUNPOD_GPU'}})===true`; `isPodGated('GEMINI_OMNI', {billing_providers:{GEMINI_OMNI:'GOOGLE_GEMINI_API'}})===false`.
- [ ] **Step 3: Implement** the two libs to pass.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `git add web/src/lib && git commit -m "feat(ui): config-driven reconciled video-engine list + pod-gating helpers"`.

---

### Task 8: Setup Settings inspector (Video/Image/Identity/Voice/Budget) + delete MaxQualityTier

**Files:**
- Create: `web/src/components/setup/SettingsInspector.tsx` + `inspector/{VideoSection,ImageSection,IdentitySection,VoiceSection,BudgetSection}.tsx` + `VideoSection.test.tsx`
- Delete: `web/src/components/settings/MaxQualityTierSection.tsx`
- Modify: `web/src/components/settings/{AdvancedSection,CostEstimatorSection,index.ts}.tsx`, `web/src/components/SettingsPanel.tsx` (or replace its use in SetupPage)

**Interfaces:**
- Consumes: `videoEngines`/`isPodGated` (Task 7), `Section/Toggle/Badge/SelectPill/Meter` (Task 3), the `update(key,value)` contract. Each section reads `s = project.global_settings` and writes via `update`.
- Exact config keys per section (from inventory — do not invent):
  - **Video:** engine enable via `s.api_engines[key].enabled` (falls back to `config.api_engine_defaults[key]`), write `update('api_engines', {...current, [key]:{...}})`; global `s.cascade_retry_limit` (0–5, default 2); post-processing lives here too: `color_grade_preset`, `motion_quality_threshold` (0.4), `coherence_check_enabled` (true), `color_drift_sensitivity` (0.3), `scene_transitions` (false), `transition_duration` (0.5), `face_swap_enabled`. Each engine row shows `<Badge variant={isPodGated?'pod':'cloud'}/>` and `<Badge variant="pri"/>` when primary.
  - **Image:** `identity_backend` toggle (`'gemini_multiref'` default = Nano Banana `Cloud` Primary ↔ `'pod'` = ComfyUI FLUX+PuLID `⚙ Pod`); `comfyui_sampler`, `comfyui_steps` (20) shown only when backend='pod'.
  - **Identity:** `identity_strictness` (0.6), `identity_retry_max` (3), `adaptive_pulid` (true), `flux_guidance` (3.5), `coherence_threshold` (0.6); per-character LoRA training entry carries `<Badge variant="pod"/>` (LoRA UI stays in CharacterPanel; here just surface the pod-gated flag + link).
  - **Voice:** `tts_provider` (default `ELEVENLABS_V3`, options from `config.api_registry` filtered `modality==='tts'`), defaults **Eric**/**Lily** as the male/female voice choices, `dialogue_mode_enabled` (true), `forced_alignment_enabled` (true), lipsync: `lip_sync_mode` (`auto|overlay|generation|skip`), `lipsync_engine_priority` (reorderable, reuse `AudioSyncSection`'s `LipsyncPriorityList`), `lipsync_quality_validation` (true), `lipsync_validation_threshold` (0.65). **Pace control:** a target-wpm number field bound to a NEW key `s.dialogue_target_wpm` (default 145) with helper text "applied via atempo post-process" — NOT a `speed` field (eleven_v3 ignores speed). `music_mastering` select also lands here.
  - **Budget:** `budget_limit_usd` (0=unlimited) + the `CostEstimatorSection` estimate sub-view (production-only path — see Step 3).
- Reconciliation folded in: **no quality-tier selector** (max retired); ProductionSection's `aspect_ratio`/`language`/`music_mood`/`color_palette`/`style_rules` move to a top **"Project"** `Section` at the inspector top.

- [ ] **Step 1: Delete MaxQualityTier** — remove `MaxQualityTierSection.tsx`, its `index.ts` export, and its mount in `SettingsPanel`. In `AdvancedSection.tsx` delete the entire `MaxTierComfyControls` block and all `isMaxTier`-gated fields (`ays_steps, slg_scale, detail_daemon_amount, freeu_*, controlnet_*_strength, redux_strength, hires_fix_*, face_detailer_*, supir_*`), keeping production-tier fields only. In `CostEstimatorSection.tsx` remove the `quality_tier==='max'` branch — always use the production candidate path in the `/api/cost-estimate` POST body. (Backend `char_lora_paths`/`style_reference_paths` config keys are NOT deleted — only the UI; a note: verify no backend read outside the retired max pipeline before any backend key removal — out of scope here.)
- [ ] **Step 2: Write failing test** — `VideoSection.test.tsx`: render `VideoSection` with mock `config` (5 live video engines + billing_providers) and `s={}`; assert engine rows render in Google-first order, `GEMINI_OMNI` shows a `Primary` badge, all five show `Cloud` (none pod), and Sora/Runway are absent. Add an assertion that a mock pod engine (`FLUX_DEV`, if surfaced anywhere) would show `⚙ Pod`.
- [ ] **Step 3: Build the 5 sections + SettingsInspector** — each is a `<Section>` wrapping token-styled rows using `Toggle/SelectPill/Badge/Meter`; every engine/option row renders its pod/cloud badge via `isPodGated`. `SettingsInspector` composes: Project → Video → Image → Identity → Voice → Budget. Mount `SettingsInspector` in `SetupPage`'s right column (replacing the interim `SettingsPanel`). Reuse `AudioSyncSection`'s reorderable-list + `styles.ts` class constants to cut duplication.
- [ ] **Step 4: Run → PASS; build green** (proves the MaxQualityTier deletion left no dangling `isMaxTier`/import).
- [ ] **Step 5: Commit** — `git add -A web/src && git commit -m "feat(ui): Setup settings inspector (Video/Image/Identity/Voice/Budget) + delete max-tier UI; reconcile engines/pod badges/voice+pace"`.

---

### Task 9: Edit page — shot workspace

**Files:**
- Create: `web/src/components/edit/{ShotBin,ShotViewer,Timeline,ShotInspector}.tsx`, `web/src/components/pages/EditPage.tsx` (replace stub), `Timeline.test.tsx`

**Interfaces:**
- Consumes: `usePage().focusScene`, `project.scenes[].shots[]`, `PromptEditor` save logic (`PUT /api/projects/{pid}/shots/{sid}` body `{prompt, target_api, camera, visual_effect, negative_constraints, continuity_constraints, intent_notes}` — verbatim field names), `classifyShotType/getShotTemplate` from `lib/guidance`, `videoEngines` (Task 7), the shared `Filmstrip` timeline pattern.

- [ ] **Step 1: EditPage layout** — 3-region: `ShotBin (left)` | `stage (center: ShotViewer + transport + Timeline)` | `ShotInspector (right)`. Default the focused scene to `usePage().focusScene ?? project.scenes[0]?.id`; local `selectedShotId` state.
- [ ] **Step 2: ShotBin** — the focused scene's shots as a list with `<StatusDot/>` per shot (status from `shotStates` map when a run exists, else `idle`).
- [ ] **Step 3: ShotViewer** — reuse `HeroShot`'s media-resolution pattern (`state?.generated_image||shot?.generated_image`; URL via `${apiBase}/projects/${projectId}/file?path=${encodeURIComponent(path)}`); transport bar is presentational.
- [ ] **Step 4: Timeline** — horizontal track of clips grouped by scene (all `project.scenes` → their shots), selected clip highlighted (`border-acc`), click selects, double-click stays in Edit. This is the canonical "scenes→shots as clips" view.
- [ ] **Step 5: ShotInspector** — sections Prompt (positive/negative, reuse PromptEditor's section-tag parse/assemble — extract to `web/src/lib/promptSections.ts` shared with `ShotRow`), Dialogue (line + voice `SelectPill` + pace wpm), Shot (type via `classifyShotType`, primary API via `videoEngines` `SelectPill`, duration), Identity (PuLID weight, threshold, `⚙ Pod` ComfyUI-keyframe `Toggle` bound to `identity_backend`). Saves via the PromptEditor PUT contract.
- [ ] **Step 6: Test** — `Timeline.test.tsx`: 2 scenes × 2 shots → 4 clips render grouped; clicking clip 3 calls the `onSelect` spy with that shot id.
- [ ] **Step 7: Verify + Commit** — test PASS, build green. `git add -A web/src && git commit -m "feat(ui): Edit page — shot bin + viewer + timeline + inspector"`.

---

### Task 10: Run page — merge PipelineLayout + DirectorsConsole; canonical Filmstrip

**Files:**
- Create: `web/src/components/shared/Filmstrip.tsx` + `Filmstrip.test.tsx`, `web/src/components/pages/RunPage.tsx` (replace stub)
- Modify: consumers of the old two filmstrips; Delete `web/src/components/pipeline/Filmstrip.tsx` + `web/src/components/console/Filmstrip.tsx` after migration.

**Interfaces:**
- Consumes: the frozen `usePipelineState` values + callbacks (threaded through `AppShell`), `PipelineStageRail`, `HeroShot`, `TakeStrip`, `ShotApprovalControls`, `Telemetry`, `Notes`, `Monitor`, `ReviewStage`/`ScreeningStage` (restyle in place). 
- Produces: `Filmstrip({project, shotStates, apiBase?, projectId, activeShotId?, onShotClick?})` — the merged component: windowed (40 + "+N more") from console/ + 4-state `FrameStatus` (`frameStatusOf(ShotState.status)`) + engine tag + real `generated_image` thumbnails via the shared file-URL resolver. Falls back to `shot.plan_status` when no `ShotState` exists.

- [ ] **Step 1: Build canonical `shared/Filmstrip.tsx`** merging both feature sets (windowing + onShotClick + 4-state status + thumbnails). Extract the repeated media-URL resolver to `web/src/lib/mediaUrl.ts` `fileUrl(apiBase, projectId, path)`.
- [ ] **Step 2: Test** — `Filmstrip.test.tsx`: 45 shots → renders 40 + a "+5 more" control; a shot with `ShotState.status==='complete'` gets the `done` status class; `onShotClick` fires with shot id on click.
- [ ] **Step 3: RunPage** — compose: left shot-queue (statuses), center `PipelineStageRail` (must render all 14 stage ids incl. `SCREENING`) + `HeroShot`/`Monitor` + `TakeStrip` + the merged `Filmstrip`, right `Telemetry` + `ShotApprovalControls` + `Notes`. Route on `activeStage` exactly as the old `PipelineLayout` did (`SCREENING`→ScreeningStage; review stages→ReviewStage; else execution board). Thread all `on*` callbacks from `AppShell`.
- [ ] **Step 4: Migrate + delete** the two old Filmstrips; point `PipelineLayout`/`DirectorsConsole` remnants (or their replaced call sites) at `shared/Filmstrip`. Build green proves no dangling imports.
- [ ] **Step 5: Verify + Commit** — tests PASS, build green. `git add -A web/src && git commit -m "feat(ui): Run page merges pipeline+console; single canonical Filmstrip"`.

---

### Task 11: Capability page — restyle CapabilityConsole

**Files:**
- Create: `web/src/components/pages/CapabilityPage.tsx` (replace stub)
- Modify: `web/src/components/console/CapabilityConsole.tsx` (restyle to tokens; keep fetch/state machine)

**Interfaces:**
- Consumes: `GET /api/projects/{id}/capability-scorecard` → `CapabilityScorecard` (preserve the four-state `loading|ready|empty|error` machine; `empty` when `summary.shots_total===0`). Produces: nothing downstream.

- [ ] **Step 1:** Restyle `CapabilityConsole`'s internal sections (ScorecardGrid, MediaConformanceTiles, PerShotTable, CascadeProvenance, GateAudit, LoraSummary, ComponentStatus) to token classes + `Meter`/`Badge`/`StatusDot`. Overall score + "N of M systems engaged" header. Lip-sync dimension card surfaces "gate needs recal" note (from the dialogue findings). Add the spec's **"Available — not engaged"** row (ComfyUI max keyframe `⚙ Pod off`, second-char LoRA, Foley) from `future_dimensions`/component status.
- [ ] **Step 2:** `CapabilityPage` renders it with `project` from context (drop the old `onBack` — navigation is the page-bar now).
- [ ] **Step 3: Test** — `CapabilityPage.test.tsx`: mock fetch returning a scorecard with `shots_total:0` → asserts the empty-state copy; a scorecard with dimensions → asserts a `Meter` per dimension renders.
- [ ] **Step 4: Verify + Commit** — test PASS, build green. `git add -A web/src && git commit -m "feat(ui): Capability page — restyled scorecard + available-not-engaged row"`.

---

### Task 12: Backend lip-sync fix — drop the miswired Kling generation attempt

**Files:**
- Modify: `lip_sync.py` (~line 857-875, the `ATTEMPT 0: Kling native lip sync` block inside `lipsync_generation`)
- Test: `tests/unit/test_lipsync_generation_cascade.py`

**Interfaces:**
- The generation cascade becomes `OmniHuman v1.5 → Creatify Aurora` (Kling's `fal-ai/kling-video/lipsync/audio-to-video` requires `video_url`, so it 422s on every still-image generation call — verified live 2026-07-18, `x-fal-billable-units:0`). Kling stays valid in the OVERLAY path (`lipsync_overlay`), which is unchanged.

- [ ] **Step 1: Write failing test** — `test_lipsync_generation_cascade.py`: monkeypatch `fal_client.subscribe` to record the endpoint strings it's called with; drive `lipsync_generation(image, audio, out, ...)` with OmniHuman succeeding; assert `fal-ai/kling-video/lipsync/audio-to-video` is NEVER among the called endpoints (it must not be attempted in the generation path), and OmniHuman IS attempted first. Run with `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_lipsync_generation_cascade.py -v` → FAIL (Kling currently attempted).
- [ ] **Step 2: Implement** — delete the `ATTEMPT 0: Kling native lip sync` try-block in `lipsync_generation`; renumber the comments so OmniHuman is ATTEMPT 0. Do NOT touch `lipsync_overlay`.
- [ ] **Step 3: Run → PASS.** Also run the existing lip-sync tests: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/ -k lipsync -q` → green.
- [ ] **Step 4: Commit** — `git add lip_sync.py tests/unit/test_lipsync_generation_cascade.py && git commit -m "fix(lipsync): drop miswired Kling overlay endpoint from still→talking-head generation cascade (422 every call); OmniHuman is ATTEMPT 0"`.

---

### Task 13: Cleanup, token prune, and live verification

**Files:**
- Modify: `web/tailwind.config.js`, `web/src/index.css`; delete `EditorialShell.tsx`, `DirectorsConsole.tsx`, old `PipelineLayout.tsx`/`SettingsPanel.tsx` if fully unreferenced.

- [ ] **Step 1: Prune dead shells** — `grep -rl 'EditorialShell\|DirectorsConsole' web/src` → if only self-references remain, delete them. Same for the old `SettingsPanel` (superseded by `SettingsInspector`) and `pipeline/PipelineLayout` chrome (superseded by `RunPage`).
- [ ] **Step 2: Prune editorial/console tokens** — `grep -rE 'text-editorial-|bg-editorial-|text-console-|bg-console-|font-display|Fraunces' web/src` → migrate any stragglers to indigo tokens; once zero, remove the `editorial`/`console` color namespaces + Fraunces `fontFamily`/`eyebrow` fontSize tokens + marquee/flicker animations from `tailwind.config.js`, and the film-grain/vignette/marquee blocks from `index.css`.
- [ ] **Step 3: Full check** — `npm --prefix web run test` (all green) and `npm --prefix web run build` (tsc clean + vite build) and `cd web && npm run build` produces `web/dist`.
- [ ] **Step 4: Live smoke** — start the app (`.venv/bin/python web_server.py`), load a project, verify each page renders, the page-bar switches, a scene double-click jumps to Edit, engine rows show correct Cloud/Pod/Primary badges, and Generate switches to Run. Capture a screenshot per page.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "chore(ui): prune editorial/console tokens + dead shells; build green on indigo system"`.

---

## Self-Review (author checklist — completed)

**Spec coverage:** tokens (T2) · ui primitives + Section (T3) · delete Eyebrow/stageColors (T4) · AppShell + page-bar + usePage + budgetHalt preserved (T5) · Setup tree+cue-sheet (T6) · Setup settings inspector Video/Image/Identity/Voice/Budget (T8) · Edit page (T9) · Run page merge + Filmstrip dedup (T10) · Capability restyle + available-not-engaged (T11) · pod-gating from billing_providers (T7/T8) · Google-first server-driven engines + remove Sora/Runway/Hedra (T7/T8) · Nano Banana default (T8) · delete MaxQualityTier + isMaxTier branches (T8) · Eric/Lily + atempo-wpm pace not speed (T8) · lip-sync Kling fix (T12) · Vitest tests (T1 + per-task) · error/loading/BUDGET_EXCEEDED preserved (T5) — **all mapped.**

**No-pod-status-endpoint gap:** the spec allows "manual toggle when no health endpoint exists" — pod *badges* are truthful (static, from `billing_providers`); a live pod-running indicator is deferred (a new `/api/pod/status` endpoint is out of scope and gated by the standing pod-auth rule). Flagged, not silently dropped.

**Type consistency:** `Page`, `usePage`, `videoEngines`, `isPodGated`, `Badge.variant`, `Section`, `fileUrl`, `frameStatusOf`, the frozen `usePipelineState` names, and the `update(key,value)` contract are used identically across tasks.

**Placeholder scan:** engine keys, config keys, endpoint field names, token hex, and defaults are all concrete (from the inventory). Where a component's full JSX is left to the implementer, the exact props/contracts/behaviors-to-preserve and the test are specified.
