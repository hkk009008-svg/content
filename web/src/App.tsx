import { useState, useEffect, useLayoutEffect, useCallback, useRef } from 'react'
import type { Project, AppConfig, ProgressEvent } from './types/project'
import { usePipelineState } from './hooks/usePipelineState'
import { ErrorBoundary } from './components/ui'
import { PageProvider, usePage } from './context/PageContext'
import ProjectSelector from './components/ProjectSelector'
import AppShell from './components/AppShell'
import { apiGet, apiPost } from './lib/api'

const API = '/api'

/**
 * App — thin provider wrapper. All state + wiring lives in `AppInner`, which
 * must run under `<PageProvider>` so `handleGenerate` can flip the shell to the
 * Run page via `usePage().setPage`.
 */
export default function App() {
  return (
    <PageProvider>
      <AppInner />
    </PageProvider>
  )
}

function AppInner() {
  const { setPage, resetForNewProject } = usePage()
  const [project, setProject] = useState<Project | null>(null)
  const [config, setConfig] = useState<AppConfig | null>(null)
  // True only while THIS session's own /generate request is in flight (a
  // brief, self-correcting spinner) -- NOT "is the pipeline running".
  // That truth comes from the hook's server-derived `running` below; see
  // the `generating={running || starting}` prop passed to AppShell.
  const [starting, setStarting] = useState(false)
  // Surfaces a failed mutation this component owns directly (generate/
  // cancel) or one wrapped by `withRefresh` (approve/reject/iterate/...).
  // Slice 8 requirement 5: 409/non-2xx is an error, never painted as
  // optimistic success.
  const [actionError, setActionError] = useState<string | null>(null)

  const {
    events, latest, isStreaming, start: startSSE, stop: stopSSE,
    stages, activeStage, shotStates, directorReview, processEvent,
    isPaused, failedShots, running, refreshPipelineState,
    pause: pausePipeline, resume: resumePipeline,
    approveShotPlan, rejectShotPlan, generateKeyframe, approveKeyframe, approvePerformance, generateMotion, approveFinal,
    regenerateShot, restartShot, correctShot, diagnoseShot, proceedToAssembly, iterateTake,
    approveScreening, reassembleProject,
  } = usePipelineState(project?.id ?? null)

  // P1-3: sticky BUDGET_EXCEEDED halt. Owned HERE (not in a page) because the
  // gate fires mid-run and must survive page switches — AppShell renders the
  // banner in its always-mounted top region.
  // Not keyed on `latest`: the phase abort emits MOTION_HALTED right after
  // the halt event, which would flash a latest-keyed banner away.
  const [budgetHalt, setBudgetHalt] = useState<ProgressEvent | null>(null)
  useEffect(() => {
    if (latest?.stage === 'BUDGET_EXCEEDED') setBudgetHalt(latest)
  }, [latest])

  // PID boundary (Slice 8b): everything App.tsx itself owns resets
  // synchronously (before paint) the instant the project identity changes
  // -- `AppInner` never unmounts across a project switch (only the
  // conditionally-rendered ProjectSelector/AppShell subtree does), so
  // without this, project B would render with project A's stale config,
  // in-flight-request spinner, budget halt, and page/focus still set.
  // `usePipelineState`'s own project-scoped fields (shots/failures/stage/
  // running/allowedActions) reset the same way inside that hook.
  useLayoutEffect(() => {
    setConfig(null)
    setStarting(false)
    setActionError(null)
    setBudgetHalt(null)
    resetForNewProject()
  }, [project?.id, resetForNewProject])

  // Config is project-scoped once a project is selected: `video_engines`
  // (the server-reconciled engine-selectability view UI pickers consume —
  // see web/src/lib/engines.ts) reads that project's persisted shot targets
  // + api_engines overrides, so it's only meaningful with `project_id` set.
  // Nothing before project-selection (ProjectSelector) reads `config`, so
  // there's no need to fetch it until a project exists. Guarded against a
  // stale response landing after a further project switch — the
  // layout effect above already reset `config` to null synchronously, and
  // an out-of-order resolve here must not paint over the newer project.
  useEffect(() => {
    if (!project) return
    let cancelled = false
    const pid = project.id
    apiGet<AppConfig>(`${API}/config?project_id=${encodeURIComponent(pid)}`).then((result) => {
      if (cancelled) return
      if (result.ok) setConfig(result.data)
    })
    return () => { cancelled = true }
  }, [project?.id])

  // Guards the ROOT project identity against an out-of-order arrival --
  // same epoch/generation discipline `usePipelineState`'s `epochRef` uses
  // for its own (project-scoped) state, applied one level up at the
  // `project` object itself. `loadProject` is the ONLY thing that ever
  // calls `setProject` with fetched data (both the initial ProjectSelector
  // pick and every `refreshProject` re-fetch funnel through it), so bumping
  // here is a single choke point: a fresh `loadProject` call -- for a NEW
  // id, or a re-confirming refresh of the SAME id -- invalidates whatever
  // request was already in flight. Without this, a slow refresh for
  // project A that is still in flight when the user switches to project B
  // would resolve later and stomp B's project object with A's (the exact
  // leak class Slice 8b closed inside the hook, still open here at root).
  const projectEpochRef = useRef(0)

  const loadProject = useCallback(async (id: string) => {
    projectEpochRef.current += 1
    const myEpoch = projectEpochRef.current
    const result = await apiGet<Project>(`${API}/projects/${id}`)
    if (projectEpochRef.current !== myEpoch) return // superseded by a newer load/switch
    if (result.ok) setProject(result.data)
  }, [])

  const refreshProject = useCallback(async () => {
    if (project) await loadProject(project.id)
  }, [project, loadProject])

  // Explicit "leave this project" path (back to ProjectSelector) does not
  // go through `loadProject`, so it must invalidate the epoch itself --
  // mirrors the hook's own `!projectId` early-bump branch -- otherwise a
  // straggling refresh for the project just left would resolve after
  // `setProject(null)` and silently drag the UI back into it.
  const handleBackToProjects = useCallback(() => {
    projectEpochRef.current += 1
    setProject(null)
  }, [])

  const handleGenerate = async () => {
    if (!project) return
    setActionError(null)
    setBudgetHalt(null) // new run: the previous halt is history
    setStarting(true)
    const result = await apiPost<{ error?: string }>(`${API}/projects/${project.id}/generate`)
    setStarting(false)
    if (result.ok) {
      setPage('run')  // Switch to the Run page (replaces the old mode='pipeline')
      startSSE()
    } else {
      setActionError(result.error)
    }
    await refreshPipelineState() // authoritative truth either way
  }

  const handleCancel = async () => {
    if (!project) return
    setActionError(null)
    const result = await apiPost(`${API}/projects/${project.id}/cancel`)
    if (result.ok) {
      stopSSE()
    } else {
      setActionError(result.error)
    }
    await refreshPipelineState() // authoritative truth either way
  }

  const handleBackToSetup = () => {
    setPage('setup')
  }

  const withRefresh = useCallback(async (action: () => Promise<any>) => {
    const result = await action()
    // Feature-specific mutation functions (usePipelineState.ts) always
    // resolve to an object with a truthy `.error` string on failure, never
    // throw, and never claim success on a non-2xx — see that file's
    // `postJson`. Surface it; a success result clears any prior error.
    if (result && typeof result === 'object' && 'error' in result && result.error) {
      setActionError(String(result.error))
    } else {
      setActionError(null)
    }
    await refreshProject()
    return result
  }, [refreshProject])

  // Process SSE events through pipeline state router
  useEffect(() => {
    if (latest) processEvent(latest)
  }, [latest, processEvent])

  useEffect(() => {
    if (!latest || !project) return
    const refreshStages = new Set([
      'DECOMPOSE',
      'PLAN_REVIEW',
      'KEYFRAME_READY',
      'KEYFRAME_REVIEW',
      'MOTION_READY',
      'POSTPROCESS_READY',
      'REVIEW',
      'SCENE_PREVIEW',
      'COMPLETE',
    ])
    if (refreshStages.has(latest.stage)) {
      refreshProject()
    }
  }, [latest, project, refreshProject])

  // Re-confirm run/allowed-actions truth from the server on a terminal SSE
  // stage, instead of assuming completion locally (Slice 8 requirement 3).
  useEffect(() => {
    if (latest?.stage === 'DONE' || latest?.stage === 'ERROR' || latest?.stage === 'COMPLETE') {
      refreshPipelineState()
    }
  }, [latest, refreshPipelineState])

  if (!project) {
    return <ProjectSelector onSelect={loadProject} />
  }

  // Pipeline system-level surfaces — computed here and threaded through
  // AppShell → RunPage unchanged (parity with the old mode==='pipeline' block;
  // the intermediate `pipeline/PipelineLayout` component was deleted in Task 13).
  const pipelineError =
    latest?.stage === 'ERROR'
      ? {
          message: latest.failure_reason || latest.detail || 'The pipeline reported an error.',
          hint: 'The director has stopped the run. You can restart from setup, or retry to resume.',
          onRetry: handleGenerate,
        }
      : null

  const pipelineLoadingLabel =
    starting && !isStreaming && events.length === 0
      ? 'Calling the projection room'
      : null

  return (
    <ErrorBoundary>
      {actionError && (
        <div
          role="alert"
          className="fixed bottom-4 right-4 z-[60] flex max-w-sm items-start gap-3
            rounded border border-fail/50 bg-fail px-4 py-3 text-sm text-white shadow-lg"
        >
          <span className="flex-1">{actionError}</span>
          <button
            onClick={() => setActionError(null)}
            aria-label="Dismiss error"
            className="text-white/80 hover:text-white"
          >
            &times;
          </button>
        </div>
      )}
      <AppShell
        // ── EditorialShell-parity props ──
        project={project}
        config={config}
        events={events}
        latest={latest}
        isStreaming={isStreaming}
        generating={running || starting}
        onBackToProjects={handleBackToProjects}
        onGenerate={handleGenerate}
        onCancel={handleCancel}
        onRefreshProject={refreshProject}
        onOpenConsole={() => setPage('run')}
        onOpenCapability={() => setPage('capability')}
        apiBase={API}
        budgetHalt={budgetHalt}
        onDismissBudgetHalt={() => setBudgetHalt(null)}
        // ── Pipeline state (Run page) ──
        stages={stages}
        activeStage={activeStage}
        shotStates={shotStates}
        directorReview={directorReview}
        isPaused={isPaused}
        failedShots={failedShots}
        pipelineError={pipelineError}
        pipelineLoadingLabel={pipelineLoadingLabel}
        // ── Pipeline callbacks (withRefresh-wrapped except onDiagnoseShot / onReassemble) ──
        onBack={handleBackToSetup}
        onPause={pausePipeline}
        onResume={resumePipeline}
        onApproveShotPlan={(shotId) => withRefresh(() => approveShotPlan(shotId))}
        onRejectShotPlan={(shotId, reason) => withRefresh(() => rejectShotPlan(shotId, reason))}
        onGenerateKeyframe={(shotId, positive, negative) => withRefresh(() => generateKeyframe(shotId, positive, negative))}
        onApproveKeyframe={(shotId, takeId) => withRefresh(() => approveKeyframe(shotId, takeId))}
        onApprovePerformance={(shotId, takeId) => withRefresh(() => approvePerformance(shotId, takeId))}
        onGenerateMotion={(shotId) => withRefresh(() => generateMotion(shotId))}
        onApproveFinal={(shotId, takeId) => withRefresh(() => approveFinal(shotId, takeId))}
        onRegenerateShot={(shotId, positive, negative) => withRefresh(() => regenerateShot(shotId, positive, negative))}
        onRestartShot={(shotId, positive, negative) => withRefresh(() => restartShot(shotId, positive, negative))}
        onCorrectShot={(shotId, action, params, takeId) => withRefresh(() => correctShot(shotId, action, params, takeId))}
        onDiagnoseShot={(shotId, takeId, deep) => diagnoseShot(shotId, takeId, deep)}
        onProceedToAssembly={() => withRefresh(() => proceedToAssembly())}
        onIterate={(shotId, takeId, prose, targetStage, verb, params) =>
          withRefresh(() => iterateTake(shotId, takeId, prose, targetStage, verb, params))
        }
        onApproveFinalCut={async () => {
          await withRefresh(() => approveScreening())
        }}
        onReassemble={(onlyIfChanged) => reassembleProject(onlyIfChanged)}
      />
    </ErrorBoundary>
  )
}
