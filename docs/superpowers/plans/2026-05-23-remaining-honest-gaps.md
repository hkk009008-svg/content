# Remaining Honest Gaps — Implementation Handoff

> **For agentic workers:** REQUIRED — use `superpowers:subagent-driven-development` (if subagents available) or `superpowers:executing-plans` to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close out the three remaining honest gaps from the post-`a8c6435` audit (excluding Runway Gen-4 driving consumption, deferred by operator decision).

**Architecture:** Three independent slices, executable in any order. None of them touch the performance-capture critical path that's already shipping; they're polish + tuning + design fidelity. Each slice has its own done criteria.

**Tech stack:** TypeScript/React (slices A, C), Python (slice B), Tailwind v3, the existing `performance/`, `cinema/shots/`, `cinema/phases/`, `hooks/usePipelineState` surface.

**Branch:** any feature branch off `main`. Suggested: `feature/remaining-gaps`. Each slice can also be its own micro-branch.

---

## 1. Why this matters (the WHY before the WHAT)

The post-merge audit at `89a195d` identified four remaining gaps. The Runway Gen-4 driving-video consumption is deferred (operator's call — handoff §18 of the original performance plan flagged it as v2 anyway). That leaves three:

| Gap | Symptom today | What "done" looks like |
|---|---|---|
| **A. Director's Console regions wired to live data** | The new console route renders the layout from `design/directors-console.html` but every region shows "TODO: data source: …" | Each of the 5 regions consumes real state from `usePipelineState` + the project. Hero region updates as the active shot changes. Filmstrip windows for >40 shots. Notes panel streams the last 20 SSE events with brass-themed formatting. |
| **B. Per-shot-type motion-floor calibration** | `performance/motion_gate.py:DEFAULT_MOTION_FLOOR = 0.50` is a single number applied uniformly — empirically picked, not data-driven. A portrait shot at 0.55 and a wide shot at 0.55 don't mean the same thing. | Per-shot-type floors live in `workflow_selector.py:MOTION_FIDELITY_FLOORS` and the gate reads from there. Floors are calibrated against ≥20 real shots' worth of (engine, shot_type, eyeballed-grade, gate-score) data. |
| **C. Full visual fidelity to `design/directors-console.html`** | The console shell is structurally faithful but visually generic. The mockup uses gradients, custom fonts, and bespoke spacing that the React shell skips. | Tailwind config has the mockup's tokens (colors, font, spacing scale). Each console region's styling matches the mockup screenshot at parity (operator-judged). |

None of these block production runs. All three meaningfully raise the perceived polish + tunability of the pipeline once you've got real shot data flowing.

---

## 2. Slice A: Director's Console live-data wiring

### 2.1 Files this slice owns

```
web/src/components/DirectorsConsole.tsx                ← gut and rewrite each region
web/src/hooks/usePipelineState.ts                      ← add active-shot tracker + notes buffer
web/src/components/console/*.tsx                       ← (new) per-region subcomponents
  HeroShot.tsx
  PhasesRail.tsx
  Monitor.tsx
  Telemetry.tsx
  Filmstrip.tsx
  Notes.tsx
```

**Decomposition rationale:** Each region has its own data shape + interaction model. Splitting into focused subcomponents is what the writing-plans skill calls "files that change together stay together, split by responsibility not by layer". The current 200-line `DirectorsConsole.tsx` is the shell that composes them.

### 2.2 State additions to `usePipelineState`

Add two new pieces of state, both already nearly there but never exposed:

```typescript
// hooks/usePipelineState.ts
// Existing state: events, shotStates, activeStage, ...
// NEW state needed by the console:

const [activeShotId, setActiveShotId] = useState<string | null>(null)
// Tracks the most recent shot_id that received a non-failure event.
// Hero region renders this shot. Updated inside processEvent.

const [notesBuffer, setNotesBuffer] = useState<ProgressEvent[]>([])
// Circular buffer of the last 20 events for the Notes region.
// Push in processEvent: setNotesBuffer(prev => [event, ...prev].slice(0, 20)).
```

**Update `processEvent` to populate both.** When `shot_id` is present and `stage` isn't a failure, set `activeShotId = shot_id`. On every event, push into `notesBuffer`.

Export them in the hook's return:

```typescript
return {
  // ... existing fields ...
  activeShotId,
  notesBuffer,
}
```

### 2.3 Per-region contracts

Each subcomponent gets a focused props surface. Below is the contract; the implementation follows the existing `ReviewStage` patterns.

#### `HeroShot.tsx`
```typescript
interface Props {
  project: Project
  activeShotId: string | null      // from hook
  shotStates: Map<string, Partial<ShotState>>
}
// Renders the most-recent shot: image (or last performance video) + scene title
// + camera motion + delivery cue (if dialogue). Falls back to a "no active shot"
// poster when activeShotId is null.
```

Find the resolved shot via:
```typescript
const activeShot = useMemo(() => {
  for (const scene of project.scenes || []) {
    for (const shot of scene.shots || []) {
      if (shot.id === activeShotId) return { shot, scene }
    }
  }
  return null
}, [project, activeShotId])
```

#### `PhasesRail.tsx`
```typescript
interface Props {
  stages: PipelineStage[]
  activeStage: string | null
  isPaused: boolean
  failedShots: string[]
}
// Existing inline implementation in DirectorsConsole.tsx is correct; extract as-is.
// Add a pause indicator when isPaused. Add failed-shot count footer.
```

#### `Monitor.tsx`
```typescript
interface Props {
  project: Project
  activeShotId: string | null
  shotStates: Map<string, Partial<ShotState>>
  apiBase: string
  directorReview: DirectorReview | null
}
// 3-pane preview: keyframe still | performance clip | motion clip.
// Mirrors the side-by-side pattern from ReviewStage.tsx's Performance Capture
// section. Renders the active shot's latest take from each stage when available.
// Below the panes: directorReview card (when present) — already exists inline.
```

The 3-pane preview pattern is already in `ReviewStage.tsx` (we built it for the PERFORMANCE_REVIEW gate). Extract the JSX (~40 lines) into a reusable `TakeStrip` component and use it in both ReviewStage and Monitor.

#### `Telemetry.tsx`
```typescript
interface Props {
  project: Project
  shotStates: Map<string, Partial<ShotState>>
  failedShots: string[]
  // (Optional) live cost ticker — pulled from a new /api/cost-tracker/live endpoint
  liveCostUsd?: number
}
// Shots metric, failed count, current engine pick (read from latest shot state),
// gate-score histogram (compute from shotStates' identity_score values).
```

The "live cost ticker" needs a new backend endpoint. Sketch:

```python
# web_server.py
@app.route("/api/projects/<pid>/cost-live", methods=["GET"])
def api_cost_live(pid):
    """Sum of cost_log entries for this video_id since pipeline start."""
    from cost_tracker import CostTracker
    tracker = CostTracker()
    rows = tracker.conn.execute(
        "SELECT SUM(cost_usd) AS total FROM cost_log WHERE video_id = ?",
        (pid,),
    ).fetchone()
    return jsonify({"total_usd": round(rows["total"] or 0.0, 4)})
```

Poll it from `Telemetry.tsx` every 5s while pipeline is streaming.

#### `Filmstrip.tsx`
```typescript
interface Props {
  project: Project
  apiBase: string
  onShotClick?: (shotId: string) => void   // optional — clicking sets activeShotId
}
// Horizontal scroller. For >40 shots, window the rendering (slice to ±20 around
// the focused shot, virtual scroll with intersection observer for the rest).
// Each card: thumbnail + scene tag + status badge (approved/failed/in-progress).
```

**Windowing approach** (simpler than full virtualization for our scale):
```typescript
const FILMSTRIP_WINDOW = 40
const allShots = useMemo(() => project.scenes?.flatMap(s => s.shots || []) || [], [project])
const visibleShots = allShots.slice(0, FILMSTRIP_WINDOW)
const overflowCount = Math.max(0, allShots.length - FILMSTRIP_WINDOW)
```

If `overflowCount > 0`, render a "+N more" card at the end that, when clicked, expands the window. Don't try to do real virtualization — the largest realistic short has ~120 shots; 40 in view is fine.

#### `Notes.tsx`
```typescript
interface Props {
  notesBuffer: ProgressEvent[]   // from hook
}
// Render the last 20 events with brass-themed monospace formatting.
// Color per stage (pulled from the existing stageColors map in GenerationPanel).
// Newest at the top.
```

### 2.4 Slice plan

| # | Slice | Touches | LOC | Risk |
|---|---|---|---|---|
| A1 | Add `activeShotId` + `notesBuffer` to `usePipelineState` | `hooks/usePipelineState.ts` | ~30 | low |
| A2 | Extract `TakeStrip` shared component (3-pane preview) | new `components/console/TakeStrip.tsx`, refactor `ReviewStage.tsx` to use it | ~80 | low — pattern already exists |
| A3 | Create the 6 region subcomponents (Hero, Phases, Monitor, Telemetry, Filmstrip, Notes) | new `components/console/*.tsx` | ~400 | low |
| A4 | Rewrite `DirectorsConsole.tsx` to compose the 6 regions | `components/DirectorsConsole.tsx` | ~80 | low |
| A5 | Backend `/api/projects/{pid}/cost-live` route | `web_server.py` | ~20 | low |
| A6 | Verify visual integrity + run real pipeline against console | manual | n/a | n/a |

**Ship order:** A1 → A2 → A3 (in parallel — 6 small files) → A4 → A5 → A6.

### 2.5 Done criteria for Slice A

- [ ] Open a project with ≥3 shots, click "Director's Console", confirm:
  - [ ] Hero shows the most recent shot's image/video without manual refresh
  - [ ] Phases rail highlights the active stage and shows pause indicator if paused
  - [ ] Monitor 3-pane preview shows keyframe + performance + motion takes side-by-side
  - [ ] Telemetry shows shot count, failed count, AND a non-zero live cost ticker
  - [ ] Filmstrip renders every shot, with "+N more" affordance when >40
  - [ ] Notes panel shows the last 20 SSE events with stage-colored formatting
- [ ] No TODO strings remain visible to the user in the console (`grep -n "TODO" web/src/components/console/` returns nothing surfacing in the running UI)
- [ ] `npx tsc --noEmit` clean
- [ ] `npx vite build` succeeds

---

## 3. Slice B: Per-shot-type motion-floor calibration

### 3.1 Why a single floor is wrong

`performance/motion_gate.py` returns a similarity in [0, 1] based on optical-flow histogram cosine. We currently treat 0.50 as the "below this, recommend the operator reject" floor across all shots. But:

- **Portrait close-ups** have narrow flow patterns (mostly face-region motion) — histogram bins are sparse, scores cluster low naturally, 0.50 is too strict.
- **Wide shots** have lots of background motion — scores cluster high, 0.50 is too loose.
- **Action shots** have high-magnitude flow — high baseline scores, 0.50 lets garbage through.
- **Macro/detail shots** have minimal flow on either side — scores are noisy near zero.

The fix: per-shot-type floors, calibrated empirically.

### 3.2 Data-gathering protocol (the real work of this slice)

This slice is mostly NOT code. It's a data-gathering + analysis pass against a real pipeline run. Here's the protocol:

#### Step 1: Run ≥20 real shots through the full performance-capture pipeline

Pick a project (or compose one) with **at least 4 shots per shot type**:
- 4× portrait dialogue shots
- 4× medium dialogue shots
- 4× wide establishing shots
- 4× action motion shots
- 4× macro/detail shots

Ensure each has:
- An approved keyframe
- A performance driving video (Mode B autopilot is fine for dialogue; Mode A upload for action)
- A completed motion render

#### Step 2: Capture (engine, shot_type, motion_fidelity, identity_score, eyeball_grade) per shot

The pipeline already stores `motion_fidelity` in `take["metadata"]`. Add a small CLI script:

```python
# scripts/calibrate_motion_floor.py
"""Dump (shot_type, motion_fidelity, identity_score) tuples for calibration."""
import json
import sys
from project_manager import load_project

def dump_metrics(project_id: str) -> list[dict]:
    project = load_project(project_id)
    rows = []
    for scene in project.get("scenes", []):
        for shot in scene.get("shots", []):
            mt = shot.get("motion_takes", [])
            if not mt:
                continue
            latest = mt[-1]
            meta = latest.get("metadata", {})
            rows.append({
                "shot_id": shot["id"],
                "shot_type": shot.get("shot_type", "?"),
                "engine": meta.get("target_api", "?"),
                "motion_fidelity": meta.get("motion_fidelity"),
                "identity_score": meta.get("identity_score"),
                "eyeball_grade": None,  # operator fills in
            })
    return rows

if __name__ == "__main__":
    print(json.dumps(dump_metrics(sys.argv[1]), indent=2))
```

#### Step 3: Eyeball-grade each shot (operator workflow)

Open each motion take in QuickTime/Resolve. Compare against its driving video. Grade 1-5:
- 1 = motion doesn't match driving video at all
- 2 = wrong direction/timing
- 3 = roughly correct but obvious differences
- 4 = correct motion with minor differences
- 5 = motion follows driving closely

Append grades to the JSON above.

#### Step 4: Compute per-shot-type floors

Sort each shot type's rows by `motion_fidelity`. Find the threshold that:
- Passes most grade-3+ shots
- Rejects most grade-1 and grade-2 shots

In practice, the floor is roughly the `motion_fidelity` value of the worst grade-3 shot in each type.

Expected ballpark from prior runs:

```python
MOTION_FIDELITY_FLOORS = {
    "portrait":  0.42,   # narrower flow bins → lower natural scores
    "medium":    0.55,
    "wide":      0.65,   # lots of background motion → higher floor
    "action":    0.60,   # high-magnitude flow needs stricter cutoff
    "macro":     0.40,   # minimal motion in either video; noisy
    "landscape": None,   # no performance capture for landscape — N/A
}
```

**Do not ship the table above as gospel.** It's a starting point. Operator must verify against their real shot data.

### 3.3 Code changes

#### B1. Add the calibrated table

```python
# workflow_selector.py  (or a new domain/motion_thresholds.py — operator's call)

MOTION_FIDELITY_FLOORS: dict[str, Optional[float]] = {
    "portrait":  0.42,
    "medium":    0.55,
    "wide":      0.65,
    "action":    0.60,
    "macro":     0.40,
    "landscape": None,
}

def motion_floor_for(shot_type: str) -> Optional[float]:
    """Return the motion-fidelity floor for a shot type, or None when motion
    capture doesn't apply (landscapes)."""
    return MOTION_FIDELITY_FLOORS.get(shot_type)
```

#### B2. Update `motion_gate.needs_remotion()` to be shot-type aware

```python
# performance/motion_gate.py

def needs_remotion(
    score: Optional[float],
    shot_type: Optional[str] = None,
    floor_override: Optional[float] = None,
) -> bool:
    """True when the gate's score is below the per-shot-type floor.

    Returns False when score is None (inconclusive — defer to operator) OR
    when the shot type has no floor (landscape).

    Resolution order:
      1. floor_override (caller forces a value, e.g., per-shot tuning)
      2. workflow_selector.motion_floor_for(shot_type)
      3. DEFAULT_MOTION_FLOOR (legacy single-value behavior)
    """
    if score is None:
        return False

    if floor_override is not None:
        floor = floor_override
    elif shot_type:
        from workflow_selector import motion_floor_for
        floor = motion_floor_for(shot_type)
        if floor is None:
            return False   # shot type opts out (landscape)
    else:
        floor = DEFAULT_MOTION_FLOOR

    return score < floor
```

#### B3. Wire `shot_type` through the call site

Currently `generate_motion_take` calls `score_motion_fidelity` but doesn't act on the score. Once `MOTION_FIDELITY_FLOORS` exists, add a downstream consumer (a UI signal, not an auto-fail — see §3.4):

```python
# cinema/shots/controller.py  (inside generate_motion_take, after motion_fidelity is computed)

from performance.motion_gate import needs_remotion
if needs_remotion(motion_score, shot_type=resolved_shot_type):
    take["metadata"]["motion_floor_failed"] = True
    self.progress(
        "MOTION_BELOW_FLOOR",
        f"Shot {shot_id} motion fidelity {motion_score:.3f} below floor for {resolved_shot_type}",
        -1, scene_id=scene_id, shot_id=shot_id,
        motion_fidelity=motion_score, shot_type=resolved_shot_type,
    )
```

The `MOTION_BELOW_FLOOR` event surfaces in the SSE stream. UI can highlight the take in the review gate.

#### B4. Surface the flag in `ReviewStage.tsx`

In the Performance Capture section's scores block, when `metadata.motion_floor_failed === true`, render a brass warning chip:
```tsx
{performanceMetadata.motion_floor_failed && (
  <span className="ml-2 rounded bg-editorial-curtain/20 px-1.5 py-0.5 text-eyebrow-lg text-editorial-curtain">
    below {resolvedShotType} floor
  </span>
)}
```

### 3.4 Critical design call (operator decision needed before slice ships)

**Should `MOTION_BELOW_FLOOR` auto-fail the take, or just flag it for review?**

Two valid paths:

- **Advisory** (recommended): flag the take, surface in UI, let operator decide. Matches the current "gate is a scoreboard not auth" stance from the identity gate.
- **Auto-fail**: mark the take rejected and trigger a re-render. Saves operator clicks but trusts the threshold absolutely.

Calibration accuracy on 20 shots isn't enough to justify auto-fail — picking advisory until you have ≥100 shots of calibration data is the conservative call.

**Reference:** the original performance-capture handoff §15 picks advisory for the same reason. Match that posture.

### 3.5 Slice plan

| # | Slice | Touches | LOC | Effort |
|---|---|---|---|---|
| B1 | Run 20-shot calibration pass, write grades | manual + `scripts/calibrate_motion_floor.py` | 30 LOC + ~1 hour of operator review | medium |
| B2 | Add `MOTION_FIDELITY_FLOORS` + `motion_floor_for()` | `workflow_selector.py` | ~15 | low |
| B3 | Update `needs_remotion()` to be shot-type aware | `performance/motion_gate.py` | ~15 | low |
| B4 | Wire emit `MOTION_BELOW_FLOOR` SSE event | `cinema/shots/controller.py` | ~10 | low |
| B5 | Surface flag in `ReviewStage.tsx` | `web/src/components/pipeline/ReviewStage.tsx` | ~10 | low |
| B6 | Unit test: `needs_remotion(0.5, shot_type='portrait')` returns False, `shot_type='wide'` returns True | `tests/unit/test_motion_gate.py` | ~20 | low |

### 3.6 Done criteria for Slice B

- [ ] `scripts/calibrate_motion_floor.py` produces JSON for ≥20 real shots
- [ ] Operator-graded JSON checked into `data/calibration/motion_floors_<date>.json`
- [ ] `MOTION_FIDELITY_FLOORS` dict reflects the calibration (not the placeholder values from §3.2)
- [ ] `tests/unit/test_motion_gate.py` covers per-shot-type floor lookup + landscape opt-out
- [ ] At least one real pipeline run emits a `MOTION_BELOW_FLOOR` SSE event for a deliberately-bad shot AND the UI shows the brass warning chip
- [ ] Operator-decision section (§3.4) explicitly resolved — advisory or auto-fail, written in a code comment above `MOTION_FIDELITY_FLOORS`

---

## 4. Slice C: Full visual fidelity to `design/directors-console.html`

### 4.1 What "visual fidelity" means here

`design/directors-console.html` is a 1091-line static design mockup. The current React shell (Slice A above wires it up to data) is structurally faithful — same regions, same layout grid — but visually generic. The mockup uses:

- A custom Tailwind palette extending the existing editorial tokens (`editorial-brass-glow`, `editorial-ivory-warmer`, gradient stops for the masthead)
- Two custom fonts loaded via `@font-face` (display font for the masthead, monospace for the telemetry numbers)
- Bespoke spacing for the phases rail (tighter than default Tailwind `space-y-1.5`)
- Gradient backgrounds on the masthead + hero section
- Subtle inner shadows on the panels (`shadow-editorial-inset`)
- A custom scrollbar treatment for the filmstrip

### 4.2 What this slice does NOT do

- It does NOT redesign anything. The mockup is the spec.
- It does NOT touch any other component's styling. Editorial-cinema fidelity pass already shipped at `c7ab448` — that's the reference for non-console treatments.
- It does NOT load any new third-party libraries.

### 4.3 Pre-work: extract the tokens

Open `design/directors-console.html` and identify each unique:

1. Color (hex codes) — there are ~15 used. Mark which ones aren't in `tailwind.config.js` already.
2. Font face — note `@font-face` declarations + source URLs. Likely Google Fonts; if so, add to `index.html` as a link tag.
3. Spacing unit (px or rem) that doesn't already map to Tailwind's scale.
4. Gradient (`linear-gradient(...)`) — extract for use as a Tailwind plugin or inline CSS.

### 4.4 File changes

```
web/tailwind.config.js                       ← extend theme with new tokens
web/src/index.css                            ← @font-face declarations OR
web/index.html                                ← Google Fonts link
web/src/components/console/*.tsx             ← apply new tokens (per region)
```

### 4.5 Token additions to `tailwind.config.js`

The existing config has an `editorial` palette under `theme.extend.colors`. Add the console-specific tokens there:

```javascript
// web/tailwind.config.js
module.exports = {
  // ...existing config...
  theme: {
    extend: {
      colors: {
        editorial: {
          // ...existing editorial.* tokens...
          'brass-glow':    '#D4A06B',   // brighter brass for masthead headlines
          'ivory-warmer':  '#F5EAD3',   // warmer ivory for hero subtitle
          'masthead-bg':   '#0D0B12',   // deepest ink (masthead background)
          'panel-inset':   '#15131C',   // panel inner shadow color
        },
      },
      fontFamily: {
        // Map the console's display font to a name we can use in className
        'console-display': ['Cormorant Garamond', 'Georgia', 'serif'],
        'console-mono':    ['JetBrains Mono', 'Menlo', 'monospace'],
      },
      boxShadow: {
        'editorial-inset': 'inset 0 1px 0 0 rgba(255,255,255,0.04), inset 0 -1px 0 0 rgba(0,0,0,0.4)',
      },
      backgroundImage: {
        'masthead-gradient': 'linear-gradient(180deg, #0D0B12 0%, #15131C 100%)',
        'hero-gradient':     'linear-gradient(135deg, rgba(212,160,107,0.08) 0%, rgba(13,11,18,0) 60%)',
      },
    },
  },
}
```

### 4.6 Per-region styling pass

For each subcomponent from Slice A, apply the tokens:

#### `HeroShot.tsx`
```tsx
<section className="bg-hero-gradient px-8 py-12">
  <h1 className="font-console-display text-4xl text-editorial-brass-glow">
    {/* ... */}
  </h1>
</section>
```

#### `PhasesRail.tsx`
```tsx
<aside className="bg-editorial-masthead-bg shadow-editorial-inset px-4 py-6">
  <ul className="space-y-[6px]">  {/* tighter than space-y-1.5 */}
    {/* ... */}
  </ul>
</aside>
```

#### `Monitor.tsx`, `Telemetry.tsx`, `Filmstrip.tsx`, `Notes.tsx`
Same pattern — pick tokens from the mockup, apply per-element.

### 4.7 Custom scrollbar for the filmstrip

```css
/* web/src/index.css */
.filmstrip-scroll::-webkit-scrollbar { height: 6px; }
.filmstrip-scroll::-webkit-scrollbar-track { background: transparent; }
.filmstrip-scroll::-webkit-scrollbar-thumb {
  background: theme('colors.editorial.brass-glow');
  border-radius: 3px;
}
```

Apply class to the filmstrip's outer scrollable div.

### 4.8 Slice plan

| # | Slice | Touches | LOC | Risk |
|---|---|---|---|---|
| C1 | Extract tokens from `design/directors-console.html` (manual audit) | none, but produces a token list | n/a | low |
| C2 | Extend `tailwind.config.js` with new tokens | `web/tailwind.config.js` | ~30 | low |
| C3 | Add `@font-face` or Google Fonts link | `web/index.html` or `web/src/index.css` | ~10 | low |
| C4 | Apply tokens region-by-region | 6× `web/src/components/console/*.tsx` | ~60 | low — visual only |
| C5 | Add custom scrollbar CSS | `web/src/index.css` | ~10 | low |
| C6 | Side-by-side visual compare against mockup screenshot, iterate | manual | ~1 hour | medium — taste call |

### 4.9 Done criteria for Slice C

- [ ] Tailwind config has all new editorial tokens; `npx vite build` succeeds
- [ ] Console route in dev mode renders without console errors
- [ ] Side-by-side screenshot comparison (browser DevTools full-page capture vs `design/directors-console.html` opened in same window): visual delta < 10% per region by operator judgement
- [ ] `npx tsc --noEmit` clean
- [ ] No regression on other UI routes (open ProjectSelector + PipelineLayout + EditorialShell, confirm no broken styling)

---

## 5. Cross-cutting open questions to resolve BEFORE starting

These three slices interact lightly. Resolve before you start:

1. **Order of execution.** Slice A (live data) is the foundation — B and C make less sense without A. If picking only one, do A. If picking two, A + B (real numbers in the UI matter more than visual fidelity).
2. **Should `MOTION_BELOW_FLOOR` events appear in the Notes panel?** (Slice A × Slice B intersection.) Recommended: yes, in `editorial-curtain` color so it stands out. Trivial to wire when both slices are done.
3. **Where do the calibration JSONs live in git?** Proposal: `data/calibration/motion_floors_<YYYY-MM-DD>.json`, gitignored except for an `index.json` that lists which calibration is currently active. Avoids leaking per-project shot grades into the repo while preserving the audit trail.
4. **Asset rights for the console fonts.** Verify Cormorant Garamond and JetBrains Mono (or whatever the mockup uses) are SIL/OFL-licensed and freely embeddable. If not, swap to nearest licensed alternative before committing the font load.

---

## 6. What NOT to do in any of these slices

- **Don't reorganize the console regions.** The 7-region layout (masthead / hero / phases / monitor / telemetry / filmstrip / notes) is the design. Sub-components inside each region can refactor freely, but the top-level grid stays.
- **Don't auto-fail shots from the motion floor gate.** Advisory only until ≥100 shots of calibration data. See §3.4.
- **Don't add new state to `usePipelineState` beyond `activeShotId` + `notesBuffer`** without revisiting how SSE event routing works. The hook is already doing too much; new state types should live in their own hook (`useTelemetry`, etc.).
- **Don't load real-time cost data on every render.** Poll every 5 seconds when streaming, every 30 seconds otherwise. Don't subscribe to a `cost_log` table change feed — we don't have one and adding it is out of scope.
- **Don't port the mockup's CSS literally.** It's a hand-written HTML/CSS file with no React-class idioms. Translate intent (gradients, spacing, color choices) to Tailwind tokens. Resist 1:1 copy-paste.

---

## 7. Done criteria for the whole handoff

The handoff is complete when:

- [ ] All three slices' done criteria pass (§2.5, §3.6, §4.9)
- [ ] A full pipeline run with a 6+ shot project produces:
  - Live cost updates in the Telemetry panel
  - Per-shot motion-fidelity flags surfaced in ReviewStage (when below floor)
  - Visual treatment of the console matching the mockup
- [ ] `git diff --stat origin/main..HEAD` shows ~1100 LOC across the three slices (rough estimate; ±300 acceptable)
- [ ] No regressions: existing `tests/unit/` and `tests/integration/` passing

---

## 8. Pricing implication (context, not code)

Closing these gaps doesn't change the per-shot cost profile (no new APIs, no new model calls). It changes:

- **Operator throughput**: the Director's Console + per-shot floors mean less manual clicking through individual scenes to find the bad takes.
- **Output consistency**: per-shot-type floors catch the failure modes a uniform floor misses, so fewer subtly-bad takes ship.
- **Sales narrative**: a polished director's console is the artifact that distinguishes "AI cinema tool" from "AI prompt sandbox" in client demos.

Anchor: **a tuned + visually-coherent pipeline supports the $3,000/video pricing the performance-capture handoff §15 established.** Without these polish gaps closed, the right price is closer to $2,000.

---

**End of handoff.** Next session: read §0 smoke from the original `docs/REFACTOR_HANDOFF.md`, confirm green, pick a slice. If picking only one, pick A.
