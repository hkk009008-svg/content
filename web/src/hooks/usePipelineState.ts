import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import type { ProgressEvent, ShotState, ShotStatus, PipelineStage, DirectorReview, PipelineState, PipelineAction, CheckpointInfo, PipelineQueueSnapshot } from '../types/project'
import { useSSE } from './useSSE'
import { apiGet, apiPost } from '../lib/api'

// ---------------------------------------------------------------------------
// Canonical stage vocabulary (Slice 11b)
// ---------------------------------------------------------------------------
//
// The backend emits far more distinct SSE `stage` strings than the 14-row
// Setup/Run rail has rows for: per-shot signals (KEYFRAME_READY,
// MOTION_BELOW_FLOOR, PERFORMANCE_SKIPPED, ...), lifecycle/abort/meta
// signals (PAUSED, RESUMED, RESUME, SCENE, CANCELLED, ERROR, CLEANUP,
// CORRECTING, ...), whole-run terminal signals (COMPLETE, DONE), and the
// SSE control frames from Slice 11a (GAP, HEARTBEAT, END) all share the
// same `ProgressEvent.stage` channel as the 14 coarse phase names —
// exactly the "backend stages drift from the UI's 14-stage rail" gap the
// 2026-07-30 audit named. Exhaustively verified against every production
// `.progress(...)` / `_wait_for_gate(...)` call site across
// cinema_pipeline.py, cinema/{shots,review}/controller.py,
// cinema/checkpoint.py, and web_server.py (grep evidence in the slice
// 11b handoff) — `cinema/pipeline.py`'s generic Phase driver is a
// separate, unwired utility class (incompatible callback signature) and
// never reaches the SSE bus, so its phase names are out of scope here.
//
// A prior version of this reducer called `setActiveStage(stage)`
// unconditionally for every event. That is actively wrong, not just
// incomplete: `/shots/<id>/keyframes/generate` (and regenerate/restart)
// publish into the SAME per-project bus via `_get_stage_pipeline` while
// the main pipeline thread sits blocked inside the KEYFRAME_REVIEW gate
// (`_wait_for_gate` polls a predicate; the gate name is NOT re-asserted
// by side-channel calls) — so clicking "Generate another keyframe" while
// reviewing legitimately re-publishes "KEYFRAME" / "KEYFRAME_READY" into
// the stream the operator is watching. Blindly following the latest
// stage string would yank `activeStage` away from 'KEYFRAME_REVIEW' back
// to 'KEYFRAME' mid-review, which (per RunPage.tsx's REGRESSION CONTRACT
// routing on `activeStage`) silently swaps the Review UI out from under
// the operator. The fix has two parts:
//
//   1. STAGE_RAIL_MAP buckets EVERY stage into exactly one of:
//        {kind:'rail', id}  -- one of the 14 PIPELINE_STAGES ids.
//        {kind:'terminal'}  -- COMPLETE/DONE: the whole rail completes.
//        {kind:'info'}      -- meta/per-shot/abort/control signal; never
//                              touches activeStage (shot-level bookkeeping
//                              for these, where it applies, is the
//                              SEPARATE per-shot routing block below).
//   2. `advanceActiveStage` only ever accepts a 'rail' transition whose
//      canonical position is STRICTLY AHEAD of the current one
//      (monotonic forward-only) — so a same-named side-channel event
//      fired during a later gate is inert instead of moving the rail
//      backward. `railIndexOf` is the ONE position function shared by
//      the reducer (`processEvent`) and the rail (`stages` below), so
//      they can never drift apart again.
//
// An unmapped stage (a key genuinely absent from STAGE_RAIL_MAP) is a
// contract break: `resolveStageBucket` throws rather than silently
// leaving the rail looking blank. Exhaustiveness is covered directly in
// usePipelineState.test.ts.
const RAIL_STAGE_IDS = [
  'STYLE', 'AUDIO', 'DECOMPOSE', 'DIRECTOR', 'PLAN_REVIEW', 'KEYFRAME',
  'KEYFRAME_REVIEW', 'PERFORMANCE', 'PERFORMANCE_REVIEW', 'MOTION',
  'REVIEW', 'SCENE_PREVIEW', 'ASSEMBLY', 'SCREENING',
] as const

type RailStageId = typeof RAIL_STAGE_IDS[number]

const RAIL_STAGE_LABELS: Record<RailStageId, string> = {
  STYLE: 'Style Rules',
  AUDIO: 'Background Music',
  DECOMPOSE: 'Shot Decomposition',
  DIRECTOR: 'Director Review',
  PLAN_REVIEW: 'Shot Plans',
  KEYFRAME: 'Keyframes',
  KEYFRAME_REVIEW: 'Keyframe Review',
  PERFORMANCE: 'Performance Capture',
  PERFORMANCE_REVIEW: 'Performance Review',
  MOTION: 'Motion',
  REVIEW: 'Final Review',
  SCENE_PREVIEW: 'Scene Preview',
  ASSEMBLY: 'Final Assembly',
  // S19 Surface B (cycle-9): SCREENING is a 14th stage inserted AFTER ASSEMBLY.
  // Visible unconditionally in the stage list; the BACKEND `CINEMA_SCREENING_STAGE`
  // env flag controls whether the pipeline actually emits SCREENING stage events.
  // Default ON as of v5.1+ flag-flip (2026-05-26); §7.7.3 Class B opt-out UX flag.
  // When explicitly opted out (CINEMA_SCREENING_STAGE=0) the pipeline goes
  // ASSEMBLY → COMPLETE as before and this stage simply remains in 'pending'
  // status (legacy-compatible pre-flip behavior).
  SCREENING: 'Screening',
}

const PIPELINE_STAGES: PipelineStage[] = RAIL_STAGE_IDS.map((id) => ({
  id,
  label: RAIL_STAGE_LABELS[id],
  status: 'pending',
}))

type StageBucket =
  | { kind: 'rail'; id: RailStageId }
  | { kind: 'route'; id: RailStageId }
  | { kind: 'terminal' }
  | { kind: 'info' }

export const STAGE_RAIL_MAP: Record<string, StageBucket> = {
  // -- the 14 rail stages (identity mapping; gate names included) --
  STYLE: { kind: 'rail', id: 'STYLE' },
  AUDIO: { kind: 'rail', id: 'AUDIO' },
  DECOMPOSE: { kind: 'rail', id: 'DECOMPOSE' },
  DIRECTOR: { kind: 'rail', id: 'DIRECTOR' },
  PLAN_REVIEW: { kind: 'rail', id: 'PLAN_REVIEW' },
  KEYFRAME: { kind: 'rail', id: 'KEYFRAME' },
  KEYFRAME_REVIEW: { kind: 'rail', id: 'KEYFRAME_REVIEW' },
  PERFORMANCE: { kind: 'rail', id: 'PERFORMANCE' },
  PERFORMANCE_REVIEW: { kind: 'rail', id: 'PERFORMANCE_REVIEW' },
  MOTION: { kind: 'rail', id: 'MOTION' },
  REVIEW: { kind: 'rail', id: 'REVIEW' },
  SCENE_PREVIEW: { kind: 'rail', id: 'SCENE_PREVIEW' },
  ASSEMBLY: { kind: 'rail', id: 'ASSEMBLY' },
  SCREENING: { kind: 'rail', id: 'SCREENING' },

  // -- whole-run terminal signals (cinema_pipeline.py COMPLETE;
  //    web_server.py's run_pipeline wrapper DONE) --
  COMPLETE: { kind: 'terminal' },
  DONE: { kind: 'terminal' },

  // -- lifecycle / meta signals; never move the rail --
  PAUSED: { kind: 'info' },
  RESUMED: { kind: 'info' },
  RESUME: { kind: 'info' },        // checkpoint-resume marker (cinema/checkpoint.py) -- distinct from RESUMED
  SCENE: { kind: 'info' },         // per-scene-loop overview marker, fires just before that scene's DECOMPOSE/DIRECTOR
  CANCELLED: { kind: 'info' },
  ERROR: { kind: 'info' },
  CLEANUP: { kind: 'info' },

  // -- per-shot signals -- side-channel-reachable during ANY gate (see the
  //    module comment above); must never move activeStage --
  SHOT_FAILED: { kind: 'info' },
  BUDGET_EXCEEDED: { kind: 'info' },
  CORRECTING: { kind: 'info' },
  KEYFRAME_DONE: { kind: 'info' },
  // A durable provider/budget halt must route to Review so its recovery
  // controls remain visible live. Idle pipeline-state hydration also derives
  // KEYFRAME_REVIEW from the durable project marker after a reload.
  KEYFRAME_HALTED: { kind: 'route', id: 'KEYFRAME_REVIEW' },
  KEYFRAME_READY: { kind: 'info' },
  KEYFRAME_RECOVERY: { kind: 'info' },
  PERFORMANCE_DONE: { kind: 'info' },
  PERFORMANCE_BLOCKED: { kind: 'info' },
  PERFORMANCE_DEFERRED: { kind: 'info' },
  PERFORMANCE_HALTED: { kind: 'info' },
  PERFORMANCE_READY: { kind: 'info' },
  PERFORMANCE_SKIPPED: { kind: 'info' },
  PERFORMANCE_SKIPPED_GATE: { kind: 'info' },
  PERFORMANCE_REVIEW_REQUIRED: { kind: 'info' },
  MOTION_DONE: { kind: 'info' },
  MOTION_HALTED: { kind: 'info' },
  MOTION_READY: { kind: 'info' },
  MOTION_BELOW_FLOOR: { kind: 'info' },
  POSTPROCESS_READY: { kind: 'info' },
  ARTIFACT_VERSION_RECOVERED: { kind: 'info' },
  REVIEW_COMPLETE: { kind: 'info' },

  // -- SSE control frames (Slice 11a). HEARTBEAT/END are filtered by
  //    useSSE before they ever reach this reducer; GAP is deliberately
  //    let through (see the GAP handling in processEvent below). All
  //    three are listed here anyway so this table is exhaustive against
  //    the real wire contract, not just against whatever useSSE happens
  //    to forward today. --
  GAP: { kind: 'info' },
  HEARTBEAT: { kind: 'info' },
  END: { kind: 'info' },
}

/** Looks up `stage` in STAGE_RAIL_MAP. Throws for a stage the table has
 *  never heard of — a genuine contract break the caller should surface
 *  loudly (a blank-looking rail is a silent failure; this is not). */
export function resolveStageBucket(stage: string): StageBucket {
  const bucket = STAGE_RAIL_MAP[stage]
  if (!bucket) {
    throw new Error(
      `usePipelineState: backend emitted stage "${stage}", which is absent ` +
      'from STAGE_RAIL_MAP. Add it there with a deliberate {kind:...} ' +
      'bucket instead of letting the rail silently drop it.',
    )
  }
  return bucket
}

/** The ONE position function shared by the reducer's monotonic-forward
 *  check and the rail's complete/running derivation. `null` (no stage
 *  yet) and an unrecognized raw string (e.g. a hydrate-only value this
 *  table doesn't special-case) both resolve to -1 -- "nothing provably
 *  before this." COMPLETE/DONE resolve one-past-the-end so every real
 *  rail id counts as behind them. */
function railIndexOf(stage: string | null): number {
  if (stage === null) return -1
  if (stage === 'COMPLETE' || stage === 'DONE') return RAIL_STAGE_IDS.length
  return (RAIL_STAGE_IDS as readonly string[]).indexOf(stage)
}

/** Monotonic forward-only advance across the canonical rail vocabulary.
 *  'info'-bucketed stages never move `activeStage`; a rail/route stage only
 *  wins if its position is STRICTLY ahead of the current one (see the
 *  module comment above STAGE_RAIL_MAP for why side-channel regen calls
 *  during a review gate make this necessary, not just tidy); 'terminal'
 *  always wins (COMPLETE/DONE outrank every real rail position). */
function advanceActiveStage(prev: string | null, stage: string): string | null {
  const bucket = resolveStageBucket(stage)
  if (bucket.kind === 'info') return prev
  if (bucket.kind === 'terminal') return stage
  return RAIL_STAGE_IDS.indexOf(bucket.id) > railIndexOf(prev) ? bucket.id : prev
}

/** Legacy `PipelineState.gate_status` is a per-PROJECT aggregate (counts,
 *  no shot ids) -- unlike a live `current_stage`, it can prove earlier
 *  gates cleared but can never say what's running RIGHT NOW. Used only
 *  as a floor for "at least this much is behind us" in the `stages`
 *  memo below; deliberately never fed into `activeStage` itself -- doing
 *  that would synthesize a stage fact the server never actually reported
 *  for this moment, exactly what this slice's reconnect contract
 *  forbids. */
function gateStatusFloorIndex(gate: PipelineState['gate_status'] | undefined | null): number {
  if (!gate || gate.total_shots <= 0) return -1
  let floor = -1
  if (gate.plans_approved === gate.total_shots) {
    floor = Math.max(floor, RAIL_STAGE_IDS.indexOf('KEYFRAME'))
  }
  if (gate.keyframes_approved === gate.total_shots) {
    floor = Math.max(floor, RAIL_STAGE_IDS.indexOf('PERFORMANCE'))
  }
  if (gate.motions_generated === gate.total_shots) {
    floor = Math.max(floor, RAIL_STAGE_IDS.indexOf('REVIEW'))
  }
  if (gate.finals_approved === gate.total_shots) {
    floor = Math.max(floor, RAIL_STAGE_IDS.indexOf('SCENE_PREVIEW'))
  }
  return floor
}

// The only two `shot_results[id].status` values any production write site
// sets (cinema/shots/controller.py:1103,1884 -- grep-verified). Deliberately
// LENIENT unlike STAGE_RAIL_MAP's throwing treatment: this reads a
// possibly-stale on-disk checkpoint written by an older code version, so an
// unrecognized value is left unset rather than crashing the hydrate fetch.
const LEGACY_SHOT_STATUS_MAP: Partial<Record<string, ShotStatus>> = {
  keyframe_review: 'image_review',
  final_review: 'final_review',
}

/** Slice 11b: reconcile the legacy `shot_results` hydrate snapshot into
 *  the SAME `Partial<ShotState>` shape `processEvent` below builds from
 *  live SSE events (8b's disclosed deferral -- see hydrateFrom). */
function shotStatesFromLegacySnapshot(
  shotResults: PipelineState['shot_results'] | undefined,
): Map<string, Partial<ShotState>> {
  const next = new Map<string, Partial<ShotState>>()
  if (!shotResults) return next
  for (const [shotId, legacy] of Object.entries(shotResults)) {
    const entry: Partial<ShotState> = { id: shotId }
    if (legacy.image) entry.generated_image = legacy.image
    if (legacy.video) entry.generated_video = legacy.video
    if (typeof legacy.identity_score === 'number' && legacy.identity_score >= 0) {
      entry.identity_score = legacy.identity_score
    }
    const mappedStatus = LEGACY_SHOT_STATUS_MAP[legacy.status]
    if (mappedStatus) entry.status = mappedStatus
    next.set(shotId, entry)
  }
  return next
}

export function usePipelineState(projectId: string | null) {
  const sse = useSSE(projectId)
  const [shotStates, setShotStates] = useState<Map<string, Partial<ShotState>>>(new Map())
  const [directorReview, setDirectorReview] = useState<DirectorReview | null>(null)
  const [activeStage, setActiveStage] = useState<string | null>(null)
  // Slice 11b: derived-from-legacy-gate_status floor for the `stages`
  // rail memo below (see gateStatusFloorIndex's docstring). Replaces the
  // old percent>=100-triggered `completedStages` Set, which almost never
  // fired for the 14 coarse stages in practice (see the STAGE_RAIL_MAP
  // module comment) and could not express "we know more is behind us
  // than activeStage alone shows" for a gate_status-only hydration.
  const [gateFloorIndex, setGateFloorIndex] = useState(-1)
  const [isPaused, setIsPaused] = useState(false)
  const [failedShots, setFailedShots] = useState<string[]>([])
  const [activeShotId, setActiveShotId] = useState<string | null>(null)
  const [notesBuffer, setNotesBuffer] = useState<ProgressEvent[]>([])
  // Slice 8b: server-derived lifecycle authority
  // (`web_server.py:_pipeline_action_authority`, via
  // `GET /api/projects/<pid>/pipeline-state`). NEVER inferred from
  // `sse.isStreaming` (transport connectivity is not job truth) -- see
  // `fetchAndHydrate` / `refreshPipelineState` below.
  const [running, setRunning] = useState(false)
  const [allowedActions, setAllowedActions] = useState<PipelineAction[]>([])
  // Slice 11c: the on-disk checkpoint summary, present whenever the
  // server's idle branch reported one (see PipelineState.checkpoint's
  // docstring) -- null while running/paused (the live-pipeline branch
  // never carries this key) or before the project has one at all.
  const [checkpoint, setCheckpoint] = useState<CheckpointInfo | null>(null)
  const [queue, setQueue] = useState<PipelineQueueSnapshot | null>(null)

  // Guards every pipeline-state fetch (project-switch hydration AND
  // on-demand post-mutation refreshes) against an out-of-order arrival:
  // bumped before every fetch is issued and on effect cleanup, compared
  // when a fetch resolves. A response whose epoch no longer matches the
  // current one was superseded by a newer fetch (a fresh project switch,
  // or a fresh refresh) and is dropped rather than applied.
  const epochRef = useRef(0)

  // Shared by the PID-switch effect below and `start()` -- both need the
  // same "forget everything about the previous run" reset.
  const resetLocalState = useCallback(() => {
    setShotStates(new Map())
    setDirectorReview(null)
    setActiveStage(null)
    setGateFloorIndex(-1)
    setIsPaused(false)
    setFailedShots([])
    setActiveShotId(null)
    setNotesBuffer([])
    setRunning(false)
    setAllowedActions([])
    setCheckpoint(null)
    setQueue(null)
  }, [])

  const hydrateFrom = useCallback((state: PipelineState) => {
    setIsPaused(!!state.paused)
    setFailedShots(state.failed_shots ?? [])
    setActiveStage(state.current_stage || null)
    setRunning(!!state.running)
    setAllowedActions(state.allowed_actions ?? [])
    setQueue(state.queue ?? null)
    // Absent on the live-pipeline branch by design (Slice 11c) -- null
    // rather than a stale prior idle-branch value.
    setCheckpoint(state.checkpoint ?? null)
    // Slice 11b: legacy shot_results/gate_status reconciliation (8b's
    // disclosed deferral). gate_status only ever RAISES the rail's
    // completed floor (see gateStatusFloorIndex -- it never asserts a
    // live "running" stage). shot_results hydrates shotStates in the
    // SAME Partial<ShotState> shape processEvent produces from live SSE
    // events, merged so a legacy field only FILLS A GAP -- it can never
    // overwrite a richer field a live event already set (a page reload
    // mid-run, or a pause/resume refresh, must not wipe accumulated
    // coherence_score/take_kind/etc. back down to the legacy snapshot).
    setGateFloorIndex(gateStatusFloorIndex(state.gate_status))
    setShotStates((prev) => {
      const legacy = shotStatesFromLegacySnapshot(state.shot_results)
      if (legacy.size === 0) return prev
      const next = new Map(prev)
      for (const [shotId, legacyEntry] of legacy) {
        const existing = next.get(shotId)
        next.set(shotId, existing ? { ...legacyEntry, ...existing } : legacyEntry)
      }
      return next
    })
  }, [])

  const fetchAndHydrate = useCallback(async (pid: string) => {
    epochRef.current += 1
    const myEpoch = epochRef.current
    const result = await apiGet<PipelineState>(`/api/projects/${pid}/pipeline-state`)
    if (epochRef.current !== myEpoch) return // superseded by a newer switch/refresh
    if (result.ok) hydrateFrom(result.data)
  }, [hydrateFrom])

  // PID boundary (Slice 8b): reset synchronously so no part of the OLD
  // project's shot/failure/stage/action state is visible even for a
  // paint, then hydrate from the NEW project's real backend state instead
  // of assuming a fresh idle run -- a project can already be mid-run,
  // paused, or pending-start when it's selected (e.g. a page reload, or
  // switching back to a project with a run left going).
  useEffect(() => {
    resetLocalState()
    if (!projectId) {
      epochRef.current += 1 // invalidate anything still in flight for the old id
      return
    }
    void fetchAndHydrate(projectId)
    return () => {
      // Also invalidate on cleanup (real unmount, or React 18 StrictMode's
      // dev-only double-invoke) even though no new fetch follows here.
      epochRef.current += 1
    }
  }, [projectId, resetLocalState, fetchAndHydrate])

  /** Public, no-arg refresh: re-fetch and re-derive running/allowed_actions
   *  (plus the other hydrated fields) from the server right now. Used
   *  after pause/resume/generate/cancel so the UI reflects CONFIRMED
   *  backend truth instead of assuming the POST means the transition
   *  already happened. No-ops when there is no active project. */
  const refreshPipelineState = useCallback(() => {
    if (!projectId) return Promise.resolve()
    return fetchAndHydrate(projectId)
  }, [projectId, fetchAndHydrate])

  // Queue position and cross-process lease state do not travel over this
  // process's in-memory SSE bus. Poll the authoritative snapshot only while
  // a durable job is active; terminal/idle projects stay request-free.
  useEffect(() => {
    if (!projectId || !queue || !['queued', 'running'].includes(queue.state)) return
    const timer = window.setInterval(() => {
      void refreshPipelineState()
    }, 2_000)
    return () => window.clearInterval(timer)
  }, [projectId, queue?.state, queue?.job_id, refreshPipelineState])

  // A reload/switch can hydrate a job that was already accepted by the
  // backend. Observe that existing run without entering the fresh-run path:
  // sse.attach() preserves the hydrated snapshot, stream history, and last
  // event id, and is idempotent across the queue poll above.
  useEffect(() => {
    const queueIsActive = queue?.state === 'queued' || queue?.state === 'running'
    if (projectId && (running || queueIsActive)) sse.attach()
  }, [projectId, running, queue?.state, queue?.job_id, sse.attach])

  // Route incoming events to the right state buckets
  const processEvent = useCallback((event: ProgressEvent) => {
    const { stage, scene_id, shot_id, image_url, video_url, take_id, take_kind, identity_score, director_review,
            coherence_score, motion_score, shot_type, failure_reason, quality_metrics } = event

    // Track pause/resume
    if (stage === 'PAUSED') { setIsPaused(true); return }
    if (stage === 'RESUMED') { setIsPaused(false); return }

    // Slice 11a's GAP control frame: the client provably missed events
    // the replay buffer already evicted. Guessing at what happened in
    // that range would be exactly the "synthesize stage facts absent
    // from the server" this slice's reconnect contract forbids --
    // reconcile with a fresh authoritative snapshot instead. GAP carries
    // no shot_id/scene_id/director_review, so nothing else below applies
    // to it (mirrors the PAUSED/RESUMED early-returns above).
    if (stage === 'GAP') { void refreshPipelineState(); return }

    // Track active stage -- monotonic forward-only across the canonical
    // rail vocabulary (see the STAGE_RAIL_MAP module comment above
    // PIPELINE_STAGES for why this can no longer be an unconditional
    // overwrite).
    setActiveStage((prev) => advanceActiveStage(prev, stage))

    // Track failed shots
    if (stage === 'SHOT_FAILED' && shot_id) {
      setFailedShots(prev => [...prev, shot_id])
    }

    // Track most-recent active shot (non-failure events only)
    if (shot_id && stage !== 'SHOT_FAILED') {
      setActiveShotId(shot_id)
    }

    // Rolling notes buffer (last 20 events)
    setNotesBuffer(prev => [event, ...prev].slice(0, 20))

    // Route director review events
    if (director_review) {
      setDirectorReview(director_review)
    }

    // Route shot-level events
    if (shot_id && scene_id) {
      setShotStates(prev => {
        const next = new Map(prev)
        const existing = next.get(shot_id) || { id: shot_id, scene_id }
        const updated = { ...existing }

        if (image_url) updated.generated_image = image_url
        if (video_url) updated.generated_video = video_url
        if (take_id) updated.take_id = take_id
        if (take_kind) updated.take_kind = take_kind
        if (identity_score !== undefined && identity_score >= 0) updated.identity_score = identity_score
        if (coherence_score !== undefined && coherence_score >= 0) updated.coherence_score = coherence_score
        if (motion_score !== undefined && motion_score >= 0) updated.motion_score = motion_score
        if (shot_type) updated.shot_type = shot_type
        if (failure_reason) updated.failure_reason = failure_reason
        if (quality_metrics) updated.quality_metrics = quality_metrics

        // Map stage to shot status
        if (stage === 'PLAN_REVIEW') updated.status = 'plan_review'
        if (stage === 'KEYFRAME') updated.status = 'generating_image'
        if (stage === 'KEYFRAME_READY' || stage === 'KEYFRAME_REVIEW') updated.status = 'image_review'
        if (stage === 'PERFORMANCE') updated.status = 'generating_performance' as any
        if (stage === 'PERFORMANCE_READY' || stage === 'PERFORMANCE_REVIEW') updated.status = 'performance_review' as any
        if (stage === 'SHOT_FAILED') updated.status = 'failed'
        if (stage === 'MOTION') updated.status = 'generating_video'
        if (stage === 'MOTION_READY' || stage === 'REVIEW') updated.status = 'final_review'
        if (stage === 'POSTPROCESS_READY') updated.status = 'post_processing'
        if (stage === 'COMPLETE') updated.status = 'complete'

        next.set(shot_id, updated)
        return next
      })
    }
  }, [refreshPipelineState])

  // Compute pipeline stages with live status. `liveIdx` is the truthful
  // "currently running" position (only ever set from a real rail-mapped
  // SSE stage or a hydrated current_stage -- see STAGE_RAIL_MAP);
  // `completeIdx` additionally trusts gate_status's floor for stages we
  // can PROVE cleared even without a live pointer (e.g. hydrating a
  // project between runs). A stage only ever renders 'running' at
  // `liveIdx` itself -- gate_status can move the completed boundary
  // forward but can never assert a stage is currently active (see
  // gateStatusFloorIndex's docstring: that would synthesize a fact the
  // server never reported for this moment).
  const stages = useMemo((): PipelineStage[] => {
    const liveIdx = railIndexOf(activeStage)
    const completeIdx = Math.max(liveIdx, gateFloorIndex)
    return PIPELINE_STAGES.map((s, i) => ({
      ...s,
      status: i < completeIdx
        ? 'complete'
        : i === liveIdx
          ? 'running'
          : s.status,
    }))
  }, [activeStage, gateFloorIndex])

  // Pipeline control actions -- neither flips local state optimistically.
  // Each fires the POST, then re-confirms truth from the server: the
  // request succeeding does not mean the transition already happened (the
  // pending-start window is exactly this), so `isPaused`/`running`/
  // `allowedActions` only ever change via `hydrateFrom` (Slice 8
  // requirement 5 -- never paint optimistic success).
  const pause = useCallback(async () => {
    if (!projectId) return
    await apiPost(`/api/projects/${projectId}/pause`)
    await refreshPipelineState()
  }, [projectId, refreshPipelineState])

  const resume = useCallback(async () => {
    if (!projectId) return
    await apiPost(`/api/projects/${projectId}/resume`)
    await refreshPipelineState()
  }, [projectId, refreshPipelineState])

  /** Every POST mutation below funnels through here. A non-2xx response, a
   *  non-JSON body, or a network failure ALWAYS yields an object with a
   *  truthy `.error` string (synthesizing one when the endpoint's own
   *  failure body omitted it) -- so the existing `if (!result?.error)` /
   *  `if (result?.success)` checks in ReviewStage.tsx / ScreeningStage.tsx
   *  stay truthful for every failure mode, not just the ones a given
   *  endpoint happens to encode in JSON. A real 2xx body passes through
   *  unchanged (existing callers read fields like `.take`/`.approved`
   *  straight off it). */
  const postJson = useCallback(async (path: string, body?: Record<string, any>) => {
    const result = await apiPost<Record<string, any>>(path, body)
    if (result.ok) return result.data ?? {}
    const bodyRecord = (result.body && typeof result.body === 'object' && !Array.isArray(result.body))
      ? result.body as Record<string, any>
      : {}
    return { ...bodyRecord, success: false, error: bodyRecord.error || result.error }
  }, [])

  const regenerateShot = useCallback(async (shotId: string, positivePrompt?: string, negativePrompt?: string) => {
    if (!projectId) return null
    const body: any = {}
    if (positivePrompt) body.positive_prompt = positivePrompt
    if (negativePrompt) body.negative_prompt = negativePrompt
    return postJson(`/api/projects/${projectId}/shots/${shotId}/regenerate`, body)
  }, [projectId, postJson])

  const approveShotPlan = useCallback(async (shotId: string) => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/plan/approve`)
  }, [projectId, postJson])

  const rejectShotPlan = useCallback(async (shotId: string, reason = '') => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/plan/reject`, { reason })
  }, [projectId, postJson])

  const generateKeyframe = useCallback(async (shotId: string, positivePrompt?: string, negativePrompt?: string) => {
    if (!projectId) return null
    const body: Record<string, any> = {}
    if (positivePrompt) body.positive_prompt = positivePrompt
    if (negativePrompt) body.negative_prompt = negativePrompt
    return postJson(`/api/projects/${projectId}/shots/${shotId}/keyframes/generate`, body)
  }, [projectId, postJson])

  const restartShot = useCallback(async (shotId: string, positivePrompt?: string, negativePrompt?: string) => {
    if (!projectId) return null
    const body: Record<string, any> = {}
    if (positivePrompt) body.positive_prompt = positivePrompt
    if (negativePrompt) body.negative_prompt = negativePrompt
    return postJson(`/api/projects/${projectId}/shots/${shotId}/restart`, body)
  }, [projectId, postJson])

  const approveKeyframe = useCallback(async (shotId: string, takeId: string) => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/keyframes/${takeId}/approve`)
  }, [projectId, postJson])

  const approvePerformance = useCallback(async (shotId: string, takeId: string) => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/performance/${takeId}/approve`)
  }, [projectId, postJson])

  const generatePerformance = useCallback(async (shotId: string) => {
    if (!projectId) return null
    const storageKey = `cinema:performance-request:${projectId}:${shotId}`
    let requestId = ''
    try {
      requestId = window.sessionStorage.getItem(storageKey) || ''
    } catch {
      // Storage can be unavailable in privacy modes; cryptographic request
      // identity still protects this individual HTTP action.
    }
    if (!/^[0-9a-f]{32}$/.test(requestId)) {
      if (typeof globalThis.crypto?.randomUUID !== 'function') {
        return {
          success: false,
          error: 'This browser cannot create a safe performance request ID.',
          code: 'performance_request_id_unavailable',
        }
      }
      requestId = globalThis.crypto.randomUUID().replace(/-/g, '').toLowerCase()
      try {
        window.sessionStorage.setItem(storageKey, requestId)
      } catch {
        // The request still carries the ID; only cross-refresh recovery is lost.
      }
    }
    let result = await postJson(
      `/api/projects/${projectId}/shots/${shotId}/performance/generate`,
      { request_id: requestId },
    )
    const persistedRequestId = result?.code === 'performance_request_active'
      ? String(result?.request?.request_id || '')
      : ''
    if (
      /^[0-9a-f]{32}$/.test(persistedRequestId)
      && persistedRequestId !== requestId
    ) {
      // A browser/session crash can lose sessionStorage while the server still
      // owns a durable deferred request. Adopt the server-returned request ID
      // and retry once; backend input binding decides whether it is safe to
      // resume, so this cannot turn changed bytes into a new paid submission.
      requestId = persistedRequestId
      try {
        window.sessionStorage.setItem(storageKey, requestId)
      } catch {
        // The in-memory retry remains safe even when storage is unavailable.
      }
      result = await postJson(
        `/api/projects/${projectId}/shots/${shotId}/performance/generate`,
        { request_id: requestId },
      )
    }
    const keepForRecovery = result?.success !== true && (
      result?.retryable === true
      || !result?.code
      || result?.code === 'provider_job_deferred'
      || result?.code === 'performance_request_active'
    )
    if (!keepForRecovery) {
      try {
        window.sessionStorage.removeItem(storageKey)
      } catch {
        // Nothing else depends on storage cleanup.
      }
    }
    return result
  }, [projectId, postJson])

  const skipPerformance = useCallback(async (shotId: string, reason: string) => {
    if (!projectId) return null
    return postJson(
      `/api/projects/${projectId}/shots/${shotId}/performance/skip`,
      { confirmed: true, reason },
    )
  }, [projectId, postJson])

  const generateMotion = useCallback(async (shotId: string) => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/motion/generate`)
  }, [projectId, postJson])

  const approveFinal = useCallback(async (shotId: string, takeId: string) => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/final/${takeId}/approve`)
  }, [projectId, postJson])

  const correctShot = useCallback(async (shotId: string, action: string, params: Record<string, any> = {}, takeId?: string) => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/correct`, { action, params, take_id: takeId })
  }, [projectId, postJson])

  const diagnoseShot = useCallback(async (shotId: string, takeId?: string, deep = false) => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/diagnose`, { ...(takeId ? { take_id: takeId } : {}), deep })
  }, [projectId, postJson])

  const proceedToAssembly = useCallback(async () => {
    if (!projectId) return
    return postJson(`/api/projects/${projectId}/assemble`)
  }, [projectId, postJson])

  /** S17 + S18: directorial iteration — POST flat body `{ prose, target_stage, verb?, params? }`
   *  to the iterate endpoint. On success the new take is included in the response
   *  body as `{ success: true, take: {...} }`. The caller is responsible for
   *  refreshing the project so the new take appears in the relevant take list.
   *  On 404 (CINEMA_DIRECTORIAL_ITERATION flag off), surface the error JSON
   *  rather than throwing so the IterationPanel can show an inline message.
   *  Returns `null` as the no-op contract when projectId is unset (called
   *  before a project is loaded); callers treat null as "did not run."
   *
   *  S18: `targetStage` defaults to 'keyframe' for back-compat with S17 callers
   *  (the KEYFRAME_REVIEW wiring still works without changes). `verb`+`params`
   *  are optional structured-iteration extensions; when omitted, the endpoint
   *  treats the call as freeform (the original S17 path).
   *
   *  Server endpoint accepts both nested `{intent: {...}}` and flat shapes per
   *  the F1 accept-both decision (operator Lane V #4, 2026-05-25T15-49-12Z);
   *  we send the flat shape to stay aligned with the existing 16 endpoint
   *  tests. The `verb`/`params` keys travel cleanly through DirectorialIntent
   *  validation because verb is Optional[str] and params is dict — no schema
   *  migration required for new verbs. */
  const iterateTake = useCallback(async (
    shotId: string,
    takeId: string,
    prose: string,
    targetStage: 'keyframe' | 'performance' | 'motion' = 'keyframe',
    verb?: string,
    params?: Record<string, unknown>,
  ) => {
    if (!projectId) return null
    const body: Record<string, unknown> = { prose, target_stage: targetStage }
    if (verb) {
      body.verb = verb
      body.params = params ?? {}
    }
    return postJson(`/api/projects/${projectId}/shots/${shotId}/takes/${takeId}/iterate`, body)
  }, [projectId, postJson])

  /** S20 (cycle-9 Surface B): operator approves the screened cut.
   *  POSTs to /api/projects/<pid>/screening/approve. The endpoint is
   *  feature-flagged behind CINEMA_SCREENING_STAGE; a 404 surfaces here
   *  as a JSON error rather than throwing, so the caller can render the
   *  inline error. Returns null when projectId is unset (same no-op
   *  contract as iterateTake). */
  const approveScreening = useCallback(async () => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/screening/approve`)
  }, [projectId, postJson])

  /** S21 (cycle-9 Surface B): re-assemble the cut from current approved takes.
   *  POSTs to /api/projects/<pid>/assemble/re-assemble with
   *  ``{only_if_changed: bool}``. Returns the JSON response shape:
   *    { success, new_assembled_path, regenerated_shots, cost_estimate_seconds, skipped }
   *
   *  Mirrors approveScreening's no-op-when-projectId-null contract. The
   *  endpoint is feature-flagged behind CINEMA_SCREENING_STAGE; 404 surfaces
   *  in the JSON for the caller to render.
   *
   *  ``onlyIfChanged=true`` (default) is the operator-facing button's normal
   *  click — short-circuits when nothing changed. ``false`` is reserved for
   *  a "force re-assemble" power-user override (not wired into UI for v1). */
  const reassembleProject = useCallback(async (onlyIfChanged: boolean = true) => {
    if (!projectId) return null
    // (S21 reviewer Minor #5's non-JSON/500 guard is now `postJson`'s job
    // uniformly -- see its docstring above.)
    return postJson(`/api/projects/${projectId}/assemble/re-assemble`, { only_if_changed: onlyIfChanged })
  }, [projectId, postJson])

  // Enhanced start that also processes events -- reuses the same reset
  // `usePipelineState` applies at a project switch, since starting a new
  // run within the SAME project needs to forget the previous run's shot/
  // failure/stage state too.
  const start = useCallback(() => {
    resetLocalState()
    sse.start()
  }, [sse, resetLocalState])

  return {
    shotStates,
    stages,
    activeStage,
    directorReview,
    processEvent,
    isPaused,
    failedShots,
    activeShotId,
    notesBuffer,
    // Slice 8b: server-derived lifecycle authority + refresh.
    running,
    allowedActions,
    // Slice 11c: on-disk checkpoint summary (idle branch only -- see
    // hydrateFrom above).
    checkpoint,
    queue,
    refreshPipelineState,
    // Pipeline controls
    pause,
    resume,
    approveShotPlan,
    rejectShotPlan,
    generateKeyframe,
    approveKeyframe,
    approvePerformance,
    generatePerformance,
    skipPerformance,
    generateMotion,
    approveFinal,
    regenerateShot,
    restartShot,
    correctShot,
    diagnoseShot,
    proceedToAssembly,
    iterateTake,
    approveScreening,
    reassembleProject,
    // Pass-through from useSSE
    events: sse.events,
    latest: sse.latest,
    isStreaming: sse.isStreaming,
    start,
    stop: sse.stop,
  }
}
