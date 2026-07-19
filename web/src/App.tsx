import { useState, useEffect, useCallback } from 'react'
import type { Project, AppConfig, ProgressEvent } from './types/project'
import { usePipelineState } from './hooks/usePipelineState'
import { ErrorBoundary } from './components/ui'
import { PageProvider, usePage } from './context/PageContext'
import ProjectSelector from './components/ProjectSelector'
import AppShell from './components/AppShell'

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
  const { setPage } = usePage()
  const [project, setProject] = useState<Project | null>(null)
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [generating, setGenerating] = useState(false)

  const {
    events, latest, isStreaming, start: startSSE, stop: stopSSE,
    stages, activeStage, shotStates, directorReview, processEvent,
    isPaused, failedShots, pause: pausePipeline, resume: resumePipeline,
    approveShotPlan, rejectShotPlan, generateKeyframe, approveKeyframe, approvePerformance, generateMotion, approveFinal,
    regenerateShot, restartShot, correctShot, diagnoseShot, proceedToAssembly, iterateTake,
    approveScreening, reassembleProject,
  } = usePipelineState(project?.id ?? null)

  // Load config on mount
  useEffect(() => {
    fetch(`${API}/config`).then(r => r.json()).then(setConfig).catch(() => {})
  }, [])

  const loadProject = useCallback(async (id: string) => {
    const res = await fetch(`${API}/projects/${id}`)
    if (res.ok) setProject(await res.json())
  }, [])

  const refreshProject = useCallback(async () => {
    if (project) await loadProject(project.id)
  }, [project, loadProject])

  // P1-3: sticky BUDGET_EXCEEDED halt. Owned HERE (not in a page) because the
  // gate fires mid-run and must survive page switches — AppShell renders the
  // banner in its always-mounted top region.
  // Not keyed on `latest`: the phase abort emits MOTION_HALTED right after
  // the halt event, which would flash a latest-keyed banner away.
  const [budgetHalt, setBudgetHalt] = useState<ProgressEvent | null>(null)
  useEffect(() => {
    if (latest?.stage === 'BUDGET_EXCEEDED') setBudgetHalt(latest)
  }, [latest])

  const handleGenerate = async () => {
    if (!project) return
    setGenerating(true)
    setBudgetHalt(null) // new run: the previous halt is history
    setPage('run')  // Switch to the Run page (replaces the old mode='pipeline')
    await fetch(`${API}/projects/${project.id}/generate`, { method: 'POST' })
    startSSE()
  }

  const handleCancel = async () => {
    if (!project) return
    await fetch(`${API}/projects/${project.id}/cancel`, { method: 'POST' })
    stopSSE()
    setGenerating(false)
  }

  const handleBackToSetup = () => {
    setPage('setup')
  }

  const withRefresh = useCallback(async (action: () => Promise<any>) => {
    const result = await action()
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

  // Watch for generation completion
  useEffect(() => {
    if (latest?.stage === 'DONE' || latest?.stage === 'ERROR' || latest?.stage === 'COMPLETE') {
      setGenerating(false)
    }
  }, [latest])

  if (!project) {
    return <ProjectSelector onSelect={loadProject} />
  }

  // Pipeline system-level surfaces — computed here and threaded through
  // AppShell → RunPage → PipelineLayout unchanged (parity with the old
  // mode==='pipeline' block).
  const pipelineError =
    latest?.stage === 'ERROR'
      ? {
          message: latest.failure_reason || latest.detail || 'The pipeline reported an error.',
          hint: 'The director has stopped the run. You can restart from setup, or retry to resume.',
          onRetry: handleGenerate,
        }
      : null

  const pipelineLoadingLabel =
    generating && !isStreaming && events.length === 0
      ? 'Calling the projection room'
      : null

  return (
    <ErrorBoundary>
      <AppShell
        // ── EditorialShell-parity props ──
        project={project}
        config={config}
        events={events}
        latest={latest}
        isStreaming={isStreaming}
        generating={generating}
        onBackToProjects={() => setProject(null)}
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
